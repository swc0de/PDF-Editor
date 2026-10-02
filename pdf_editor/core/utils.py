"""Small, dependency-free helpers shared by the core layer."""

from __future__ import annotations

import os
import re
from typing import Iterable, Sequence

import pymupdf

from .errors import InvalidInput

RGB = tuple[float, float, float]


def rgb_from_hex(value: str) -> RGB:
    """Convert ``"#rrggbb"`` (or ``"rrggbb"``) to a PyMuPDF float triple."""
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", text):
        raise InvalidInput(f"'{value}' is not a valid colour.")
    return tuple(int(text[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def hex_from_rgb(color: Sequence[float] | None) -> str | None:
    """Convert a PyMuPDF colour sequence (gray, RGB or CMYK) to ``#rrggbb``."""
    if not color:
        return None
    if len(color) == 1:
        r = g = b = color[0]
    elif len(color) == 3:
        r, g, b = color
    elif len(color) == 4:
        c, m, y, k = color
        r, g, b = (1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)
    else:
        return None
    return "#" + "".join(f"{round(max(0.0, min(1.0, v)) * 255):02x}" for v in (r, g, b))


def rgb_from_int(value: int) -> RGB:
    """Convert an sRGB integer (as found in text-extraction spans) to floats."""
    return (((value >> 16) & 255) / 255.0, ((value >> 8) & 255) / 255.0, (value & 255) / 255.0)


def normalize_pages(pages: Iterable[int] | None, page_count: int) -> list[int]:
    """Return sorted, de-duplicated, validated 0-based page indices.

    ``None`` means "all pages".
    """
    if pages is None:
        return list(range(page_count))
    result = sorted(set(int(p) for p in pages))
    for p in result:
        if p < 0 or p >= page_count:
            raise InvalidInput(f"Page {p + 1} does not exist (document has {page_count} pages).")
    return result


def parse_page_ranges(spec: str, page_count: int) -> list[list[int]]:
    """Parse a range specification such as ``"1-3, 5, 8-"`` into page groups.

    Page numbers in ``spec`` are 1-based; the returned indices are 0-based.
    ``"8-"`` means "page 8 to the end", ``"-3"`` means "pages 1 to 3" and
    ``"5-2"`` is a descending range. Each comma-separated part becomes one group.
    """
    groups: list[list[int]] = []
    parts = [p.strip() for p in spec.replace(";", ",").split(",")]
    if not any(parts):
        raise InvalidInput("Please enter at least one page or page range.")
    for part in parts:
        if not part:
            continue
        match = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if match:
            start = int(match.group(1)) if match.group(1) else 1
            end = int(match.group(2)) if match.group(2) else page_count
        elif part.isdigit():
            start = end = int(part)
        else:
            raise InvalidInput(f"'{part}' is not a valid page or range.")
        for number in (start, end):
            if number < 1 or number > page_count:
                raise InvalidInput(f"Page {number} is out of range (1-{page_count}).")
        step = 1 if end >= start else -1
        groups.append([n - 1 for n in range(start, end + step, step)])
    return groups


def format_size(num_bytes: int | float) -> str:
    """Format a byte count for humans, e.g. ``1.4 MB``."""
    size = float(num_bytes)
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} bytes" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"  # pragma: no cover - loop always returns


def file_size(path: str | os.PathLike[str] | None) -> int:
    """Size of a file in bytes, or 0 if it does not exist."""
    try:
        return os.path.getsize(path) if path else 0
    except OSError:
        return 0


def normalized_rect(x0: float, y0: float, x1: float, y1: float) -> pymupdf.Rect:
    """Rectangle from two arbitrary corners."""
    return pymupdf.Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def visual_to_page(page: pymupdf.Page, point: Sequence[float]) -> pymupdf.Point:
    """Convert a point on the displayed (rotated) page to unrotated page space."""
    return pymupdf.Point(point) * page.derotation_matrix


def page_to_visual(page: pymupdf.Page, point: Sequence[float]) -> pymupdf.Point:
    """Convert an unrotated page-space point to displayed (rotated) coordinates."""
    return pymupdf.Point(point) * page.rotation_matrix


def visual_rect_to_page(page: pymupdf.Page, rect: Sequence[float]) -> pymupdf.Rect:
    """Convert a rectangle drawn on the displayed page to unrotated page space."""
    return (pymupdf.Rect(rect) * page.derotation_matrix).normalize()


def safe_filename(name: str, default: str = "document") -> str:
    """Strip characters that are not allowed in file names on common systems."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return cleaned or default
