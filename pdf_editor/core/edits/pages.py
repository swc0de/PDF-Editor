"""Undoable page-management edits (mixed into ``PdfDocument``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Sequence

import pymupdf

from ..errors import InvalidInput
from ..events import Change, ChangeEvent
from ..operations import pages as ops
from ..utils import normalize_pages

if TYPE_CHECKING:  # pragma: no cover
    from ..document import PdfDocument

ASSEMBLE = pymupdf.PDF_PERM_ASSEMBLE


def _plural(n: int, word: str = "page") -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


class PageEditsMixin:
    """Rotate, delete, duplicate, insert, reorder and crop pages."""

    def rotate_pages(self: "PdfDocument", pages: Iterable[int], angle: int) -> None:
        """Rotate pages clockwise by ``angle`` degrees (multiple of 90)."""
        indices = normalize_pages(pages, self.page_count)
        self.edit_reversible(
            f"Rotate {_plural(len(indices))}",
            do=lambda: ops.rotate_pages(self.raw, indices, angle),
            undo=lambda: ops.rotate_pages(self.raw, indices, -angle),
            event=ChangeEvent(Change.STRUCTURE, tuple(indices)),
            permission=ASSEMBLE,
        )

    def delete_pages(self: "PdfDocument", pages: Iterable[int]) -> None:
        """Delete pages (snapshot undo: deletion also rewrites links/outline)."""
        indices = normalize_pages(pages, self.page_count)
        self.edit_snapshot(
            f"Delete {_plural(len(indices))}", lambda: ops.delete_pages(self.raw, indices), permission=ASSEMBLE
        )

    def duplicate_pages(self: "PdfDocument", pages: Iterable[int]) -> list[int]:
        """Duplicate pages; returns the indices of the copies."""
        indices = normalize_pages(pages, self.page_count)
        return self.edit_snapshot(
            f"Duplicate {_plural(len(indices))}",
            lambda: ops.duplicate_pages(self.raw, indices),
            permission=ASSEMBLE,
        )

    def insert_blank_page(self: "PdfDocument", index: int, width: float | None = None, height: float | None = None) -> int:
        """Insert a blank page before ``index``; returns its index."""
        return self.edit_snapshot(
            "Insert blank page", lambda: ops.insert_blank_page(self.raw, index, width, height), permission=ASSEMBLE
        )

    def move_pages(self: "PdfDocument", pages: Iterable[int], target: int) -> list[int]:
        """Move pages before ``target``; returns their new indices."""
        moving = normalize_pages(pages, self.page_count)
        order = ops.compute_move_order(self.page_count, moving, target)
        new_positions = [order.index(p) for p in moving]
        if order == list(range(self.page_count)):
            return new_positions
        inverse = ops.inverse_order(order)
        self.edit_reversible(
            f"Move {_plural(len(moving))}",
            do=lambda: ops.reorder_pages(self.raw, order),
            undo=lambda: ops.reorder_pages(self.raw, inverse),
            event=ChangeEvent(Change.STRUCTURE),
            permission=ASSEMBLE,
        )
        return new_positions

    def reorder_pages(self: "PdfDocument", order: Sequence[int]) -> None:
        """Apply a complete new page order (``order[i]`` = old index of new page i)."""
        order = list(order)
        if sorted(order) != list(range(self.page_count)):
            raise InvalidInput("The new page order must contain every page exactly once.")
        if order == list(range(self.page_count)):
            return
        inverse = ops.inverse_order(order)
        self.edit_reversible(
            "Reorder pages",
            do=lambda: ops.reorder_pages(self.raw, order),
            undo=lambda: ops.reorder_pages(self.raw, inverse),
            event=ChangeEvent(Change.STRUCTURE),
            permission=ASSEMBLE,
        )

    def insert_pdf(
        self: "PdfDocument",
        source: str | bytes,
        index: int,
        pages: Iterable[int] | None = None,
        password: str | None = None,
    ) -> int:
        """Insert pages from another PDF (path or bytes) before ``index``."""
        src = pymupdf.open(source) if isinstance(source, str) else pymupdf.open("pdf", source)
        try:
            if not src.is_pdf:
                converted = pymupdf.open("pdf", src.convert_to_pdf())
                src.close()
                src = converted
            if src.needs_pass and password:
                src.authenticate(password)
            wanted = None if pages is None else list(pages)
            return self.edit_snapshot(
                "Insert pages", lambda: ops.insert_pdf_pages(self.raw, src, index, wanted), permission=ASSEMBLE
            )
        finally:
            src.close()

    def insert_images(
        self: "PdfDocument",
        images: Sequence[str | bytes],
        index: int,
        page_size: tuple[float, float] | None = None,
        margin: float = 0,
    ) -> int:
        """Insert one page per image before ``index``; returns the count."""
        return self.edit_snapshot(
            f"Insert {_plural(len(images), 'image')} as pages",
            lambda: ops.insert_images_as_pages(self.raw, images, index, page_size, margin),
            permission=ASSEMBLE,
        )

    def crop_pages(self: "PdfDocument", pages: Iterable[int], rect: Sequence[float]) -> None:
        """Crop pages to ``rect`` (unrotated page coordinates)."""
        indices = normalize_pages(pages, self.page_count)
        self.edit_pages(
            f"Crop {_plural(len(indices))}",
            indices,
            lambda: ops.crop_pages(self.raw, indices, rect),
            kind=Change.STRUCTURE,
        )

    def crop_margins(
        self: "PdfDocument", pages: Iterable[int], left: float, top: float, right: float, bottom: float
    ) -> None:
        """Trim visual margins (points) from pages."""
        indices = normalize_pages(pages, self.page_count)
        self.edit_pages(
            f"Crop {_plural(len(indices))}",
            indices,
            lambda: ops.crop_margins(self.raw, indices, left, top, right, bottom),
            kind=Change.STRUCTURE,
        )

    def reset_crop(self: "PdfDocument", pages: Iterable[int]) -> None:
        """Undo any cropping of ``pages``."""
        indices = normalize_pages(pages, self.page_count)
        self.edit_pages(
            "Remove crop", indices, lambda: ops.reset_crop(self.raw, indices), kind=Change.STRUCTURE
        )

    def extract_pages_to(self: "PdfDocument", pages: Iterable[int], path: str) -> None:
        """Save ``pages`` (in the given order) as a new PDF at ``path``."""
        out = ops.extract_pages(self.raw, list(pages))
        try:
            out.save(path, garbage=3, deflate=True)
        finally:
            out.close()
