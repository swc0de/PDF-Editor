"""Images in page content: insert, find, move/resize, and Pillow helpers.

Moving an image rewrites the ``cm`` (placement matrix) that precedes its
``Do`` operator in the page's content stream. This works for images placed
with the common ``q … cm /Name Do Q`` pattern - which includes every image
inserted by this editor. Images drawn in other ways (inside forms, with
several references, or with transformations spread over the stream) are
reported as unsupported instead of being modified unreliably.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Sequence

import pymupdf
from PIL import Image, ImageChops, ImageOps

from ..errors import InvalidInput, UnsupportedOperation

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)"


@dataclass(frozen=True)
class PageImage:
    """One placement of an image on a page."""

    xref: int
    name: str
    bbox: pymupdf.Rect
    transform: pymupdf.Matrix


def load_image_bytes(source: str | bytes) -> bytes:
    """Read an image file (or validate bytes) and return PNG/JPEG data PyMuPDF accepts."""
    data = source if isinstance(source, bytes) else open(source, "rb").read()
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = (im.format or "").upper()
            if fmt in ("PNG", "JPEG"):
                return data
            im = ImageOps.exif_transpose(im)
            out = io.BytesIO()
            im.convert("RGBA" if "A" in im.getbands() else "RGB").save(out, "PNG")
            return out.getvalue()
    except (OSError, ValueError) as exc:
        raise InvalidInput("The file is not a supported image.") from exc


def image_size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as im:
        return im.size


def fit_rect(rect: Sequence[float], width: float, height: float) -> pymupdf.Rect:
    """The largest rectangle with the image's aspect ratio centred in ``rect``."""
    box = pymupdf.Rect(rect)
    scale = min(box.width / width, box.height / height)
    w, h = width * scale, height * scale
    x0, y0 = box.x0 + (box.width - w) / 2, box.y0 + (box.height - h) / 2
    return pymupdf.Rect(x0, y0, x0 + w, y0 + h)


def insert_image(page: pymupdf.Page, rect: Sequence[float], image: bytes, keep_proportion: bool = True) -> int:
    """Place an image in ``rect`` (page content, not an annotation); returns its xref."""
    box = pymupdf.Rect(rect)
    if box.is_empty or box.width < 1 or box.height < 1:
        raise InvalidInput("The image area is too small.")
    data = load_image_bytes(image)
    return page.insert_image(box, stream=data, keep_proportion=keep_proportion)


def page_images(page: pymupdf.Page) -> list[PageImage]:
    """All image placements on the page (in drawing order)."""
    names = {img[0]: img[7] for img in page.get_images(full=True)}
    result = []
    for info in page.get_image_info(xrefs=True):
        xref = info.get("xref", 0)
        if xref and xref in names:
            result.append(PageImage(xref, names[xref], pymupdf.Rect(info["bbox"]), pymupdf.Matrix(info["transform"])))
    return result


def image_at(page: pymupdf.Page, point: Sequence[float]) -> PageImage | None:
    """The top-most image under ``point``."""
    p = pymupdf.Point(point)
    hits = [img for img in page_images(page) if img.bbox.contains(p)]
    return hits[-1] if hits else None


def _find_placement(doc: pymupdf.Document, page: pymupdf.Page, name: str) -> tuple[int, re.Match]:
    pattern = re.compile(
        rf"({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s+cm\s*/{re.escape(name)}\s+Do".encode()
    )
    found: list[tuple[int, re.Match]] = []
    total_refs = 0
    for xref in page.get_contents():
        stream = doc.xref_stream(xref)
        total_refs += len(re.findall(rb"/" + re.escape(name.encode()) + rb"\s+Do", stream))
        found += [(xref, m) for m in pattern.finditer(stream)]
    if len(found) != 1 or total_refs != 1:
        raise UnsupportedOperation(
            "This image is placed in a way that cannot be moved reliably (it is drawn more than once "
            "or its position is set elsewhere in the page). Images you insert with this editor can always be moved."
        )
    return found[0]


