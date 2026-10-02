"""Run slow operations in a child process with progress and cancellation.

PyMuPDF holds the GIL during long calls (rendering, OCR, image rewriting),
so a plain worker thread would still freeze the GUI. The GUI therefore runs
jobs from a ``QThreadPool`` worker that calls :func:`run_job`, which starts
a *process*, relays its progress, and can stop it on request. Jobs work on
files, so the child never shares a PyMuPDF document with the GUI.

A job target is a ``"module:function"`` string. The function receives the
given keyword arguments plus ``progress(done, total, message) -> bool``;
returning ``False`` from ``progress`` means "please cancel".
"""

from __future__ import annotations

import importlib
import multiprocessing
import queue as queue_module
import threading
import time
import traceback
from typing import Any, Callable

from . import errors
from .errors import JobFailed, OperationCancelled, PdfEditorError

ProgressCallback = Callable[[int, int, str], None]

CANCEL_GRACE_SECONDS = 3.0


def resolve_target(target: str) -> Callable[..., Any]:
    """Import ``"package.module:function"``."""
    module_name, _, func_name = target.partition(":")
    if not module_name or not func_name:
        raise ValueError(f"Invalid job target '{target}'")
    return getattr(importlib.import_module(module_name), func_name)


def _child_main(target: str, kwargs: dict, messages: Any, cancel: Any) -> None:
    """Entry point of the job process."""

    def progress(done: int, total: int, message: str = "") -> bool:
        messages.put(("progress", done, total, message))
        return not cancel.is_set()

    try:
        result = resolve_target(target)(**kwargs, progress=progress)
        messages.put(("result", result))
    except OperationCancelled:
        messages.put(("cancelled",))
    except PdfEditorError as exc:
        messages.put(("error", type(exc).__name__, exc.message, exc.details))
    except BaseException as exc:  # report everything; never die silently
        messages.put(("crash", f"{type(exc).__name__}: {exc}", traceback.format_exc()))


def _raise_error(name: str, message: str, details: str | None) -> None:
    cls = getattr(errors, name, None)
    if isinstance(cls, type) and issubclass(cls, PdfEditorError):
        if cls is OperationCancelled:
            raise OperationCancelled(message)
        raise cls(message, details=details)
    raise JobFailed(message, details=details)


def run_job(
    target: str,
    kwargs: dict,
    *,
    on_progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
    in_process: bool = True,
    poll_interval: float = 0.05,
) -> Any:
    """Run ``target(**kwargs, progress=...)`` and return its result.

    With ``in_process=False`` the function runs in the calling thread (used
    by tests and as a fallback). Raises :class:`OperationCancelled` when
    ``cancel`` is set, or the job's own error type if it failed.
    """
    cancel = cancel or threading.Event()
    if not in_process:
        return _run_inline(target, kwargs, on_progress, cancel)

    ctx = multiprocessing.get_context("spawn")
    messages = ctx.Queue()
    child_cancel = ctx.Event()
    proc = ctx.Process(target=_child_main, args=(target, kwargs, messages, child_cancel), daemon=True)
    proc.start()
    deadline: float | None = None
    try:
        while True:
            if cancel.is_set() and deadline is None:
                child_cancel.set()
                deadline = time.monotonic() + CANCEL_GRACE_SECONDS
            if deadline is not None and time.monotonic() > deadline:
                proc.terminate()
                raise OperationCancelled()
            try:
                msg = messages.get(timeout=poll_interval)
            except queue_module.Empty:
                if not proc.is_alive():
                    # The child may have exited right after posting its last message.
                    try:
                        msg = messages.get(timeout=0.5)
                    except queue_module.Empty:
                        raise JobFailed(
                            f"The background process stopped unexpectedly (exit code {proc.exitcode})."
                        ) from None
                else:
                    continue
            kind = msg[0]
            if kind == "progress":
                if on_progress is not None:
                    on_progress(msg[1], msg[2], msg[3])
            elif kind == "result":
                return msg[1]
            elif kind == "cancelled":
                raise OperationCancelled()
            elif kind == "error":
                _raise_error(msg[1], msg[2], msg[3])
            elif kind == "crash":
                raise JobFailed(f"The operation failed: {msg[1]}", details=msg[2])
    finally:
        proc.join(timeout=1.0)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=1.0)
        messages.close()


def _run_inline(target: str, kwargs: dict, on_progress: ProgressCallback | None, cancel: threading.Event) -> Any:
    def progress(done: int, total: int, message: str = "") -> bool:
        if on_progress is not None:
            on_progress(done, total, message)
        return not cancel.is_set()

    try:
        return resolve_target(target)(**kwargs, progress=progress)
    except PdfEditorError:
        raise
    except Exception as exc:
        raise JobFailed(f"The operation failed: {type(exc).__name__}: {exc}", details=traceback.format_exc()) from exc
