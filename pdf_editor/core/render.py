"""Page rendering to raw pixel buffers (GUI-free).

The viewer converts :class:`RenderedPage` into a ``QImage``; keeping the
PyMuPDF side here means rendering can be tested without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pymupdf

# Never create pixmaps larger than this many pixels (memory guard at high zoom).
MAX_PIXELS = 24_000_000


@dataclass(frozen=True)
class RenderedPage:
    """An RGB (or RGBA) pixel buffer for one page or part of a page."""

    width: int
    height: int
    stride: int
    samples: bytes
    alpha: bool
    scale: float  # pixels per point actually used


def effective_scale(page_rect: pymupdf.Rect, scale: float, max_pixels: int = MAX_PIXELS) -> float:
    """Clamp ``scale`` so the full page stays under ``max_pixels``."""
    pixels = page_rect.width * page_rect.height * scale * scale
    if pixels <= max_pixels or pixels <= 0:
        return scale
    return scale * (max_pixels / pixels) ** 0.5


def render_page(
    doc: pymupdf.Document,
    pno: int,
    scale: float,
    *,
    clip: Sequence[float] | None = None,
    annots: bool = True,
    alpha: bool = False,
    max_pixels: int = MAX_PIXELS,
) -> RenderedPage:
    """Render page ``pno`` at ``scale`` pixels per point.

    ``clip`` is a rectangle in *visual* (rotated) page coordinates; when
    given, only that part is rendered (used for sharp detail at high zoom).
    """
    page = doc[pno]
    if clip is None:
        scale = effective_scale(page.rect, scale, max_pixels)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), annots=annots, alpha=alpha)
    else:
        # get_pixmap's clip is given in visual (rotated) page coordinates.
        visual = pymupdf.Rect(clip) & page.rect
        scale = effective_scale(visual, scale, max_pixels)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=visual, annots=annots, alpha=alpha)
    return RenderedPage(pix.width, pix.height, pix.stride, bytes(pix.samples), pix.alpha == 1, scale)


def page_sizes(doc: pymupdf.Document) -> list[tuple[float, float]]:
    """Visible (rotated, cropped) width and height of every page in points."""
    sizes = []
    for pno in range(doc.page_count):
        rect = doc[pno].rect
        sizes.append((rect.width, rect.height))
    return sizes
