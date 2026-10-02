"""Undoable content edits: text, images, forms, signatures, watermarks, headers.

Mixed into ``PdfDocument``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Sequence

import pymupdf

from .. import objstate
from ..events import Change, ChangeEvent
from ..operations import forms as form_ops
from ..operations import images as image_ops
from ..operations import layout as layout_ops
from ..operations import textedit as text_ops
from ..utils import normalize_pages

if TYPE_CHECKING:  # pragma: no cover
    from ..document import PdfDocument


class ContentEditsMixin:
    """Edits that change page content (as opposed to annotations)."""

    # -- text ---------------------------------------------------------------------
    def add_text(self: "PdfDocument", pno: int, rect: Sequence[float], text: str, **style) -> pymupdf.Rect:
        """Write new text (family/bold/italic/fontfile/fontsize/color/align)."""
        return self.edit_pages("Add text", [pno], lambda: text_ops.add_text(self.raw[pno], rect, text, **style))

    def text_span_at(self: "PdfDocument", pno: int, point: Sequence[float]) -> text_ops.TextSpan | None:
        return text_ops.span_at(self.raw[pno], point)

    def preview_font(self: "PdfDocument", span: text_ops.TextSpan, text: str) -> text_ops.FontChoice:
        """Which font would be used to replace ``span`` with ``text`` (no change made)."""
        return text_ops.match_font(self.raw, self.raw[span.page], span, text)

    def replace_text(self: "PdfDocument", span: text_ops.TextSpan, new_text: str) -> text_ops.FontChoice:
        """Replace an existing text span; returns the font used (check ``.warning``)."""
        pno = span.page
        return self.edit_pages(
            "Edit text", [pno], lambda: text_ops.replace_span_text(self.raw, pno, span, new_text), deep=True
        )

    # -- images and signatures ---------------------------------------------------------
    def insert_image(self: "PdfDocument", pno: int, rect: Sequence[float], image: bytes,
                     label: str = "Insert image") -> int:
        """Place an image in the page content (pre-rotated to look upright)."""
        page_rotation = self.raw[pno].rotation
        data = image_ops.load_image_bytes(image)
        if page_rotation:
            data = image_ops.styled_image(data, 1.0, page_rotation)
        return self.edit_pages(label, [pno], lambda: image_ops.insert_image(self.raw[pno], rect, data))

    def place_signature(self: "PdfDocument", pno: int, rect: Sequence[float], png: bytes) -> int:
        """Place a signature image (transparent PNG) on the page."""
        return self.insert_image(pno, rect, png, label="Place signature")

    def page_images(self: "PdfDocument", pno: int) -> list[image_ops.PageImage]:
        return image_ops.page_images(self.raw[pno])

    def image_at(self: "PdfDocument", pno: int, point: Sequence[float]) -> image_ops.PageImage | None:
        return image_ops.image_at(self.raw[pno], point)

    def move_image(self: "PdfDocument", pno: int, image: image_ops.PageImage, rect: Sequence[float]) -> None:
        """Move/resize an image placement to ``rect`` (unrotated page coordinates)."""
        self.edit_pages("Move image", [pno], lambda: image_ops.move_image(
            self.raw[pno], image_ops.find_image(self.raw[pno], image.xref, image.bbox), rect))

    # -- forms ------------------------------------------------------------------------
    def form_fields(self: "PdfDocument", pages=None) -> list[form_ops.FieldInfo]:
        return form_ops.list_fields(self.raw, pages)

    def field_at(self: "PdfDocument", pno: int, point: Sequence[float]) -> form_ops.FieldInfo | None:
        return form_ops.field_at(self.raw[pno], point)

    def set_field_value(self: "PdfDocument", pno: int, xref: int, value: str | bool) -> None:
        """Fill a form field (one undo step; radio groups update together)."""
        pages = self._field_pages(pno, xref)
        self.edit_objects(
            "Fill form field",
            lambda: objstate.annot_object_xrefs(self.raw, xref),
            lambda: form_ops.set_field_value(self.raw, pno, xref, value),
            ChangeEvent(Change.FORMS, pages),
            permission=pymupdf.PDF_PERM_FORM,
        )

    def _field_pages(self: "PdfDocument", pno: int, xref: int) -> tuple[int, ...]:
        """Pages showing widgets of the same field (a radio group may span pages)."""
        page_of = {self.raw.page_xref(i): i for i in range(self.page_count)}
        pages = {pno}
        for x in objstate.annot_object_xrefs(self.raw, xref):
            kind, value = self.raw.xref_get_key(x, "P")
            if kind == "xref" and int(value.split()[0]) in page_of:
                pages.add(page_of[int(value.split()[0])])
        return tuple(sorted(pages))

    def flatten_forms(self: "PdfDocument") -> int:
        """Make all form fields part of the page content (snapshot undo)."""
        return self.edit_snapshot("Flatten form", lambda: form_ops.flatten_forms(self.raw))

    # -- watermarks, headers and footers ----------------------------------------------------
    def add_text_watermark(self: "PdfDocument", pages: Iterable[int] | None, text: str, **style) -> int:
        indices = normalize_pages(pages, self.page_count)
        return self.edit_pages("Add watermark", indices,
                               lambda: layout_ops.add_text_watermark(self.raw, indices, text, **style))

    def add_image_watermark(self: "PdfDocument", pages: Iterable[int] | None, image: bytes, **style) -> int:
        indices = normalize_pages(pages, self.page_count)
        return self.edit_pages("Add watermark", indices,
                               lambda: layout_ops.add_image_watermark(self.raw, indices, image, **style))

    def add_header_footer(self: "PdfDocument", pages: Iterable[int] | None, spec: layout_ops.HeaderFooter) -> int:
        indices = normalize_pages(pages, self.page_count)
        title = (self.raw.metadata or {}).get("title", "") or ""
        return self.edit_pages("Add header/footer", indices, lambda: layout_ops.add_header_footer(
            self.raw, indices, spec, filename=self.display_name, title=title))

    def add_page_numbers(self: "PdfDocument", pages: Iterable[int] | None, **options) -> int:
        indices = normalize_pages(pages, self.page_count)
        return self.edit_pages("Add page numbers", indices,
                               lambda: layout_ops.add_page_numbers(self.raw, indices, **options))
