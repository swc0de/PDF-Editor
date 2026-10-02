"""Page management: rotate, delete, duplicate, insert, reorder, merge, split, crop.

All functions are pure in the sense that they only touch the PyMuPDF
documents passed in. Page indices are 0-based.
"""

from __future__ import annotations

import io
import os
from typing import Callable, Iterable, Sequence

import pymupdf
from PIL import Image, ImageOps

from ..errors import InvalidInput, OperationCancelled
from ..utils import normalize_pages, safe_filename

Progress = Callable[[int, int, str], bool]

A4 = (595.0, 842.0)


def _tick(progress: Progress | None, done: int, total: int, message: str) -> None:
    if progress is not None and progress(done, total, message) is False:
        raise OperationCancelled()


def rotate_pages(doc: pymupdf.Document, pages: Iterable[int], angle: int) -> None:
    """Rotate pages clockwise by ``angle`` (a multiple of 90, may be negative)."""
    if angle % 90:
        raise InvalidInput("Pages can only be rotated in steps of 90 degrees.")
    for pno in normalize_pages(pages, doc.page_count):
        page = doc[pno]
        page.set_rotation((page.rotation + angle) % 360)


def delete_pages(doc: pymupdf.Document, pages: Iterable[int]) -> None:
    """Delete pages. At least one page must remain."""
    indices = normalize_pages(pages, doc.page_count)
    if not indices:
        return
    if len(indices) >= doc.page_count:
        raise InvalidInput("A PDF must keep at least one page.")
    doc.delete_pages(indices)


def duplicate_pages(doc: pymupdf.Document, pages: Iterable[int]) -> list[int]:
    """Insert an independent copy of each page right after it.

    Returns the indices of the new copies (after all insertions).
    """
    indices = normalize_pages(pages, doc.page_count)
    for pno in reversed(indices):
        # ``to`` inserts before that index; -1 appends after the last page
        doc.fullcopy_page(pno, pno + 1 if pno + 1 < doc.page_count else -1)
    # each copy is shifted by the number of copies inserted before it
    return [pno + i + 1 for i, pno in enumerate(indices)]


def insert_blank_page(
    doc: pymupdf.Document, index: int, width: float | None = None, height: float | None = None
) -> int:
    """Insert a blank page before ``index`` (``index == page_count`` appends).

    Without an explicit size the new page copies the size of its neighbour,
    or A4 for an empty document. Returns the new page's index.
    """
    if not 0 <= index <= doc.page_count:
        raise InvalidInput(f"Cannot insert a page at position {index + 1}.")
    if width is None or height is None:
        if doc.page_count:
            ref = doc[min(index, doc.page_count - 1)].rect
            width, height = ref.width, ref.height
        else:
            width, height = A4
    if width <= 0 or height <= 0:
        raise InvalidInput("Page width and height must be positive.")
    doc.new_page(pno=index if index < doc.page_count else -1, width=width, height=height)
    return index


def compute_move_order(page_count: int, pages: Iterable[int], target: int) -> list[int]:
    """New page order after moving ``pages`` so they start before ``target``.

    ``target`` is an index in the *current* order (``page_count`` = end).
    The moved pages keep their relative order.
    """
    moving = normalize_pages(pages, page_count)
    if not 0 <= target <= page_count:
        raise InvalidInput("Invalid drop position.")
    moving_set = set(moving)
    before = [p for p in range(target) if p not in moving_set]
    after = [p for p in range(target, page_count) if p not in moving_set]
    return before + moving + after


def reorder_pages(doc: pymupdf.Document, order: Sequence[int]) -> None:
    """Rearrange pages so that new page ``i`` is old page ``order[i]``."""
    if sorted(order) != list(range(doc.page_count)):
        raise InvalidInput("The new page order must contain every page exactly once.")
    if list(order) != list(range(doc.page_count)):
        doc.select(list(order))


def inverse_order(order: Sequence[int]) -> list[int]:
    """The permutation that undoes :func:`reorder_pages` with ``order``."""
    inverse = [0] * len(order)
    for new_index, old_index in enumerate(order):
        inverse[old_index] = new_index
    return inverse


