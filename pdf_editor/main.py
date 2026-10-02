"""Entry point: ``python -m pdf_editor [files...]`` or ``python pdf_editor/main.py``."""

from __future__ import annotations

import multiprocessing
import os
import sys

if __package__ in (None, ""):  # executed as a script: make the package importable
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv: list[str] | None = None) -> int:
    """Run the desktop application."""
    multiprocessing.freeze_support()  # background jobs use spawned processes
    from pdf_editor.app.application import run

    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
