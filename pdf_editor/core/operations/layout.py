"""Watermarks, headers, footers and page numbers.

All positions are computed on the page *as displayed* and converted to
unrotated page space, so the results look right on rotated pages too.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import pymupdf

from ..errors import InvalidInput
from ..utils import normalize_pages
from . import images as image_ops
from .textedit import FALLBACK_FONT, base14_name

POSITIONS = ("top-left", "top-center", "top-right", "bottom-left", "bottom-center", "bottom-right")
TOKENS = ("{page}", "{total}", "{date}", "{filename}", "{title}")


def _font_for(text: str, family: str, bold: bool = False) -> str:
    code = base14_name(family, bold)
    font = pymupdf.Font(code)
    if all(font.has_glyph(ord(c)) for c in text if not c.isspace()):
        return code
    return FALLBACK_FONT


def add_text_watermark(
    doc: pymupdf.Document,
    pages: Iterable[int] | None,
    text: str,
    *,
    fontsize: float = 60,
    color: Sequence[float] = (0.6, 0.6, 0.6),
    opacity: float = 0.3,
    rotation: float = 45,
    family: str = "Helvetica",
    bold: bool = True,
    overlay: bool = True,
) -> int:
    """Centred text watermark rotated by ``rotation`` degrees (counter-clockwise)."""
    if not text.strip():
        raise InvalidInput("Enter the watermark text.")
    if not 0 < opacity <= 1:
        raise InvalidInput("Opacity must be between 1% and 100%.")
    fontname = _font_for(text, family, bold)
    width = pymupdf.Font(fontname).text_length(text, fontsize)
    indices = normalize_pages(pages, doc.page_count)
    for pno in indices:
        page = doc[pno]
        pivot = pymupdf.Point(page.rect.width / 2, page.rect.height / 2) * page.derotation_matrix
        start = pymupdf.Point(pivot.x - width / 2, pivot.y + fontsize * 0.35)
        page.insert_text(
            start, text, fontsize=fontsize, fontname=fontname, color=tuple(color),
            fill_opacity=opacity, stroke_opacity=opacity, overlay=overlay,
            morph=(pivot, pymupdf.Matrix(rotation + page.rotation)),
        )
    return len(indices)


def add_image_watermark(
    doc: pymupdf.Document,
    pages: Iterable[int] | None,
    image: bytes,
    *,
    opacity: float = 0.3,
    rotation: float = 0,
    scale: float = 0.5,
    overlay: bool = True,
) -> int:
    """Centred image watermark; ``scale`` is the width relative to the page width."""
    if not 0 < scale <= 1:
        raise InvalidInput("The watermark size must be between 1% and 100% of the page width.")
    data = image_ops.load_image_bytes(image)
    indices = normalize_pages(pages, doc.page_count)
    prepared: dict[int, bytes] = {}
    for pno in indices:
        page = doc[pno]
        angle = rotation + page.rotation
        if angle not in prepared:
            prepared[angle] = image_ops.styled_image(data, opacity, angle)
        styled = prepared[angle]
        w_img, h_img = image_ops.image_size(styled)
        # Size the rectangle in unrotated space so that its *displayed* width is
        # scale * page width (90/270 degree pages show unrotated heights as widths).
        if page.rotation % 180 == 0:
            w_u = page.rect.width * scale
            h_u = w_u * h_img / w_img
        else:
            h_u = page.rect.width * scale
            w_u = h_u * w_img / h_img
        center = pymupdf.Point(page.rect.width / 2, page.rect.height / 2) * page.derotation_matrix
        target = pymupdf.Rect(center.x - w_u / 2, center.y - h_u / 2, center.x + w_u / 2, center.y + h_u / 2)
        page.insert_image(target, stream=styled, keep_proportion=True, overlay=overlay)
    return len(indices)


def format_template(template: str, page: int, total: int, filename: str = "", title: str = "",
                    date: _dt.date | None = None) -> str:
    """Fill ``{page}``, ``{total}``, ``{date}``, ``{filename}`` and ``{title}`` placeholders."""
    date = date or _dt.date.today()
    return (template.replace("{page}", str(page)).replace("{total}", str(total))
            .replace("{date}", date.isoformat()).replace("{filename}", filename).replace("{title}", title))


@dataclass
class HeaderFooter:
    """Texts for the six header/footer slots plus typography."""

    texts: dict[str, str] = field(default_factory=dict)  # position -> template
    fontsize: float = 10
    family: str = "Helvetica"
    color: Sequence[float] = (0, 0, 0)
    margin: float = 28  # points from the page edge
    start_number: int = 1

    def validate(self) -> None:
        unknown = set(self.texts) - set(POSITIONS)
        if unknown:
            raise InvalidInput(f"Unknown position(s): {', '.join(sorted(unknown))}")
        if not any(t.strip() for t in self.texts.values()):
            raise InvalidInput("Enter text for at least one header or footer position.")
        if self.fontsize <= 0 or self.margin < 0:
            raise InvalidInput("Font size must be positive and the margin cannot be negative.")


def add_header_footer(
    doc: pymupdf.Document, pages: Iterable[int] | None, spec: HeaderFooter, filename: str = "", title: str = ""
) -> int:
    """Stamp header/footer texts onto ``pages``; ``{page}`` counts the selected pages."""
    spec.validate()
    indices = normalize_pages(pages, doc.page_count)
    total = spec.start_number + len(indices) - 1
    aligns = {"left": pymupdf.TEXT_ALIGN_LEFT, "center": pymupdf.TEXT_ALIGN_CENTER, "right": pymupdf.TEXT_ALIGN_RIGHT}
    height = spec.fontsize * 2
    for i, pno in enumerate(indices):
        page = doc[pno]
        vis = page.rect
        for position, template in spec.texts.items():
            if not template.strip():
                continue
            text = format_template(template, spec.start_number + i, total, filename, title)
            vertical, horizontal = position.split("-")
            top = spec.margin if vertical == "top" else vis.height - spec.margin - height
            visual = pymupdf.Rect(spec.margin, top, vis.width - spec.margin, top + height)
            target = (visual * page.derotation_matrix).normalize()
            fontname = _font_for(text, spec.family)
            rc = page.insert_textbox(target, text, fontsize=spec.fontsize, fontname=fontname,
                                     color=tuple(spec.color), align=aligns[horizontal], rotate=page.rotation)
            if rc < 0:
                raise InvalidInput(f"The text '{text}' does not fit in the {position.replace('-', ' ')} area.")
    return len(indices)


def add_page_numbers(
    doc: pymupdf.Document,
    pages: Iterable[int] | None = None,
    template: str = "Page {page} of {total}",
    position: str = "bottom-center",
    fontsize: float = 10,
    margin: float = 28,
    start_number: int = 1,
    color: Sequence[float] = (0, 0, 0),
) -> int:
    """Number pages; ``template`` may use ``{page}`` and ``{total}``."""
    if position not in POSITIONS:
        raise InvalidInput(f"Unknown position '{position}'.")
    if "{page}" not in template:
        raise InvalidInput("The page number format must contain {page}.")
    spec = HeaderFooter({position: template}, fontsize, "Helvetica", color, margin, start_number)
    return add_header_footer(doc, pages, spec)