def move_pages(doc: pymupdf.Document, pages: Iterable[int], target: int) -> list[int]:
    """Move ``pages`` before ``target``; returns the order that was applied."""
    order = compute_move_order(doc.page_count, pages, target)
    reorder_pages(doc, order)
    return order


def insert_pdf_pages(
    doc: pymupdf.Document,
    source: pymupdf.Document,
    index: int,
    pages: Iterable[int] | None = None,
) -> int:
    """Insert pages of ``source`` before ``index``; returns how many were inserted."""
    if not 0 <= index <= doc.page_count:
        raise InvalidInput(f"Cannot insert pages at position {index + 1}.")
    if source.needs_pass:
        raise InvalidInput("The source PDF is password protected and must be unlocked first.")
    wanted = normalize_pages(pages, source.page_count)
    if not wanted:
        return 0
    position = index
    # insert contiguous runs in one call - much faster for large ranges
    for run in _runs(wanted):
        doc.insert_pdf(source, from_page=run[0], to_page=run[-1], start_at=position)
        position += len(run)
    return len(wanted)


def _runs(indices: list[int]) -> list[list[int]]:
    """Split indices into runs of consecutive numbers, keeping their order."""
    runs: list[list[int]] = []
    for pno in indices:
        if runs and pno == runs[-1][-1] + 1:
            runs[-1].append(pno)
        else:
            runs.append([pno])
    return runs


def image_to_pdf_bytes(image: str | bytes, page_size: tuple[float, float] | None = None, margin: float = 0) -> bytes:
    """Convert an image file/bytes to a one-page PDF.

    Without ``page_size`` the page matches the image at 96 dpi (or the
    image's own dpi). With a page size the image is scaled to fit inside the
    margins and centred. EXIF orientation is honoured.
    """
    try:
        with Image.open(image if isinstance(image, str) else io.BytesIO(image)) as im:
            im = ImageOps.exif_transpose(im)
            dpi = im.info.get("dpi", (96, 96))[0] or 96
            if im.mode not in ("RGB", "RGBA", "L"):
                im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            width_pt, height_pt = im.width * 72.0 / dpi, im.height * 72.0 / dpi
    except (OSError, ValueError) as exc:
        name = image if isinstance(image, str) else "image"
        raise InvalidInput(f"'{os.path.basename(str(name))}' is not a supported image.") from exc
    pdf = pymupdf.open()
    if page_size is None:
        page = pdf.new_page(width=width_pt + 2 * margin, height=height_pt + 2 * margin)
    else:
        page = pdf.new_page(width=page_size[0], height=page_size[1])
    box = page.rect + (margin, margin, -margin, -margin)
    page.insert_image(box, stream=buf.getvalue(), keep_proportion=True)
    return pdf.tobytes(garbage=3, deflate=True)


def insert_images_as_pages(
    doc: pymupdf.Document,
    images: Sequence[str | bytes],
    index: int,
    page_size: tuple[float, float] | None = None,
    margin: float = 0,
) -> int:
    """Insert one page per image before ``index``; returns the count."""
    if not 0 <= index <= doc.page_count:
        raise InvalidInput(f"Cannot insert pages at position {index + 1}.")
    if not images:
        raise InvalidInput("No images were selected.")
    for offset, image in enumerate(images):
        single = pymupdf.open("pdf", image_to_pdf_bytes(image, page_size, margin))
        doc.insert_pdf(single, start_at=index + offset)
        single.close()
    return len(images)


def extract_pages(doc: pymupdf.Document, pages: Iterable[int]) -> pymupdf.Document:
    """Return a new document containing ``pages`` in the given order."""
    order = [int(p) for p in pages]
    if not order:
        raise InvalidInput("Select at least one page to extract.")
    normalize_pages(order, doc.page_count)  # validation only
    out = pymupdf.open()
    for run in _runs(order):
        out.insert_pdf(doc, from_page=run[0], to_page=run[-1])
    return out


