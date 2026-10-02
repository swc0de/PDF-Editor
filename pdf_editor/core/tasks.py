"""File-based job entry points run in a child process by :mod:`pdf_editor.core.jobs`.

Every function takes plain, picklable arguments (paths, numbers, lists),
opens its own documents and reports progress through ``progress``.
The GUI writes the current (possibly unsaved) document to a temporary
file before starting a job, so the child never touches the GUI's document.
"""

from __future__ import annotations

import os
from typing import Callable, Sequence

import pymupdf

from .errors import InvalidInput, PasswordRequired
from .operations import pages as page_ops

Progress = Callable[[int, int, str], bool]


def open_source(path: str, password: str | None = None) -> pymupdf.Document:
    """Open (and unlock) a PDF for a job."""
    doc = pymupdf.open(path)
    if doc.needs_pass and not doc.authenticate(password or ""):
        doc.close()
        raise PasswordRequired(f"'{os.path.basename(path)}' needs a password.")
    return doc


def merge_task(
    paths: Sequence[str], output: str, passwords: dict[str, str] | None = None, progress: Progress | None = None
) -> dict:
    """Merge PDFs into ``output``; returns ``{"path", "pages"}``."""
    count = page_ops.merge_files(list(paths), output, passwords, progress)
    return {"path": output, "pages": count}


def split_task(
    source: str,
    groups: Sequence[Sequence[int]],
    output_dir: str,
    base_name: str,
    password: str | None = None,
    progress: Progress | None = None,
) -> list[str]:
    """Split ``source`` into one file per page group; returns the written paths."""
    doc = open_source(source, password)
    try:
        for group in groups:
            for pno in group:
                if not 0 <= pno < doc.page_count:
                    raise InvalidInput(f"Page {pno + 1} does not exist.")
        return page_ops.split_document(doc, [list(g) for g in groups], output_dir, base_name, progress)
    finally:
        doc.close()
