"""True redaction: mark areas or search hits, review, then remove content for good.

Marks are standard ``Redact`` annotations (other PDF tools show them as
pending redactions). Applying them deletes the text underneath, blanks
the covered image pixels and removes covered vector graphics. The file must
then be saved with a full rewrite (never incrementally), otherwise the old
content would still be inside the file - ``PdfDocument`` enforces that.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import pymupdf

from ..errors import InvalidInput
from ..utils import normalize_pages
from . import text as text_ops
from .annotate import AnnotInfo, annotation_info

DEFAULT_FILL = (0.0, 0.0, 0.0)


def mark_area(page: pymupdf.Page, rect: Sequence[float], fill: Sequence[float] = DEFAULT_FILL,
              label: str = "") -> int:
    """Mark a rectangle for redaction; returns the mark's xref."""
    bounds = (page.rect * page.derotation_matrix).normalize()  # whole page, unrotated
    box = pymupdf.Rect(rect) & bounds
    if box.is_empty or box.width < 1 or box.height < 1:
        raise InvalidInput("The redaction area is empty.")
    annot = page.add_redact_annot(box, fill=tuple(fill), cross_out=True)
    if label:
        annot.set_info(content=label)
        annot.update()
    return annot.xref


def find_text_marks(doc: pymupdf.Document, needle: str, match_case: bool = False,
                    pages: Iterable[int] | None = None) -> dict[int, list[pymupdf.Rect]]:
    """Rectangles (per page) covering every occurrence of ``needle``."""
    if not needle.strip():
        raise InvalidInput("Enter the text to redact.")
    found: dict[int, list[pymupdf.Rect]] = {}
    for pno in normalize_pages(pages, doc.page_count):
        rects = [r for hit in text_ops.search_page(doc[pno], needle, match_case) for r in hit.rects]
        if rects:
            found[pno] = rects
    return found


def mark_text(doc: pymupdf.Document, needle: str, match_case: bool = False,
              pages: Iterable[int] | None = None, fill: Sequence[float] = DEFAULT_FILL) -> list[tuple[int, int]]:
    """Mark every occurrence of ``needle``; returns ``[(page, xref), ...]``."""
    marks = []
    for pno, rects in find_text_marks(doc, needle, match_case, pages).items():
        page = doc[pno]
        for rect in rects:
            marks.append((pno, mark_area(page, rect, fill, label=needle)))
    return marks


def list_marks(doc: pymupdf.Document) -> list[AnnotInfo]:
    """All pending redaction marks in page order."""
    marks = []
    for pno in range(doc.page_count):
        page = doc[pno]
        for annot in page.annots(types=[pymupdf.PDF_ANNOT_REDACT]):
            marks.append(annotation_info(page, annot))
    return marks


def pages_with_marks(doc: pymupdf.Document) -> list[int]:
    return sorted({m.page for m in list_marks(doc)})


def apply_redactions(doc: pymupdf.Document, pages: Iterable[int] | None = None) -> int:
    """Permanently remove everything under the marks; returns the number of pages changed."""
    targets = pages_with_marks(doc) if pages is None else normalize_pages(pages, doc.page_count)
    changed = 0
    for pno in targets:
        page = doc[pno]
        if not list(page.annots(types=[pymupdf.PDF_ANNOT_REDACT])):
            continue
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
            graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )
        changed += 1
    return changed


def scrub_hidden_data(doc: pymupdf.Document) -> None:
    """Remove metadata, JavaScript, attachments, hidden text and thumbnails."""
    doc.scrub(attached_files=True, clean_pages=True, embedded_files=True, hidden_text=True,
              javascript=True, metadata=True, redactions=False, remove_links=False,
              reset_fields=False, reset_responses=True, thumbnails=True, xml_metadata=True)
