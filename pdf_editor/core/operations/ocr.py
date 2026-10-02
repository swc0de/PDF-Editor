"""OCR through PyMuPDF's Tesseract support (optional dependency).

Each page is rendered, recognised by Tesseract, and the resulting
*invisible* text layer is laid over the original page, so the page looks
unchanged but its text becomes searchable and selectable.

Nothing here raises when Tesseract is missing: :func:`tesseract_status`
reports availability and :func:`install_instructions` explains the fix.
"""

from __future__ import annotations

import glob
import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Iterable

import pymupdf

from ..errors import InvalidInput, OcrUnavailable, OperationCancelled
from ..utils import normalize_pages

Progress = Callable[[int, int, str], bool]


@dataclass(frozen=True)
class OcrStatus:
    available: bool
    tessdata: str | None
    languages: tuple[str, ...] = ()
    message: str = ""


@dataclass
class OcrResult:
    processed: list[int] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)
    words: int = 0


def install_instructions(platform: str | None = None) -> str:
    """How to install Tesseract on the current (or given) operating system."""
    platform = platform or sys.platform
    if platform.startswith("win"):
        steps = ("Download the installer from https://github.com/UB-Mannheim/tesseract/wiki, run it, and make "
                 "sure 'tesseract.exe' is on your PATH (or set TESSDATA_PREFIX to its 'tessdata' folder).")
    elif platform == "darwin":
        steps = "Install Homebrew (https://brew.sh), then run:  brew install tesseract tesseract-lang"
    else:
        steps = ("Install it with your package manager, e.g.  sudo apt install tesseract-ocr  (Debian/Ubuntu),  "
                 "sudo dnf install tesseract  (Fedora) or  sudo pacman -S tesseract tesseract-data-eng  (Arch).")
    return f"Text recognition (OCR) needs the free Tesseract OCR engine.\n\n{steps}\n\nThen restart PDF Editor."


def tesseract_status(tessdata: str | None = None) -> OcrStatus:
    """Detect Tesseract and its installed languages (never raises)."""
    try:
        folder = pymupdf.get_tessdata(tessdata)
    except Exception:
        return OcrStatus(False, None, (), "Tesseract OCR is not installed.\n\n" + install_instructions())
    if not folder or not os.path.isdir(folder):
        return OcrStatus(False, None, (), f"Tesseract language data was not found at '{folder}'.\n\n"
                         + install_instructions())
    languages = tuple(sorted(
        os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(folder, "*.traineddata"))
        if os.path.basename(p) != "osd.traineddata"
    ))
    if not languages:
        return OcrStatus(False, folder, (), "Tesseract is installed but has no language data.\n\n"
                         + install_instructions())
    return OcrStatus(True, folder, languages, f"Tesseract OCR found ({', '.join(languages)}).")


def page_has_text(page: pymupdf.Page) -> bool:
    """True if the page already contains extractable text."""
    return bool(page.get_text("text").strip())


def ocr_page(page: pymupdf.Page, language: str = "eng", dpi: int = 300, tessdata: str | None = None) -> int:
    """Add an invisible OCR text layer to ``page``; returns the number of words found."""
    doc, pno = page.parent, page.number
    rotation = page.rotation
    if rotation:
        page.set_rotation(0)  # recognise in unrotated space so the layer lines up
        page = doc[pno]
    try:
        pix = page.get_pixmap(dpi=dpi)
        ocr = pymupdf.open("pdf", pix.pdfocr_tobytes(language=language, tessdata=tessdata))
        layer = ocr[0]
        words = len(layer.get_text("words"))
        if words:
            # keep only the invisible text: remove the page image from the OCR result
            layer.add_redact_annot(layer.rect)
            layer.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                                       graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                       text=pymupdf.PDF_REDACT_TEXT_NONE)
            page.show_pdf_page(page.rect, ocr, 0, overlay=True)
        ocr.close()
        return words
    finally:
        if rotation:
            doc[pno].set_rotation(rotation)


def ocr_document(
    doc: pymupdf.Document,
    pages: Iterable[int] | None = None,
    language: str = "eng",
    dpi: int = 300,
    skip_text_pages: bool = True,
    tessdata: str | None = None,
    progress: Progress | None = None,
) -> OcrResult:
    """OCR several pages; pages that already have text are skipped by default."""
    status = tesseract_status(tessdata)
    if not status.available:
        raise OcrUnavailable(status.message)
    for lang in language.split("+"):
        if lang not in status.languages:
            raise InvalidInput(f"The OCR language '{lang}' is not installed ({', '.join(status.languages)} available).")
    if not 72 <= dpi <= 600:
        raise InvalidInput("Choose an OCR resolution between 72 and 600 dpi.")
    indices = normalize_pages(pages, doc.page_count)
    result = OcrResult()
    for i, pno in enumerate(indices):
        if progress is not None and progress(i, len(indices), f"Recognising page {pno + 1} of {doc.page_count}") is False:
            raise OperationCancelled()
        page = doc[pno]
        if skip_text_pages and page_has_text(page):
            result.skipped.append(pno)
            continue
        result.words += ocr_page(page, language, dpi, status.tessdata)
        result.processed.append(pno)
    if progress is not None:
        progress(len(indices), len(indices), "Done")
    return result
