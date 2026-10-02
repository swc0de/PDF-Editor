"""Tests for core.operations.redact, optimize, convert and ocr."""

from __future__ import annotations

import os

import pymupdf
import pytest

from pdf_editor.core.document import PdfDocument
from pdf_editor.core.errors import InvalidInput, OcrUnavailable, OperationCancelled
from pdf_editor.core.operations import convert, ocr, optimize, redact
from tests.conftest import requires_tesseract
from tests.fixtures import builders


def contains(path: str, text: str) -> bool:
    """True if ``text`` occurs in any stream, literally or hex-encoded (as in TJ arrays)."""
    data = all_stream_text(path).lower()
    return text.encode() in data or text.encode().hex().encode() in data


def all_stream_text(path: str) -> bytes:
    """Every decompressed stream in the file, concatenated (to prove content is gone)."""
    doc = pymupdf.open(path)
    data = b""
    for xref in range(1, doc.xref_length()):
        try:
            if doc.xref_is_stream(xref):
                data += doc.xref_stream(xref) or b""
        except Exception:
            pass
    return data


# -- redact ---------------------------------------------------------------------
def test_mark_area(raw_text_doc):
    xref = redact.mark_area(raw_text_doc[0], (60, 100, 300, 125), label="secret")
    marks = redact.list_marks(raw_text_doc)
    assert [m.xref for m in marks] == [xref] and marks[0].kind == "Redact" and marks[0].contents == "secret"


def test_mark_area_outside_page(raw_text_doc):
    with pytest.raises(InvalidInput):
        redact.mark_area(raw_text_doc[0], (2000, 2000, 2100, 2100))


def test_find_text_marks(raw_text_doc):
    found = redact.find_text_marks(raw_text_doc, "marker 002")
    assert list(found) == [1] and len(found[1]) == 1


def test_find_text_marks_requires_text(raw_text_doc):
    with pytest.raises(InvalidInput):
        redact.find_text_marks(raw_text_doc, "  ")


def test_mark_text(raw_text_doc):
    marks = redact.mark_text(raw_text_doc, "Unique marker")
    assert [p for p, _ in marks] == [0, 1, 2]


def test_mark_text_no_hits(raw_text_doc):
    assert redact.mark_text(raw_text_doc, "zebra") == []


def test_list_marks_ignores_other_annotations(annotated_pdf):
    assert redact.list_marks(pymupdf.open(annotated_pdf)) == []


def test_pages_with_marks(raw_text_doc):
    redact.mark_text(raw_text_doc, "marker 003")
    assert redact.pages_with_marks(raw_text_doc) == [2]


def test_pages_with_marks_none(raw_text_doc):
    assert redact.pages_with_marks(raw_text_doc) == []


def test_apply_redactions_removes_text_and_image_pixels(tmp_path):
    path = builders.image_pdf(str(tmp_path / "img.pdf"), pages=1)
    doc = pymupdf.open(path)
    page = doc[0]
    redact.mark_text(doc, "Images page")
    redact.mark_area(doc[0], (72, 80, 200, 200))
    assert redact.apply_redactions(doc) == 1
    page = doc[0]
    assert "Images page" not in page.get_text() and redact.list_marks(doc) == []
    pix = page.get_pixmap()
    assert pix.pixel(100, 100) == (0, 0, 0)  # covered area is filled black


def test_apply_redactions_nothing_marked(raw_text_doc):
    assert redact.apply_redactions(raw_text_doc) == 0


def test_scrub_hidden_data(raw_text_doc):
    redact.scrub_hidden_data(raw_text_doc)
    assert not (raw_text_doc.metadata or {}).get("author")


def test_scrub_hidden_data_keeps_text(raw_text_doc):
    redact.scrub_hidden_data(raw_text_doc)
    assert "Page 1" in raw_text_doc[0].get_text()


def test_redaction_is_permanent_in_saved_file(text_pdf, tmp_path):
    doc = PdfDocument.open(text_pdf)
    assert doc.mark_redaction_text("Unique marker 002") == 1
    doc.apply_redactions()
    assert doc.needs_full_save
    out = str(tmp_path / "redacted.pdf")
    doc.save(out)
    assert not contains(out, "marker 002")
    assert contains(out, "marker 001")  # positive control: other text is still there
    # saving back to the original path is also a full rewrite after redaction
    doc2 = PdfDocument.open(text_pdf)
    doc2.mark_redaction_text("Unique marker 001")
    doc2.apply_redactions()
    result = doc2.save()
    assert not result.incremental and not contains(text_pdf, "marker 001")


# -- optimize --------------------------------------------------------------------
def test_get_preset():
    assert optimize.get_preset("HIGH").dpi_target == 96


def test_get_preset_unknown():
    with pytest.raises(InvalidInput):
        optimize.get_preset("extreme")


def test_compress_document_in_place(image_pdf):
    doc = pymupdf.open(image_pdf)
    optimize.compress_document(doc, "high")
    assert doc.page_count == 2


def test_compress_document_cancel(image_pdf):
    with pytest.raises(OperationCancelled):
        optimize.compress_document(pymupdf.open(image_pdf), "low", progress=lambda d, t, m: False)


