"""Entry point: ``python -m pdf_editor [files...]`` or ``python pdf_editor/main.py``.

This module must stay importable on old Python versions, so that people who
start the editor with one get a clear message instead of a traceback.
"""

from __future__ import annotations

import multiprocessing
import os
import sys

if __package__ in (None, ""):  # executed as a script: make the package importable
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MIN_PYTHON = (3, 11)


def python_version_problem(version: tuple[int, ...] | None = None) -> str | None:
    """Explain why ``version`` (default: the running Python) is too old, or return None."""
    version = tuple(sys.version_info[:3]) if version is None else tuple(version)
    if version[:2] >= MIN_PYTHON:
        return None
    needed = ".".join(map(str, MIN_PYTHON))
    found = ".".join(map(str, version[:3]))
    return (
        f"PDF Editor needs Python {needed} or newer, but it was started with Python {found}:\n"
        f"{sys.executable}\n\n"
        f"Install Python {needed} or newer from https://www.python.org/downloads/, then delete the "
        f".venv folder, create it again with the new Python (on Windows: py -{needed} -m venv .venv), "
        "activate it and run: pip install -r requirements.txt"
    )


def report_startup_problem(message: str) -> None:
    """Print ``message`` and, when Qt is importable, also show it in a dialog."""
    print(message, file=sys.stderr)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        _app = QApplication.instance() or QApplication(sys.argv[:1])  # kept while the dialog shows
        QMessageBox.critical(None, "PDF Editor cannot start", message)
    except Exception:  # no usable Qt: the console message has to do
        pass


def main(argv: list[str] | None = None) -> int:
    """Run the desktop application."""
    problem = python_version_problem()
    if problem is not None:
        report_startup_problem(problem)
        return 1
    multiprocessing.freeze_support()  # background jobs use spawned processes
    from pdf_editor.app.application import run

    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
