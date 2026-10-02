"""Run slow jobs from a QThreadPool worker with a progress dialog and Cancel.

The worker thread only waits for a child process (see
:mod:`pdf_editor.core.jobs`), so it holds no PyMuPDF objects and the GUI
thread stays fully responsive while the job runs.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import QProgressDialog, QWidget

from ..core.errors import OperationCancelled
from ..core.jobs import run_job
from .errors import show_error

log = logging.getLogger(__name__)

# Tests may switch this off to run jobs in the worker thread instead.
USE_PROCESSES = True


class _Signals(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(object)


class JobRunnable(QRunnable):
    def __init__(self, target: str, kwargs: dict, cancel: threading.Event) -> None:
        super().__init__()
        self.target = target
        self.kwargs = kwargs
        self.cancel = cancel
        self.signals = _Signals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = run_job(
                self.target,
                self.kwargs,
                on_progress=lambda d, t, m: self.signals.progress.emit(d, t, m),
                cancel=self.cancel,
                in_process=USE_PROCESSES,
            )
        except BaseException as exc:  # forwarded to the GUI thread
            self.signals.failed.emit(exc)
        else:
            self.signals.finished.emit(result)


class Job(QObject):
    """A running background job with its progress dialog."""

    done = Signal(object)

    def __init__(
        self,
        parent: QWidget,
        title: str,
        target: str,
        kwargs: dict,
        on_success: Callable[[Any], None] | None = None,
        on_finally: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.parent_widget = parent
        self.cancel_event = threading.Event()
        self.on_success = on_success
        self.on_finally = on_finally
        self.result: Any = None
        self.error: BaseException | None = None
        self.finished = False
        self.dialog = QProgressDialog(title, "Cancel", 0, 0, parent)
        self.dialog.setWindowTitle(title)
        self.dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.dialog.setMinimumDuration(300)
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)
        self.dialog.canceled.connect(self._cancel)
        self.runnable = JobRunnable(target, kwargs, self.cancel_event)
        self.runnable.signals.progress.connect(self._on_progress)
        self.runnable.signals.finished.connect(self._on_finished)
        self.runnable.signals.failed.connect(self._on_failed)

    def start(self) -> "Job":
        self.dialog.setValue(0)
        QThreadPool.globalInstance().start(self.runnable)
        return self

    def _cancel(self) -> None:
        self.cancel_event.set()
        self.dialog.setLabelText("Cancelling…")

    def _on_progress(self, done: int, total: int, message: str) -> None:
        if self.cancel_event.is_set():
            return
        if total > 0:
            self.dialog.setMaximum(total)
            self.dialog.setValue(min(done, total))
        if message:
            self.dialog.setLabelText(message)

    def _close(self) -> None:
        self.finished = True
        self.dialog.reset()
        self.dialog.close()
        self.dialog.deleteLater()
        if self.on_finally is not None:
            self.on_finally()

    def _on_finished(self, result: Any) -> None:
        self.result = result
        self._close()
        try:
            if self.on_success is not None:
                self.on_success(result)
        except Exception as exc:
            show_error(exc, self.parent_widget)
        self.done.emit(result)

    def _on_failed(self, exc: BaseException) -> None:
        self.error = exc
        self._close()
        if not isinstance(exc, OperationCancelled):
            show_error(exc, self.parent_widget)
        self.done.emit(None)


def start_job(
    parent: QWidget,
    title: str,
    target: str,
    kwargs: dict,
    on_success: Callable[[Any], None] | None = None,
    on_finally: Callable[[], None] | None = None,
) -> Job:
    """Start ``target`` in the background; ``on_success(result)`` runs in the GUI thread."""
    return Job(parent, title, target, kwargs, on_success, on_finally).start()


def write_temp_copy(doc) -> str:
    """Write the document's current state to a temporary PDF for a job."""
    fd, path = tempfile.mkstemp(prefix="pdfedit-job-", suffix=".pdf")
    with os.fdopen(fd, "wb") as fh:
        fh.write(doc.snapshot())
    return path


def remove_quietly(path: str | None) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            log.warning("Could not remove temporary file %s", path)
