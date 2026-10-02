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


def compress_task(source: str, output: str, preset: str, password: str | None = None,
                  original_size: int = 0, progress: Progress | None = None):
    """Compress ``source`` into ``output``; ``original_size`` is the size reported as "before"."""
    from .operations.optimize import CompressResult, compress_file

    result = compress_file(source, output, preset, password, progress)
    return CompressResult(result.path, original_size or result.before, result.after)


def ocr_task(source: str, output: str, pages: Sequence[int] | None, language: str, dpi: int,
             skip_text_pages: bool = True, password: str | None = None, progress: Progress | None = None):
    """OCR ``source`` and write the result to ``output`` keeping object numbers stable."""
    from .operations.ocr import ocr_document

    doc = open_source(source, password)
    try:
        result = ocr_document(doc, pages, language, dpi, skip_text_pages, progress=progress)
        # garbage=0 keeps existing xref numbers, so the GUI's undo history stays valid
        doc.save(output, garbage=0, encryption=pymupdf.PDF_ENCRYPT_KEEP)
        return result
    finally:
        doc.close()


def export_images_task(source: str, output_dir: str, pages: Sequence[int] | None, fmt: str, dpi: int,
                       base_name: str, jpg_quality: int = 90, password: str | None = None,
                       progress: Progress | None = None) -> list[str]:
    """Render pages to PNG/JPG files."""
    from .operations.convert import export_page_images

    doc = open_source(source, password)
    try:
        return export_page_images(doc, pages, output_dir, base_name, fmt, dpi, jpg_quality, progress)
    finally:
        doc.close()


def extract_images_task(source: str, output_dir: str, base_name: str, min_size: int = 0,
                        password: str | None = None, progress: Progress | None = None) -> list[str]:
    """Save all embedded images."""
    from .operations.convert import extract_images

    doc = open_source(source, password)
    try:
        return extract_images(doc, output_dir, base_name, min_size, progress)
    finally:
        doc.close()


def export_text_task(source: str, output: str, separators: bool = True, password: str | None = None,
                     progress: Progress | None = None) -> int:
    """Write all text to a .txt file; returns the number of characters."""
    from .operations.text import export_text

    doc = open_source(source, password)
    try:
        return export_text(doc, output, separators, progress)
    finally:
        doc.close()
