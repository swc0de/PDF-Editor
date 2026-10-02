"""Adding new text and editing existing text spans.

Editing existing text works like this: the original span is removed with a
narrow *text-only* redaction (images and drawings are untouched) and the
new text is inserted at the same baseline with the closest available font,
size and colour. PDF text cannot be reflowed reliably, so the replacement
is a single line placed where the old span started.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Sequence

import pymupdf

from ..errors import InvalidInput, UnsupportedOperation
from ..utils import rgb_from_int

FAMILIES = {
    # family: (regular, bold, italic, bold-italic) base-14 names
    "Helvetica": ("helv", "hebo", "heit", "hebi"),
    "Times": ("tiro", "tibo", "tiit", "tibi"),
    "Courier": ("cour", "cobo", "coit", "cobi"),
}
FALLBACK_FONT = "china-s"  # built-in Droid Sans Fallback (wide Unicode coverage)
ALIGNMENTS = {"left": pymupdf.TEXT_ALIGN_LEFT, "center": pymupdf.TEXT_ALIGN_CENTER,
              "right": pymupdf.TEXT_ALIGN_RIGHT, "justify": pymupdf.TEXT_ALIGN_JUSTIFY}


@dataclass(frozen=True)
class TextSpan:
    """One run of text with uniform font, size and colour."""

    page: int
    bbox: pymupdf.Rect
    origin: pymupdf.Point
    text: str
    font: str
    size: float
    color: tuple[float, float, float]
    flags: int
    direction: tuple[float, float]

    @property
    def bold(self) -> bool:
        return bool(self.flags & pymupdf.TEXT_FONT_BOLD) or "bold" in self.font.lower()

    @property
    def italic(self) -> bool:
        name = self.font.lower()
        return bool(self.flags & pymupdf.TEXT_FONT_ITALIC) or "italic" in name or "oblique" in name

    @property
    def serif(self) -> bool:
        return bool(self.flags & pymupdf.TEXT_FONT_SERIFED)

    @property
    def mono(self) -> bool:
        return bool(self.flags & pymupdf.TEXT_FONT_MONOSPACED)


@dataclass(frozen=True)
class FontChoice:
    """The font used to write new text, and how well it matches the original."""

    fontname: str  # name to reference in the page resources
    buffer: bytes | None  # embedded font program to (re)insert, if any
    exact: bool
    description: str
    warning: str | None = None


def base14_name(family: str, bold: bool = False, italic: bool = False) -> str:
    """PyMuPDF base-14 font code for a family and style."""
    if family not in FAMILIES:
        raise InvalidInput(f"Unknown font family '{family}'.")
    return FAMILIES[family][(2 if italic else 0) + (1 if bold else 0)]


def text_spans(page: pymupdf.Page) -> list[TextSpan]:
    """All non-empty text spans of a page (unrotated coordinates)."""
    spans = []
    for block in page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)["blocks"]:
        for line in block.get("lines", []):
            for s in line["spans"]:
                if not s["text"].strip():
                    continue
                spans.append(TextSpan(
                    page.number, pymupdf.Rect(s["bbox"]), pymupdf.Point(s["origin"]), s["text"], s["font"],
                    float(s["size"]), rgb_from_int(s["color"]), int(s["flags"]), tuple(line["dir"]),
                ))
    return spans


def span_at(page: pymupdf.Page, point: Sequence[float]) -> TextSpan | None:
    """The text span under ``point`` (smallest one if several overlap)."""
    p = pymupdf.Point(point)
    hits = [s for s in text_spans(page) if s.bbox.contains(p)]
    return min(hits, key=lambda s: s.bbox.width * s.bbox.height) if hits else None


def _covers(font: pymupdf.Font, text: str) -> bool:
    return all(font.has_glyph(ord(ch)) for ch in text if not ch.isspace())


def _embedded_font(doc: pymupdf.Document, page: pymupdf.Page, span: TextSpan) -> tuple[bytes, str] | None:
    """The span's own embedded font program, if it can be extracted."""
    wanted = span.font.split("+", 1)[-1]
    for xref, ext, _type, basefont, _name, _enc, *_ in page.get_fonts(full=True):
        if basefont.split("+", 1)[-1] != wanted or ext in ("n/a", ""):
            continue
        try:
            _basename, _ext, _subtype, buffer = doc.extract_font(xref)
        except Exception:
            return None
        return (buffer, basefont) if buffer else None
    return None


