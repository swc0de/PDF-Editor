"""Creating, listing, moving, restyling and deleting real PDF annotations.

Everything here produces standard PDF annotations (Highlight, Ink, Square,
Circle, Line, Text, FreeText, Stamp...), so other viewers show them too.
Coordinates are unrotated page coordinates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import pymupdf

from ..errors import InvalidInput
from ..utils import hex_from_rgb, normalized_rect

RGB = Sequence[float]

MARKUP_KINDS = {
    "highlight": "add_highlight_annot",
    "underline": "add_underline_annot",
    "strikeout": "add_strikeout_annot",
    "squiggly": "add_squiggly_annot",
}

STAMPS: dict[str, int] = {
    "Approved": pymupdf.STAMP_Approved,
    "Draft": pymupdf.STAMP_Draft,
    "Confidential": pymupdf.STAMP_Confidential,
    "Final": pymupdf.STAMP_Final,
    "Not Approved": pymupdf.STAMP_NotApproved,
    "For Comment": pymupdf.STAMP_ForComment,
    "Experimental": pymupdf.STAMP_Experimental,
    "Expired": pymupdf.STAMP_Expired,
    "As Is": pymupdf.STAMP_AsIs,
    "Departmental": pymupdf.STAMP_Departmental,
    "For Public Release": pymupdf.STAMP_ForPublicRelease,
    "Not For Public Release": pymupdf.STAMP_NotForPublicRelease,
    "Sold": pymupdf.STAMP_Sold,
    "Top Secret": pymupdf.STAMP_TopSecret,
}

NOTE_ICONS = ("Note", "Comment", "Help", "Insert", "Key", "NewParagraph", "Paragraph")
VERTEX_KEYS = {"Ink": "InkList", "Line": "L", "PolyLine": "Vertices", "Polygon": "Vertices"}
_DA_COLOR = re.compile(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+rg")


@dataclass
class AnnotInfo:
    """A summary of one annotation for lists and property editors."""

    page: int
    xref: int
    kind: str
    rect: pymupdf.Rect
    contents: str = ""
    author: str = ""
    stroke: str | None = None
    fill: str | None = None
    text_color: str | None = None
    width: float = 0.0
    opacity: float = 1.0
    modified: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        """Short description, e.g. ``Highlight: "quick brown"``."""
        text = " ".join(self.contents.split())
        if len(text) > 60:
            text = text[:57] + "…"
        return f"{self.kind}: “{text}”" if text else self.kind


def _finish(annot: pymupdf.Annot, author: str | None = None, opacity: float | None = None) -> int:
    if author:
        annot.set_info(title=author)
    if opacity is not None and opacity < 1:
        annot.set_opacity(max(0.05, min(1.0, opacity)))
    annot.update()
    return annot.xref


def add_text_markup(
    page: pymupdf.Page,
    kind: str,
    quads: Sequence[pymupdf.Quad | pymupdf.Rect],
    color: RGB = (1, 0.92, 0.23),
    opacity: float = 1.0,
    author: str | None = None,
    text: str = "",
) -> int:
    """Highlight / underline / strikeout / squiggly over text quads."""
    if kind not in MARKUP_KINDS:
        raise InvalidInput(f"Unknown text markup '{kind}'.")
    quads = [q.quad if isinstance(q, pymupdf.Rect) else q for q in quads]
    if not quads:
        raise InvalidInput("Select some text first.")
    annot = getattr(page, MARKUP_KINDS[kind])(quads)
    annot.set_colors(stroke=color)
    if text:
        annot.set_info(content=text)
    return _finish(annot, author, opacity)


def add_ink(
    page: pymupdf.Page,
    strokes: Sequence[Sequence[Sequence[float]]],
    color: RGB = (0.9, 0.2, 0.2),
    width: float = 2.0,
    opacity: float = 1.0,
    author: str | None = None,
) -> int:
    """Freehand drawing; each stroke is a list of points."""
    clean = [[tuple(p) for p in stroke] for stroke in strokes if len(stroke) >= 2]
    if not clean:
        raise InvalidInput("A drawing needs at least two points.")
    annot = page.add_ink_annot(clean)
    annot.set_colors(stroke=color)
    annot.set_border(width=max(0.1, width))
    return _finish(annot, author, opacity)


def add_shape(
    page: pymupdf.Page,
    kind: str,
    start: Sequence[float],
    end: Sequence[float],
    stroke: RGB = (0.9, 0.2, 0.2),
    fill: RGB | None = None,
    width: float = 2.0,
    opacity: float = 1.0,
    author: str | None = None,
) -> int:
    """Rectangle, ellipse, line or arrow between two points."""
    if kind in ("rect", "ellipse"):
        rect = normalized_rect(start[0], start[1], end[0], end[1])
        if rect.width < 1 or rect.height < 1:
            raise InvalidInput("The shape is too small.")
        annot = page.add_rect_annot(rect) if kind == "rect" else page.add_circle_annot(rect)
        annot.set_colors(stroke=stroke, fill=fill if fill else None)
    elif kind in ("line", "arrow"):
        if pymupdf.Point(start) == pymupdf.Point(end):
            raise InvalidInput("A line needs two different points.")
        annot = page.add_line_annot(start, end)
        annot.set_colors(stroke=stroke)
        if kind == "arrow":
            annot.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, pymupdf.PDF_ANNOT_LE_CLOSED_ARROW)
            annot.set_colors(stroke=stroke, fill=stroke)
    else:
        raise InvalidInput(f"Unknown shape '{kind}'.")
    annot.set_border(width=max(0.1, width))
    return _finish(annot, author, opacity)


def add_sticky_note(
    page: pymupdf.Page,
    point: Sequence[float],
    text: str,
    color: RGB = (1, 0.85, 0.1),
    icon: str = "Note",
    author: str | None = None,
) -> int:
    """A sticky note (Text annotation) with a pop-up comment."""
    if icon not in NOTE_ICONS:
        raise InvalidInput(f"Unknown note icon '{icon}'.")
    annot = page.add_text_annot(point, text, icon=icon)
    annot.set_colors(stroke=color)
    return _finish(annot, author)


def add_text_box(
    page: pymupdf.Page,
    rect: Sequence[float],
    text: str,
    fontsize: float = 12,
    text_color: RGB = (0, 0, 0),
    fill_color: RGB | None = None,
    border_width: float = 0,
    align: int = pymupdf.TEXT_ALIGN_LEFT,
    font: str = "Helv",
    author: str | None = None,
) -> int:
    """A text box (FreeText annotation)."""
    box = pymupdf.Rect(rect)
    if box.is_empty or box.width < 4 or box.height < 4:
        raise InvalidInput("The text box is too small.")
    if not text.strip():
        raise InvalidInput("The text box is empty.")
    annot = page.add_freetext_annot(
        box, text, fontsize=fontsize, fontname=font, text_color=text_color,
        fill_color=fill_color, border_width=border_width, align=align,
    )
    return _finish(annot, author)


def add_stamp(page: pymupdf.Page, rect: Sequence[float], name: str, author: str | None = None) -> int:
    """A standard rubber stamp such as Approved, Draft or Confidential."""
    if name not in STAMPS:
        raise InvalidInput(f"Unknown stamp '{name}'.")
    annot = page.add_stamp_annot(pymupdf.Rect(rect), stamp=STAMPS[name])
    return _finish(annot, author)


def add_image_stamp(page: pymupdf.Page, rect: Sequence[float], image: bytes, author: str | None = None) -> int:
    """A custom stamp showing an image (kept inside ``rect``, aspect preserved)."""
    if not image:
        raise InvalidInput("No image was given for the stamp.")
    try:
        pymupdf.Pixmap(image)  # validate before touching the page
    except Exception as exc:
        raise InvalidInput("The stamp image could not be read.") from exc
    annot = page.add_stamp_annot(pymupdf.Rect(rect), stamp=image)
    return _finish(annot, author)


def _text_color(doc: pymupdf.Document, xref: int) -> str | None:
    kind, value = doc.xref_get_key(xref, "DA")
    match = _DA_COLOR.search(value) if kind == "string" else None
    return hex_from_rgb([float(v) for v in match.groups()]) if match else None


def annotation_info(page: pymupdf.Page, annot: pymupdf.Annot) -> AnnotInfo:
    """Describe one annotation."""
    info = annot.info
    colors = annot.colors or {}
    border = annot.border or {}
    kind = annot.type[1]
    result = AnnotInfo(
        page=page.number,
        xref=annot.xref,
        kind=kind,
        rect=pymupdf.Rect(annot.rect),
        contents=info.get("content", "") or "",
        author=info.get("title", "") or "",
        stroke=hex_from_rgb(colors.get("stroke")),
        fill=hex_from_rgb(colors.get("fill")),
        width=float(border.get("width") or 0),
        opacity=annot.opacity if annot.opacity is not None and annot.opacity >= 0 else 1.0,
        modified=info.get("modDate", "") or "",
    )
    if kind == "FreeText":
        result.fill, result.stroke = result.stroke, None  # /C is the background of a text box
        result.text_color = _text_color(page.parent, annot.xref)
    return result


def list_annotations(doc: pymupdf.Document, pages: Iterable[int] | None = None) -> list[AnnotInfo]:
    """All annotations (form widgets and pop-ups excluded) in page order."""
    result: list[AnnotInfo] = []
    for pno in range(doc.page_count) if pages is None else pages:
        page = doc[pno]
        for annot in page.annots():
            if annot.type[0] == pymupdf.PDF_ANNOT_POPUP:
                continue
            result.append(annotation_info(page, annot))
    return result


def _load(page: pymupdf.Page, xref: int) -> pymupdf.Annot:
    if xref not in [x for x, *_ in page.annot_xrefs()]:
        raise InvalidInput("That annotation no longer exists.")
    return page.load_annot(xref)


def annot_at(page: pymupdf.Page, point: Sequence[float], tolerance: float = 3.0) -> int | None:
    """xref of the top-most annotation under ``point`` (widgets excluded)."""
    p = pymupdf.Point(point)
    hit = None
    for annot in page.annots():
        if annot.type[0] == pymupdf.PDF_ANNOT_POPUP:
            continue
        if (annot.rect + (-tolerance, -tolerance, tolerance, tolerance)).contains(p):
            hit = annot.xref  # later annotations are drawn on top
    return hit


def set_annotation_rect(page: pymupdf.Page, xref: int, rect: Sequence[float]) -> None:
    """Move and/or resize an annotation so it occupies ``rect``."""
    annot = _load(page, xref)
    new = pymupdf.Rect(rect)
    if new.is_empty or new.width < 1 or new.height < 1:
        raise InvalidInput("The annotation would become too small.")
    kind = annot.type[1]
    if kind in VERTEX_KEYS:
        old = annot.rect
        sx = new.width / old.width if old.width else 1
        sy = new.height / old.height if old.height else 1
        to_pdf = ~page.transformation_matrix

        def convert(pt) -> str:
            q = pymupdf.Point((pt[0] - old.x0) * sx + new.x0, (pt[1] - old.y0) * sy + new.y0) * to_pdf
            return f"{q.x:g} {q.y:g}"

        vertices = annot.vertices or []
        if kind == "Ink":
            value = "[" + "".join("[" + " ".join(convert(p) for p in stroke) + "]" for stroke in vertices) + "]"
        else:
            value = "[" + " ".join(convert(p) for p in vertices) + "]"
        page.parent.xref_set_key(xref, VERTEX_KEYS[kind], value)
        annot = page.load_annot(xref)
        annot.update()
        return
    annot.set_rect(new)
    annot.update()
    # MuPDF may grow /Rect by the border margin (/RD) when regenerating the
    # appearance; compensate once so repeated moves do not drift or grow.
    got = page.load_annot(xref).rect
    if max(abs(got.x0 - new.x0), abs(got.y0 - new.y0), abs(got.x1 - new.x1), abs(got.y1 - new.y1)) > 0.01:
        adjusted = pymupdf.Rect(2 * new.x0 - got.x0, 2 * new.y0 - got.y0, 2 * new.x1 - got.x1, 2 * new.y1 - got.y1)
        if not adjusted.is_empty:
            annot = page.load_annot(xref)
            annot.set_rect(adjusted)
            annot.update()


def move_annotation(page: pymupdf.Page, xref: int, dx: float, dy: float) -> None:
    """Shift an annotation by ``(dx, dy)`` points."""
    annot = _load(page, xref)
    set_annotation_rect(page, xref, annot.rect + (dx, dy, dx, dy))


def set_annotation_style(
    page: pymupdf.Page,
    xref: int,
    *,
    stroke: RGB | None = None,
    fill: RGB | None | bool = None,
    width: float | None = None,
    opacity: float | None = None,
) -> None:
    """Change colours, line width and/or opacity. ``fill=False`` removes the fill."""
    annot = _load(page, xref)
    kind = annot.type[1]
    if kind == "FreeText":
        kwargs = {}
        if stroke is not None:
            kwargs["text_color"] = tuple(stroke)
        if fill is not None:
            kwargs["fill_color"] = None if fill is False else tuple(fill)  # type: ignore[arg-type]
        if width is not None:
            annot.set_border(width=max(0.0, width))
        if opacity is not None:
            annot.set_opacity(max(0.05, min(1.0, opacity)))
        annot.update(**kwargs)
        return
    # set_colors leaves a colour unchanged when given None; [] removes it.
    new_fill = None if fill is None else ([] if fill is False else list(fill))  # type: ignore[arg-type]
    annot.set_colors(stroke=list(stroke) if stroke is not None else None, fill=new_fill)
    if width is not None and kind not in ("Highlight", "Underline", "StrikeOut", "Squiggly", "Text", "Stamp"):
        annot.set_border(width=max(0.1, width))
    if opacity is not None:
        annot.set_opacity(max(0.05, min(1.0, opacity)))
    annot.update()


def set_annotation_contents(page: pymupdf.Page, xref: int, text: str) -> None:
    """Change the comment text (or the visible text of a text box)."""
    annot = _load(page, xref)
    annot.set_info(content=text)
    annot.update()


def delete_annotation(page: pymupdf.Page, xref: int) -> None:
    """Remove an annotation (and its pop-up)."""
    page.delete_annot(_load(page, xref))