def test_save_compressed_shrinks(image_pdf, tmp_path):
    before = os.path.getsize(image_pdf)
    result = optimize.save_compressed(pymupdf.open(image_pdf), str(tmp_path / "small.pdf"), "high", before)
    assert result.after < before * 0.6 and result.saved_percent > 40


def test_save_compressed_presets_ordered(image_pdf, tmp_path):
    sizes = [optimize.save_compressed(pymupdf.open(image_pdf), str(tmp_path / f"{p}.pdf"), p).after
             for p in ("low", "medium", "high")]
    assert sizes[0] >= sizes[1] >= sizes[2]


def test_compress_file(image_pdf, tmp_path):
    result = optimize.compress_file(image_pdf, str(tmp_path / "c.pdf"), "medium")
    assert result.before == os.path.getsize(image_pdf) and pymupdf.open(result.path).page_count == 2


def test_compress_file_refuses_overwrite(image_pdf):
    with pytest.raises(InvalidInput):
        optimize.compress_file(image_pdf, image_pdf, "low")


def test_compress_result_percent():
    assert optimize.CompressResult("x", 0, 10).saved_percent == 0.0
    assert optimize.CompressResult("x", 200, 50).saved_percent == pytest.approx(75)


# -- convert ---------------------------------------------------------------------
def test_export_page_images_png_and_jpg(raw_text_doc, tmp_path):
    pngs = convert.export_page_images(raw_text_doc, [0, 2], str(tmp_path), "doc", "png", dpi=72)
    jpgs = convert.export_page_images(raw_text_doc, None, str(tmp_path), "doc", "jpeg", dpi=36, jpg_quality=50)
    assert [os.path.basename(p) for p in pngs] == ["doc_1.png", "doc_3.png"] and len(jpgs) == 3
    assert pymupdf.Pixmap(pngs[0]).width == 595


def test_export_page_images_validation(raw_text_doc, tmp_path):
    with pytest.raises(InvalidInput):
        convert.export_page_images(raw_text_doc, None, str(tmp_path), fmt="gif")
    with pytest.raises(InvalidInput):
        convert.export_page_images(raw_text_doc, None, str(tmp_path), dpi=5000)


def test_extract_images(image_pdf, tmp_path):
    paths = convert.extract_images(pymupdf.open(image_pdf), str(tmp_path / "imgs"))
    exts = sorted(os.path.splitext(p)[1] for p in paths)
    assert exts == [".jpg", ".png"]  # shared images are written once


def test_extract_images_min_size_and_empty(raw_text_doc, image_pdf, tmp_path):
    assert convert.extract_images(raw_text_doc, str(tmp_path / "none")) == []
    assert len(convert.extract_images(pymupdf.open(image_pdf), str(tmp_path / "big"), min_size=500)) == 1


# -- ocr -------------------------------------------------------------------------
def test_install_instructions_per_platform():
    assert "UB-Mannheim" in ocr.install_instructions("win32")
    assert "brew install tesseract" in ocr.install_instructions("darwin")
    assert "apt install tesseract-ocr" in ocr.install_instructions("linux")


def test_tesseract_status_missing(monkeypatch):
    def missing(tessdata=None):
        raise RuntimeError("No tessdata specified and Tesseract is not installed")

    monkeypatch.setattr(ocr.pymupdf, "get_tessdata", missing)
    status = ocr.tesseract_status()
    assert not status.available and "Tesseract" in status.message and "install" in status.message.lower()


def test_tesseract_status_empty_folder(tmp_path):
    status = ocr.tesseract_status(str(tmp_path))
    assert not status.available and "no language data" in status.message


def test_ocr_document_raises_friendly_error_without_tesseract(monkeypatch, scanned_pdf):
    monkeypatch.setattr(ocr, "tesseract_status", lambda tessdata=None: ocr.OcrStatus(False, None, (), "not installed"))
    with pytest.raises(OcrUnavailable):
        ocr.ocr_document(pymupdf.open(scanned_pdf))


def test_page_has_text(raw_text_doc, scanned_pdf):
    assert ocr.page_has_text(raw_text_doc[0])
    assert not ocr.page_has_text(pymupdf.open(scanned_pdf)[0])


@requires_tesseract
def test_ocr_document_makes_scan_searchable(scanned_pdf):
    doc = pymupdf.open(scanned_pdf)
    doc[0].set_rotation(90)
    result = ocr.ocr_document(doc, dpi=200)
    page = doc[0]
    assert result.processed == [0] and result.words >= 4
    assert page.search_for("invoice") and page.rotation == 90


@requires_tesseract
def test_ocr_document_skips_text_pages_and_validates(raw_text_doc):
    assert ocr.ocr_document(raw_text_doc, [0]).skipped == [0]
    with pytest.raises(InvalidInput):
        ocr.ocr_document(raw_text_doc, [0], language="klingon")


@requires_tesseract
def test_ocr_page(scanned_pdf):
    doc = pymupdf.open(scanned_pdf)
    assert ocr.ocr_page(doc[0], dpi=150) >= 4 and "12345" in doc[0].get_text()


def test_ocr_page_blank_page_finds_nothing():
    if not ocr.tesseract_status().available:
        pytest.skip("Tesseract OCR is not installed")
    doc = pymupdf.open()
    doc.new_page()
    assert ocr.ocr_page(doc[0], dpi=72) == 0
