"""Shared pytest fixtures. All PDFs are generated on the fly."""

from __future__ import annotations

import faulthandler
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.fixtures import builders  # noqa: E402


@pytest.fixture(autouse=True)
def _hang_guard():
    """Fail loudly (with a traceback) instead of hanging forever on a modal dialog."""
    faulthandler.dump_traceback_later(120, exit=True)
    yield
    faulthandler.cancel_dump_traceback_later()


@pytest.fixture
def text_pdf(tmp_path) -> str:
    return builders.text_pdf(str(tmp_path / "text.pdf"))


@pytest.fixture
def ten_page_pdf(tmp_path) -> str:
    return builders.text_pdf(str(tmp_path / "ten.pdf"), pages=10)


@pytest.fixture
def outline_pdf(tmp_path) -> str:
    return builders.outline_pdf(str(tmp_path / "outline.pdf"))


@pytest.fixture
def image_pdf(tmp_path) -> str:
    return builders.image_pdf(str(tmp_path / "images.pdf"))


@pytest.fixture
def form_pdf(tmp_path) -> str:
    return builders.form_pdf(str(tmp_path / "form.pdf"))


@pytest.fixture
def annotated_pdf(tmp_path) -> str:
    return builders.annotated_pdf(str(tmp_path / "annotated.pdf"))


@pytest.fixture
def encrypted_pdf(tmp_path) -> str:
    return builders.encrypted_pdf(str(tmp_path / "encrypted.pdf"))


@pytest.fixture
def scanned_pdf(tmp_path) -> str:
    return builders.scanned_pdf(str(tmp_path / "scanned.pdf"))


@pytest.fixture
def png_file(tmp_path) -> str:
    return builders.image_file(str(tmp_path / "picture.png"))


@pytest.fixture
def jpg_file(tmp_path) -> str:
    return builders.image_file(str(tmp_path / "photo.jpg"), fmt="JPEG")


@pytest.fixture
def raw_text_doc(text_pdf):
    """An open ``pymupdf.Document`` of the 3-page text fixture."""
    import pymupdf

    doc = pymupdf.open(text_pdf)
    yield doc
    doc.close()


@pytest.fixture
def raw_ten_doc(ten_page_pdf):
    import pymupdf

    doc = pymupdf.open(ten_page_pdf)
    yield doc
    doc.close()


tesseract_available = shutil.which("tesseract") is not None or bool(os.environ.get("TESSDATA_PREFIX"))
requires_tesseract = pytest.mark.skipif(not tesseract_available, reason="Tesseract OCR is not installed")