def merge_files(
    paths: Sequence[str],
    output: str,
    passwords: dict[str, str] | None = None,
    progress: Progress | None = None,
) -> int:
    """Merge PDFs (in the given order) into ``output``; returns the page count."""
    if len(paths) < 1:
        raise InvalidInput("Choose at least one file to merge.")
    passwords = passwords or {}
    merged = pymupdf.open()
    try:
        for i, path in enumerate(paths):
            _tick(progress, i, len(paths) + 1, f"Adding {os.path.basename(path)}")
            src = pymupdf.open(path)
            if not src.is_pdf:
                src = pymupdf.open("pdf", src.convert_to_pdf())
            if src.needs_pass and not src.authenticate(passwords.get(path, "")):
                raise InvalidInput(f"'{os.path.basename(path)}' is password protected.")
            merged.insert_pdf(src)
            src.close()
        _tick(progress, len(paths), len(paths) + 1, "Saving")
        merged.save(output, garbage=3, deflate=True)
        return merged.page_count
    finally:
        merged.close()


def split_every(page_count: int, n: int) -> list[list[int]]:
    """Groups of ``n`` consecutive pages (the last group may be shorter)."""
    if n < 1:
        raise InvalidInput("The number of pages per file must be at least 1.")
    return [list(range(i, min(i + n, page_count))) for i in range(0, page_count, n)]


def split_document(
    doc: pymupdf.Document,
    groups: Sequence[Sequence[int]],
    output_dir: str,
    base_name: str,
    progress: Progress | None = None,
) -> list[str]:
    """Write each page group to its own PDF in ``output_dir``; returns the paths."""
    if not groups:
        raise InvalidInput("There is nothing to split.")
    os.makedirs(output_dir, exist_ok=True)
    base = safe_filename(base_name)
    width = len(str(len(groups)))
    written: list[str] = []
    for i, group in enumerate(groups):
        _tick(progress, i, len(groups), f"Writing part {i + 1} of {len(groups)}")
        part = extract_pages(doc, group)
        first, last = group[0] + 1, group[-1] + 1
        suffix = f"p{first}" if first == last else f"p{first}-{last}"
        path = os.path.join(output_dir, f"{base}_{i + 1:0{width}d}_{suffix}.pdf")
        part.save(path, garbage=3, deflate=True)
        part.close()
        written.append(path)
    _tick(progress, len(groups), len(groups), "Done")
    return written


def crop_pages(doc: pymupdf.Document, pages: Iterable[int], rect: Sequence[float]) -> None:
    """Crop pages to ``rect`` given in (unrotated) page coordinates.

    The rectangle is clipped to each page's media box.
    """
    box = pymupdf.Rect(rect)
    if box.is_empty or box.width < 1 or box.height < 1:
        raise InvalidInput("The crop area is empty.")
    for pno in normalize_pages(pages, doc.page_count):
        page = doc[pno]
        pos = page.cropbox_position
        media = pymupdf.Rect(0, 0, page.mediabox.width, page.mediabox.height)
        target = (box + (pos.x, pos.y, pos.x, pos.y)) & media
        if target.is_empty or target.width < 1 or target.height < 1:
            raise InvalidInput(f"The crop area lies outside page {pno + 1}.")
        page.set_cropbox(target)


def crop_margins(
    doc: pymupdf.Document, pages: Iterable[int], left: float, top: float, right: float, bottom: float
) -> None:
    """Trim margins (in points, as seen on screen) from each page."""
    if min(left, top, right, bottom) < 0:
        raise InvalidInput("Margins cannot be negative.")
    for pno in normalize_pages(pages, doc.page_count):
        page = doc[pno]
        visual = page.rect + (left, top, -right, -bottom)
        if visual.is_empty or visual.width < 1 or visual.height < 1:
            raise InvalidInput(f"The margins are larger than page {pno + 1}.")
        crop_pages(doc, [pno], (visual * page.derotation_matrix).normalize())


def reset_crop(doc: pymupdf.Document, pages: Iterable[int]) -> None:
    """Remove cropping so the whole media box is visible again."""
    for pno in normalize_pages(pages, doc.page_count):
        page = doc[pno]
        page.set_cropbox(pymupdf.Rect(0, 0, page.mediabox.width, page.mediabox.height))
