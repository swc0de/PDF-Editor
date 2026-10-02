"""Undoable annotation edits (mixed into ``PdfDocument``).

Adding or deleting an annotation changes the page's ``/Annots`` array, so
those use page-level object capture. Restyling, moving or retexting one
annotation only touches that annotation's own objects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Sequence

import pymupdf

from ..events import Change
from ..operations import annotate as ops

if TYPE_CHECKING:  # pragma: no cover
    from ..document import PdfDocument

ANNOTATE = pymupdf.PDF_PERM_ANNOTATE


class AnnotationEditsMixin:
    """Add, modify and remove annotations."""

    def _add_annotation(self: "PdfDocument", label: str, pno: int, create: Callable[[pymupdf.Page], int]) -> int:
        return self.edit_pages(label, [pno], lambda: create(self.raw[pno]), kind=Change.ANNOTATIONS, permission=ANNOTATE)

    def add_text_markup(self: "PdfDocument", pno: int, kind: str, quads, color, opacity: float = 1.0,
                        author: str | None = None, text: str = "") -> int:
        return self._add_annotation(
            kind.capitalize(), pno, lambda p: ops.add_text_markup(p, kind, quads, color, opacity, author, text)
        )

    def add_ink(self: "PdfDocument", pno: int, strokes, color, width: float, opacity: float = 1.0,
                author: str | None = None) -> int:
        return self._add_annotation("Draw", pno, lambda p: ops.add_ink(p, strokes, color, width, opacity, author))

    def add_shape(self: "PdfDocument", pno: int, kind: str, start, end, stroke, fill=None, width: float = 2.0,
                  opacity: float = 1.0, author: str | None = None) -> int:
        return self._add_annotation(
            f"Add {kind}", pno, lambda p: ops.add_shape(p, kind, start, end, stroke, fill, width, opacity, author)
        )

    def add_sticky_note(self: "PdfDocument", pno: int, point, text: str, color, icon: str = "Note",
                        author: str | None = None) -> int:
        return self._add_annotation("Add note", pno, lambda p: ops.add_sticky_note(p, point, text, color, icon, author))

    def add_text_box(self: "PdfDocument", pno: int, rect, text: str, fontsize: float = 12, text_color=(0, 0, 0),
                     fill_color=None, border_width: float = 0, align: int = 0, author: str | None = None) -> int:
        return self._add_annotation(
            "Add text box", pno,
            lambda p: ops.add_text_box(p, rect, text, fontsize, text_color, fill_color, border_width, align,
                                       author=author),
        )

    def add_stamp(self: "PdfDocument", pno: int, rect, name: str, author: str | None = None) -> int:
        return self._add_annotation(f"Stamp {name}", pno, lambda p: ops.add_stamp(p, rect, name, author))

    def add_image_stamp(self: "PdfDocument", pno: int, rect, image: bytes, author: str | None = None) -> int:
        return self._add_annotation("Image stamp", pno, lambda p: ops.add_image_stamp(p, rect, image, author))

    def delete_annotation(self: "PdfDocument", pno: int, xref: int) -> None:
        self.edit_pages(
            "Delete annotation", [pno], lambda: ops.delete_annotation(self.raw[pno], xref),
            kind=Change.ANNOTATIONS, permission=ANNOTATE,
        )

    # -- modifications of a single annotation -----------------------------------------
    def set_annotation_rect(self: "PdfDocument", pno: int, xref: int, rect: Sequence[float],
                            label: str = "Move annotation") -> None:
        self.edit_annotation(label, pno, xref, lambda: ops.set_annotation_rect(self.raw[pno], xref, rect),
                             permission=ANNOTATE)

    def move_annotation(self: "PdfDocument", pno: int, xref: int, dx: float, dy: float) -> None:
        self.edit_annotation("Move annotation", pno, xref,
                             lambda: ops.move_annotation(self.raw[pno], xref, dx, dy), permission=ANNOTATE)

    def set_annotation_style(self: "PdfDocument", pno: int, xref: int, **style) -> None:
        self.edit_annotation("Change annotation style", pno, xref,
                             lambda: ops.set_annotation_style(self.raw[pno], xref, **style), permission=ANNOTATE)

    def set_annotation_contents(self: "PdfDocument", pno: int, xref: int, text: str) -> None:
        self.edit_annotation("Edit annotation text", pno, xref,
                             lambda: ops.set_annotation_contents(self.raw[pno], xref, text), permission=ANNOTATE)

    def update_annotation(self: "PdfDocument", pno: int, xref: int, contents: str | None = None, **style) -> None:
        """Change style and/or text of one annotation as a single undo step."""
        if contents is None and not style:
            return

        def apply() -> None:
            page = self.raw[pno]
            if style:
                ops.set_annotation_style(page, xref, **style)
            if contents is not None:
                ops.set_annotation_contents(self.raw[pno], xref, contents)

        self.edit_annotation("Edit annotation", pno, xref, apply, permission=ANNOTATE)

    # -- queries ---------------------------------------------------------------------
    def annotations(self: "PdfDocument", pages=None) -> list[ops.AnnotInfo]:
        return ops.list_annotations(self.raw, pages)

    def annotation_info(self: "PdfDocument", pno: int, xref: int) -> ops.AnnotInfo | None:
        page = self.raw[pno]
        for annot in page.annots():
            if annot.xref == xref:
                return ops.annotation_info(page, annot)
        return None
