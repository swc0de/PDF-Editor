"""Text extraction, search and reading-order selection.

Coordinates are unrotated page coordinates (the space PyMuPDF uses for
text extraction and annotations).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import pymupdf

from ..errors import InvalidInput, OperationCancelled
from ..utils import normalize_pages

Progress = Callable[[int, int, str], bool]

# Extraction flags: like RAWDICT but without image blocks (much faster).
CHAR_FLAGS = pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES


@dataclass(frozen=True)
class CharBox:
    """One character with its bounding box and the line it belongs to."""

    char: str
    rect: pymupdf.Rect
    line: int


@dataclass(frozen=True)
class TextSelection:
    """Selected text plus one rectangle per touched line (for highlighting)."""

    text: str
    rects: tuple[pymupdf.Rect, ...]

    @property
    def quads(self) -> list[pymupdf.Quad]:
        return [r.quad for r in self.rects]

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


def page_chars(page: pymupdf.Page) -> list[CharBox]:
    """All characters of a page in reading (content) order."""
    chars: list[CharBox] = []
    line_no = 0
    raw = page.get_text("rawdict", flags=CHAR_FLAGS)
    for block in raw["blocks"]:
        if block.get("type", 0) != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                for ch in span["chars"]:
                    rect = pymupdf.Rect(ch["bbox"])
                    if rect.is_empty and ch["c"].isspace():
                        rect = pymupdf.Rect(rect.x0, rect.y0, rect.x0 + 0.1, rect.y1 + 0.1)
                    chars.append(CharBox(ch["c"], rect, line_no))
            line_no += 1
    return chars


def nearest_char(chars: Sequence[CharBox], point: Sequence[float]) -> int | None:
    """Index of the character closest to ``point`` (vertical distance weighs more)."""
    if not chars:
        return None
    p = pymupdf.Point(point)
    best, best_score = None, float("inf")
    for i, ch in enumerate(chars):
        r = ch.rect
        dx = max(r.x0 - p.x, 0.0, p.x - r.x1)
        dy = max(r.y0 - p.y, 0.0, p.y - r.y1)
        score = dy * 4 + dx  # prefer the line under the cursor
        if score < best_score:
            best, best_score = i, score
            if score == 0:
                break
    return best


def select_chars(chars: Sequence[CharBox], start: Sequence[float], end: Sequence[float]) -> TextSelection:
    """Select the characters between two points in reading order."""
    a, b = nearest_char(chars, start), nearest_char(chars, end)
    if a is None or b is None:
        return TextSelection("", ())
    lo, hi = min(a, b), max(a, b)
    return selection_from_range(chars, lo, hi)


def selection_from_range(chars: Sequence[CharBox], lo: int, hi: int) -> TextSelection:
    """Build a :class:`TextSelection` for ``chars[lo:hi + 1]``."""
    parts: list[str] = []
    rects: list[pymupdf.Rect] = []
    current_line = None
    for ch in chars[lo : hi + 1]:
        if ch.line != current_line:
            if current_line is not None:
                parts.append("\n")
            current_line = ch.line
            rects.append(pymupdf.Rect(ch.rect))
        else:
            rects[-1] |= ch.rect
        parts.append(ch.char)
    return TextSelection("".join(parts), tuple(rects))


def select_text(page: pymupdf.Page, start: Sequence[float], end: Sequence[float]) -> TextSelection:
    """Select text on ``page`` between two points (convenience wrapper)."""
    return select_chars(page_chars(page), start, end)


def select_all(page: pymupdf.Page) -> TextSelection:
    """Select every character on the page."""
    chars = page_chars(page)
    return selection_from_range(chars, 0, len(chars) - 1) if chars else TextSelection("", ())


def word_at(chars: Sequence[CharBox], point: Sequence[float]) -> TextSelection:
    """The word under ``point`` (used for double-click selection)."""
    i = nearest_char(chars, point)
    if i is None or chars[i].char.isspace():
        return TextSelection("", ())
    lo = hi = i
    while lo > 0 and chars[lo - 1].line == chars[i].line and not chars[lo - 1].char.isspace():
        lo -= 1
    while hi + 1 < len(chars) and chars[hi + 1].line == chars[i].line and not chars[hi + 1].char.isspace():
        hi += 1
    return selection_from_range(chars, lo, hi)


def _searchable(chars: Sequence[CharBox], match_case: bool) -> tuple[str, list[int]]:
    """Text with collapsed whitespace and a map from text index to char index."""
    out: list[str] = []
    mapping: list[int] = []
    previous_line = None
    for i, ch in enumerate(chars):
        if previous_line is not None and ch.line != previous_line and out and out[-1] != " ":
            out.append(" ")  # line break counts as a space
            mapping.append(-1)
        previous_line = ch.line
        c = " " if ch.char.isspace() else ch.char
        if c == " " and out and out[-1] == " ":
            continue
        if not match_case:
            lowered = c.lower()
            c = lowered if len(lowered) == 1 else c
        out.append(c)
        mapping.append(i)
    return "".join(out), mapping


def search_chars(chars: Sequence[CharBox], needle: str, match_case: bool = False) -> list[TextSelection]:
    """Find all occurrences of ``needle`` in a page's characters."""
    query = " ".join(needle.split())
    if not query:
        return []
    if not match_case:
        query = "".join(c.lower() if len(c.lower()) == 1 else c for c in query)
    text, mapping = _searchable(chars, match_case)
    hits: list[TextSelection] = []
    start = text.find(query)
    while start != -1:
        indices = [mapping[j] for j in range(start, start + len(query)) if mapping[j] >= 0]
        if indices:
            hits.append(selection_from_range(chars, indices[0], indices[-1]))
        start = text.find(query, start + max(1, len(query)))
    return hits


def search_page(page: pymupdf.Page, needle: str, match_case: bool = False) -> list[TextSelection]:
    """Find all occurrences of ``needle`` on ``page``."""
    return search_chars(page_chars(page), needle, match_case)


def search_document(
    doc: pymupdf.Document, needle: str, match_case: bool = False, pages: Iterable[int] | None = None
) -> dict[int, list[TextSelection]]:
    """Search several pages; returns ``{page_index: hits}`` for pages with hits."""
    results: dict[int, list[TextSelection]] = {}
    for pno in normalize_pages(pages, doc.page_count):
        hits = search_page(doc[pno], needle, match_case)
        if hits:
            results[pno] = hits
    return results


def page_text(page: pymupdf.Page) -> str:
    """Plain text of one page in reading order."""
    return page.get_text("text", sort=False)


def extract_text(
    doc: pymupdf.Document,
    pages: Iterable[int] | None = None,
    separators: bool = True,
    progress: Progress | None = None,
) -> str:
    """Plain text of the document.

    With ``separators`` each page starts with a ``--- Page N ---`` header;
    otherwise pages are separated by form feeds.
    """
    indices = normalize_pages(pages, doc.page_count)
    chunks = []
    for i, pno in enumerate(indices):
        if progress is not None and progress(i, len(indices), f"Reading page {pno + 1}") is False:
            raise OperationCancelled()
        text = page_text(doc[pno]).rstrip()
        chunks.append(f"--- Page {pno + 1} ---\n{text}" if separators else text)
    return ("\n\n" if separators else "\n\f").join(chunks) + "\n"


def export_text(
    doc: pymupdf.Document, path: str, separators: bool = True, progress: Progress | None = None
) -> int:
    """Write all text to a UTF-8 ``.txt`` file; returns the number of characters."""
    if not path:
        raise InvalidInput("Choose a file name for the text export.")
    content = extract_text(doc, None, separators, progress)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    return len(content)