def move_image(page: pymupdf.Page, image: PageImage, new_rect: Sequence[float]) -> None:
    """Move/resize one image placement so its bounding box becomes ``new_rect``."""
    target = pymupdf.Rect(new_rect)
    if target.is_empty or target.width < 1 or target.height < 1:
        raise InvalidInput("The image would become too small.")
    old = image.bbox
    if image.transform.b or image.transform.c:
        raise UnsupportedOperation("Rotated or skewed images cannot be moved.")
    doc = page.parent
    pno = page.number
    xref, match = _find_placement(doc, page, image.name)
    local = pymupdf.Matrix(*[float(g) for g in match.groups()])
    # PyMuPDF reports the transform with the image's unit square flipped
    # vertically; undo that to get the real image-space -> page mapping T.
    real = pymupdf.Matrix(1, 0, 0, -1, 0, 1) * image.transform
    # T = local * outer  =>  outer = local^-1 * T ; new local = T' * outer^-1
    outer = ~local * real
    sx, sy = target.width / old.width, target.height / old.height
    delta = pymupdf.Matrix(1, 0, 0, 1, -old.x0, -old.y0) * pymupdf.Matrix(sx, 0, 0, sy, 0, 0) * \
        pymupdf.Matrix(1, 0, 0, 1, target.x0, target.y0)
    new_local = real * delta * ~outer
    replacement = " ".join(f"{v:.5f}".rstrip("0").rstrip(".") for v in tuple(new_local)) + f" cm\n/{image.name} Do"
    original = doc.xref_stream(xref)
    doc.update_stream(xref, original[: match.start()] + replacement.encode() + original[match.end():])
    # verify; never leave a wrongly placed image behind
    moved = [img for img in page_images(doc[pno]) if img.xref == image.xref]
    if not any(abs(m.bbox.x0 - target.x0) < 0.5 and abs(m.bbox.y0 - target.y0) < 0.5 and
               abs(m.bbox.x1 - target.x1) < 0.5 and abs(m.bbox.y1 - target.y1) < 0.5 for m in moved):
        doc.update_stream(xref, original)
        raise UnsupportedOperation("This image's placement could not be changed reliably.")


def find_image(page: pymupdf.Page, xref: int, bbox: Sequence[float]) -> PageImage:
    """Re-locate an image placement by xref and approximate position."""
    target = pymupdf.Rect(bbox)
    candidates = [img for img in page_images(page) if img.xref == xref]
    if not candidates:
        raise InvalidInput("That image no longer exists.")
    return min(candidates, key=lambda img: abs(img.bbox.x0 - target.x0) + abs(img.bbox.y0 - target.y0))


def trim_image(png: bytes, padding: int = 4) -> bytes:
    """Crop away transparent or white margins (useful for signatures)."""
    with Image.open(io.BytesIO(png)) as im:
        im = im.convert("RGBA")
        alpha = im.getchannel("A")
        if alpha.getextrema()[0] < 255:  # has transparency: trim transparent margins
            box = alpha.getbbox()
        else:  # opaque: trim near-white margins
            white = Image.new("RGBA", im.size, (255, 255, 255, 255))
            box = ImageChops.difference(im, white).convert("L").point(lambda v: 255 if v > 20 else 0).getbbox()
        if not box:
            raise InvalidInput("The image is empty.")
        x0, y0, x1, y1 = box
        im = im.crop((max(0, x0 - padding), max(0, y0 - padding), min(im.width, x1 + padding), min(im.height, y1 + padding)))
        out = io.BytesIO()
        im.save(out, "PNG")
        return out.getvalue()


def white_to_transparent(png: bytes, threshold: int = 235) -> bytes:
    """Make near-white pixels transparent (scanned signatures on white paper)."""
    with Image.open(io.BytesIO(png)) as im:
        im = im.convert("RGBA")
        r, g, b, a = im.split()
        darkest = ImageChops.darker(r, ImageChops.darker(g, b))
        white_mask = darkest.point(lambda v: 255 if v >= threshold else 0)
        im.putalpha(ImageChops.subtract(a, white_mask))
        out = io.BytesIO()
        im.save(out, "PNG")
        return out.getvalue()


def styled_image(image: bytes, opacity: float = 1.0, rotation: float = 0.0) -> bytes:
    """PNG with reduced opacity and/or rotated by ``rotation`` degrees (counter-clockwise)."""
    if not 0 < opacity <= 1:
        raise InvalidInput("Opacity must be between 0 and 1.")
    with Image.open(io.BytesIO(image)) as im:
        im = ImageOps.exif_transpose(im).convert("RGBA")
        if opacity < 1:
            alpha = im.getchannel("A").point(lambda v: int(v * opacity))
            im.putalpha(alpha)
        if rotation % 360:
            im = im.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
        out = io.BytesIO()
        im.save(out, "PNG")
        return out.getvalue()
