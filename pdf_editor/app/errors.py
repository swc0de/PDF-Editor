"""Friendly error dialogs and file logging.

Expected problems (:class:`~pdf_editor.core.errors.PdfEditorError`) are
shown as plain messages. Anything unexpected is logged with its traceback
and shown as a short apology with an expandable "Details" section - the
user never sees a raw traceback dialog or a crash.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import traceback
from types import TracebackType

from PySide6.QtCore import QtMsgType, QStandardPaths, qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from ..core.errors import OperationCancelled, PdfEditorError

log = logging.getLogger("pdf_editor")
_log_path: str | None = None


def log_file_path() -> str:
    """Where the log file lives (created on first use)."""
    global _log_path
    if _log_path is None:
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        folder = os.path.join(base or os.path.expanduser("~"), "logs")
        os.makedirs(folder, exist_ok=True)
        _log_path = os.path.join(folder, "pdf_editor.log")
    return _log_path


def setup_logging(level: int = logging.INFO) -> str:
    """Log to a rotating file (and stderr); returns the log file path."""
    path = log_file_path()
    root = logging.getLogger("pdf_editor")
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
        stream = logging.StreamHandler()
        stream.setLevel(logging.WARNING)
        root.addHandler(stream)
    root.setLevel(level)
    qInstallMessageHandler(_qt_message_handler)
    return path


_QT_NOISE = ("propagateSizeHints", "QFont::setPointSize", "Unknown property")


def _qt_message_handler(kind: QtMsgType, _context, message: str) -> None:
    """Send Qt's own warnings to the log file instead of the console."""
    if any(noise in message for noise in _QT_NOISE):
        return
    if kind in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
        log.error("Qt: %s", message)
    elif kind == QtMsgType.QtWarningMsg:
        log.warning("Qt: %s", message)
    else:
        log.debug("Qt: %s", message)


def _parent() -> QWidget | None:
    app = QApplication.instance()
    return app.activeWindow() if app is not None else None  # type: ignore[union-attr]


def show_error(exc: BaseException, parent: QWidget | None = None, title: str | None = None) -> None:
    """Show ``exc`` to the user in a friendly way and log it."""
    if isinstance(exc, OperationCancelled):
        return
    parent = parent or _parent()
    box = QMessageBox(parent)
    if isinstance(exc, PdfEditorError):
        log.info("%s: %s", type(exc).__name__, exc.message)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title or exc.title)
        box.setText(exc.message)
        if exc.details:
            box.setDetailedText(exc.details)
    else:
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        log.error("Unexpected error:\n%s", details)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(title or "Something went wrong")
        box.setText(
            "Sorry, an unexpected error occurred. Your document has not been changed by the failed action.\n\n"
            f"{type(exc).__name__}: {exc}"
        )
        box.setInformativeText(f"Details were written to the log file:\n{log_file_path()}")
        box.setDetailedText(details)
    box.exec()


def show_warning(parent: QWidget | None, title: str, message: str) -> None:
    QMessageBox.warning(parent or _parent(), title, message)


def show_info(parent: QWidget | None, title: str, message: str) -> None:
    QMessageBox.information(parent or _parent(), title, message)


_in_hook = False


def _excepthook(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
    global _in_hook
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    log.error("Uncaught exception", exc_info=(exc_type, exc, tb))
    if _in_hook or QApplication.instance() is None:
        return
    _in_hook = True
    try:
        show_error(exc)
    finally:
        _in_hook = False


def install_excepthook() -> None:
    """Route uncaught exceptions (including those in Qt slots) to dialogs."""
    sys.excepthook = _excepthook


class guarded:
    """Context manager that shows errors from a block instead of propagating them.

    Example::

        with guarded(self):
            doc.rotate_pages(pages, 90)
    """

    def __init__(self, parent: QWidget | None = None, title: str | None = None) -> None:
        self.parent = parent
        self.title = title
        self.failed = False

    def __enter__(self) -> "guarded":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is None:
            return False
        if isinstance(exc, Exception):
            self.failed = True
            show_error(exc, self.parent, self.title)
            return True
        return False
