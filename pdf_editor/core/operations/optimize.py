"""File-size reduction with Low / Medium / High presets.

* image downsampling and JPEG recompression (``Document.rewrite_images``)
* font subsetting (``Document.subset_fonts``)
* garbage collection, stream deflation and object streams on save
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

import pymupdf

from ..errors import InvalidInput, OperationCancelled

Progress = Callable[[int, int, str], bool]


@dataclass(frozen=True)
class CompressionPreset:
    name: str
    description: str
    dpi_threshold: int | None  # only images above this resolution are downsampled
    dpi_target: int
    quality: int  # JPEG quality for recompressed images
    subset_fonts: bool


PRESETS: dict[str, CompressionPreset] = {
    "low": CompressionPreset("Low", "Best quality: lossless clean-up, images above 300 dpi reduced to 220 dpi",
                             300, 220, 90, False),
    "medium": CompressionPreset("Medium", "Balanced: images reduced to 150 dpi, JPEG quality 75, fonts subset",
                                200, 150, 75, True),
    "high": CompressionPreset("High", "Smallest file: images reduced to 96 dpi, JPEG quality 55, fonts subset",
                              120, 96, 55, True),
}

SAVE_OPTIONS = {"garbage": 4, "deflate": True, "deflate_images": True, "deflate_fonts": True,
                "clean": True, "use_objstms": 1}


@dataclass(frozen=True)
class CompressResult:
    path: str
    before: int
    after: int

    @property
    def saved_percent(self) -> float:
        return 0.0 if not self.before else max(0.0, (1 - self.after / self.before) * 100)


def get_preset(name: str) -> CompressionPreset:
    try:
        return PRESETS[name.lower()]
    except KeyError:
        raise InvalidInput(f"Unknown compression level '{name}'.") from None


def _tick(progress: Progress | None, done: int, total: int, message: str) -> None:
    if progress is not None and progress(done, total, message) is False:
        raise OperationCancelled()


def compress_document(doc: pymupdf.Document, preset: str, progress: Progress | None = None) -> None:
    """Downsample images and subset fonts of ``doc`` in place."""
    p = get_preset(preset)
    _tick(progress, 0, 3, "Optimizing images…")
    if p.dpi_threshold is not None:
        doc.rewrite_images(dpi_threshold=p.dpi_threshold, dpi_target=p.dpi_target, quality=p.quality,
                           lossy=True, lossless=True, bitonal=True, color=True, gray=True)
    _tick(progress, 1, 3, "Optimizing fonts…")
    if p.subset_fonts:
        try:
            doc.subset_fonts()
        except Exception:  # some fonts cannot be subset; keep them as they are
            pass
    _tick(progress, 2, 3, "Writing the file…")


def save_compressed(doc: pymupdf.Document, output: str, preset: str, before: int = 0,
                    progress: Progress | None = None) -> CompressResult:
    """Compress ``doc`` and save it to ``output``; reports sizes before/after."""
    compress_document(doc, preset, progress)
    doc.save(output, **SAVE_OPTIONS)
    _tick(progress, 3, 3, "Done")
    return CompressResult(output, before, os.path.getsize(output))


def compress_file(source: str, output: str, preset: str, password: str | None = None,
                  progress: Progress | None = None) -> CompressResult:
    """Compress the PDF at ``source`` into ``output`` (used by background jobs)."""
    if os.path.abspath(source) == os.path.abspath(output):
        raise InvalidInput("Choose a different file name for the compressed copy.")
    doc = pymupdf.open(source)
    try:
        if doc.needs_pass and not doc.authenticate(password or ""):
            raise InvalidInput("The document is password protected.")
        return save_compressed(doc, output, preset, os.path.getsize(source), progress)
    finally:
        doc.close()
