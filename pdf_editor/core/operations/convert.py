"""Exports: pages as PNG/JPG images and extraction of embedded images.

(Plain-text export lives in :mod:`pdf_editor.core.operations.text`.)
"""

from __future__ import annotations

import os
from typing import Callable, Iterable

import pymupdf

from ..errors import InvalidInput, OperationCancelled
from ..utils import normalize_pages, safe_filename

Progress = Callable[[int, int, str], bool]
IMAGE_FORMATS = ("png", "jpg")


def _tick(progress: Progress | None, done: int, total: int, message: str) -> None:
    if progress is not None and progress(done, total, message) is False:
        raise OperationCancelled()


def export_page_images(
    doc: pymupdf.Document,
    pages: Iterable[int] | None,
    output_dir: str,
    base_name: str = "page",
    fmt: str = "png",
    dpi: int = 150,
    jpg_quality: int = 90,
    progress: Progress | None = None,
) -> list[str]:
    """Render pages to image files; returns the written paths."""
    fmt = fmt.lower().lstrip(".").replace("jpeg", "jpg")
    if fmt not in IMAGE_FORMATS:
        raise InvalidInput(f"Unsupported image format '{fmt}'. Use PNG or JPG.")
    if not 18 <= dpi <= 1200:
        raise InvalidInput("Choose a resolution between 18 and 1200 dpi.")
    indices = normalize_pages(pages, doc.page_count)
    os.makedirs(output_dir, exist_ok=True)
    base = safe_filename(base_name, "page")
    width = len(str(doc.page_count))
    written = []
    for i, pno in enumerate(indices):
        _tick(progress, i, len(indices), f"Rendering page {pno + 1}")
        pix = doc[pno].get_pixmap(dpi=dpi, alpha=False)
        path = os.path.join(output_dir, f"{base}_{pno + 1:0{width}d}.{fmt}")
        if fmt == "jpg":
            pix.save(path, jpg_quality=max(1, min(100, jpg_quality)))
        else:
            pix.save(path)
        written.append(path)
    _tick(progress, len(indices), len(indices), "Done")
    return written


def _image_pixmap(doc: pymupdf.Document, xref: int, smask: int) -> pymupdf.Pixmap:
    pix = pymupdf.Pixmap(doc, xref)
    if smask:
        mask = pymupdf.Pixmap(doc, smask)
        try:
            pix = pymupdf.Pixmap(pix, mask)
        except Exception:
            pass  # mask size mismatch: keep the image without transparency
    if pix.colorspace and pix.colorspace.n not in (1, 3):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    return pix


def extract_images(
    doc: pymupdf.Document,
    output_dir: str,
    base_name: str = "image",
    min_size: int = 0,
    progress: Progress | None = None,
) -> list[str]:
    """Save every distinct embedded image once; returns the written paths.

    JPEG/JPX images are written as-is (no recompression); others as PNG.
    Images smaller than ``min_size`` pixels on both sides are skipped.
    """
    os.makedirs(output_dir, exist_ok=True)
    base = safe_filename(base_name, "image")
    seen: set[int] = set()
    written: list[str] = []
    for pno in range(doc.page_count):
        _tick(progress, pno, doc.page_count, f"Scanning page {pno + 1}")
        for img in doc.get_page_images(pno, full=True):
            xref, smask, width, height = img[0], img[1], img[2], img[3]
            if xref in seen or (width < min_size and height < min_size):
                continue
            seen.add(xref)
            index = len(written) + 1
            info = doc.extract_image(xref)
            if not info:
                continue
            if info.get("ext") in ("jpeg", "jpg", "jpx") and not smask:
                ext = "jpg" if info["ext"] in ("jpeg", "jpg") else "jpx"
                path = os.path.join(output_dir, f"{base}_p{pno + 1}_{index}.{ext}")
                with open(path, "wb") as fh:
                    fh.write(info["image"])
            else:
                path = os.path.join(output_dir, f"{base}_p{pno + 1}_{index}.png")
                _image_pixmap(doc, xref, smask).save(path)
            written.append(path)
    _tick(progress, doc.page_count, doc.page_count, "Done")
    return written