def match_font(doc: pymupdf.Document, page: pymupdf.Page, span: TextSpan, text: str) -> FontChoice:
    """Find the closest usable font for writing ``text`` in place of ``span``."""
    embedded = _embedded_font(doc, page, span)
    if embedded is not None:
        buffer, basefont = embedded
        try:
            font = pymupdf.Font(fontbuffer=buffer)
            if _covers(font, text):
                return FontChoice("F_edit", buffer, True, f"original font {basefont.split('+', 1)[-1]}")
        except Exception:
            pass  # unusable font program: fall through to a standard font
    family = "Courier" if span.mono else "Times" if span.serif else "Helvetica"
    lowered = span.font.lower()
    if any(k in lowered for k in ("times", "georgia", "garamond", "serif", "roman")) and "sans" not in lowered:
        family = "Times"
    elif any(k in lowered for k in ("courier", "mono", "consol")):
        family = "Courier"
    elif any(k in lowered for k in ("helvetica", "arial", "sans")):
        family = "Helvetica"
    code = base14_name(family, span.bold, span.italic)
    standard = span.font.split("+", 1)[-1].replace("-", "").lower().startswith(("helvetica", "times", "courier"))
    if _covers(pymupdf.Font(code), text):
        warning = None if standard else (
            f"The original font '{span.font.split('+', 1)[-1]}' could not be reused "
            f"(it is not embedded or lacks some characters); {family} was used instead."
        )
        return FontChoice(code, None, standard, family, warning)
    return FontChoice(
        FALLBACK_FONT, None, False, "Droid Sans Fallback",
        "The text contains characters missing from the original font; a Unicode fallback font was used.",
    )


def _rotation_of(direction: tuple[float, float]) -> int:
    angle = round(math.degrees(math.atan2(-direction[1], direction[0]))) % 360
    if angle not in (0, 90, 180, 270):
        raise UnsupportedOperation("Text written at an angle cannot be edited reliably.")
    return angle


def replace_span_text(
    doc: pymupdf.Document, pno: int, span: TextSpan, new_text: str, font: FontChoice | None = None
) -> FontChoice:
    """Replace a span with ``new_text`` (same position, size and colour)."""
    page = doc[pno]
    rotate = _rotation_of(span.direction)
    choice = font or match_font(doc, page, span, new_text)
    # A thin band through the glyphs avoids removing text of neighbouring lines.
    size, origin, box = span.size, span.origin, span.bbox
    if rotate == 0:
        band = pymupdf.Rect(box.x0 + 0.3, origin.y - size * 0.45, box.x1 - 0.3, origin.y - size * 0.25)
    else:
        band = box + (size * 0.2, size * 0.2, -size * 0.2, -size * 0.2) if box.width > size * 0.5 else box
    page.add_redact_annot(band, fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    if new_text.strip():
        page = doc[pno]
        if choice.buffer is not None:
            page.insert_font(fontname=choice.fontname, fontbuffer=choice.buffer)
        page.insert_text(origin, new_text, fontsize=size, fontname=choice.fontname, color=span.color,
                         rotate=rotate)
    return choice


def text_box_height(text: str, fontname: str, fontsize: float, width: float, fontfile: str | None = None,
                    line_height: float = 1.2) -> float:
    """Height needed to set ``text`` in a box of ``width`` (word wrapped)."""
    font = pymupdf.Font(fontfile=fontfile) if fontfile else pymupdf.Font(fontname)
    lines = 0
    for paragraph in text.split("\n"):
        words, current = paragraph.split(" "), ""
        lines += 1
        for word in words:
            trial = f"{current} {word}".strip()
            if current and font.text_length(trial, fontsize) > width:
                lines += 1
                current = word
            else:
                current = trial
    return lines * fontsize * line_height + fontsize * 0.5


def add_text(
    page: pymupdf.Page,
    rect: Sequence[float],
    text: str,
    *,
    family: str = "Helvetica",
    bold: bool = False,
    italic: bool = False,
    fontfile: str | None = None,
    fontsize: float = 12,
    color: Sequence[float] = (0, 0, 0),
    align: str = "left",
) -> pymupdf.Rect:
    """Write new text into ``rect`` (grown downwards if needed); returns the box used."""
    if not text.strip():
        raise InvalidInput("There is no text to add.")
    if align not in ALIGNMENTS:
        raise InvalidInput(f"Unknown alignment '{align}'.")
    if fontfile and not os.path.isfile(fontfile):
        raise InvalidInput(f"The font file '{fontfile}' does not exist.")
    box = pymupdf.Rect(rect)
    # Lay the box out as displayed so text is upright and grows downwards on screen.
    visual = (box * page.rotation_matrix).normalize()
    if visual.width < fontsize:
        raise InvalidInput("The text area is too narrow.")
    if fontfile:
        fontname = "F_custom" + str(abs(hash(fontfile)) % 10000)
    else:
        fontname = base14_name(family, bold, italic)
        if not _covers(pymupdf.Font(fontname), text):
            fontname = FALLBACK_FONT
    needed = text_box_height(text, fontname if not fontfile else "", fontsize, visual.width, fontfile)
    visual.y1 = max(visual.y1, visual.y0 + needed)
    for _attempt in range(2):
        box = (visual * page.derotation_matrix).normalize()
        rc = page.insert_textbox(box, text, fontsize=fontsize, fontname=fontname, fontfile=fontfile,
                                 color=tuple(color), align=ALIGNMENTS[align], rotate=page.rotation)
        if rc >= 0:
            return box
        visual.y1 += -rc + fontsize  # did not fit (e.g. very long words): grow and retry
    raise InvalidInput("The text does not fit on the page.")
