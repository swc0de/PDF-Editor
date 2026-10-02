"""Tests for core.operations.forms and core.operations.layout."""

from __future__ import annotations

import datetime as dt
import math

import pymupdf
import pytest

from pdf_editor.core.document import PdfDocument
from pdf_editor.core.errors import InvalidInput
from pdf_editor.core.operations import forms as ops
from pdf_editor.core.operations import layout
from tests.fixtures import builders


@pytest.fixture
def form_doc(form_pdf):
    doc = pymupdf.open(form_pdf)
    yield doc
    doc.close()


def field(doc, name, index=0):
    return [f for f in ops.list_fields(doc) if f.name == name][index]


# -- forms --------------------------------------------------------------------------
def test_list_fields(form_doc):
    fields = ops.list_fields(form_doc)
    assert [(f.name, f.kind) for f in fields] == [
        ("name", "text"), ("agree", "checkbox"), ("size", "radio"), ("size", "radio"),
        ("color", "combobox"), ("fruit", "listbox"),
    ]
    assert field(form_doc, "color").options == ["Red", "Green", "Blue"]
    assert field(form_doc, "size", 1).on_state == "Large"


def test_list_fields_no_form(raw_text_doc):
    assert ops.list_fields(raw_text_doc) == []


def test_field_at(form_doc):
    assert ops.field_at(form_doc[0], (80, 90)).name == "name"


def test_field_at_nothing(form_doc):
    assert ops.field_at(form_doc[0], (500, 700)) is None


def test_set_field_values(form_doc):
    ops.set_field_value(form_doc, 0, field(form_doc, "name").xref, "Jane Doe")
    ops.set_field_value(form_doc, 0, field(form_doc, "agree").xref, True)
    ops.set_field_value(form_doc, 0, field(form_doc, "color").xref, "Blue")
    ops.set_field_value(form_doc, 0, field(form_doc, "fruit").xref, "Cherry")
    assert field(form_doc, "name").value == "Jane Doe"
    assert field(form_doc, "agree").value is True
    assert field(form_doc, "color").value == "Blue" and field(form_doc, "fruit").value == "Cherry"


def test_radio_group_is_exclusive(form_doc):
    small, large = field(form_doc, "size", 0), field(form_doc, "size", 1)
    ops.set_field_value(form_doc, 0, small.xref, True)
    ops.set_field_value(form_doc, 0, large.xref, True)
    assert field(form_doc, "size", 0).value is False and field(form_doc, "size", 1).value is True
    parent = form_doc.xref_get_key(large.xref, "Parent")[1].split()[0]
    assert form_doc.xref_get_key(int(parent), "V") == ("name", "/Large")


def test_set_field_value_rejects_invalid_choice(form_doc):
    with pytest.raises(InvalidInput):
        ops.set_field_value(form_doc, 0, field(form_doc, "color").xref, "Purple")
    with pytest.raises(InvalidInput):
        ops.set_field_value(form_doc, 0, 99999, "x")


def test_reset_field(form_doc):
    xref = field(form_doc, "name").xref
    ops.set_field_value(form_doc, 0, xref, "temp")
    ops.reset_field(form_doc, 0, xref)
    assert field(form_doc, "name").value in ("", None)


def test_reset_field_missing(form_doc):
    with pytest.raises(InvalidInput):
        ops.reset_field(form_doc, 0, 424242)


def test_flatten_forms(form_doc):
    ops.set_field_value(form_doc, 0, field(form_doc, "name").xref, "Flat Value")
    assert ops.flatten_forms(form_doc) == 6
    assert ops.list_fields(form_doc) == [] and "Flat Value" in form_doc[0].get_text()


def test_flatten_forms_without_fields(raw_text_doc):
    assert ops.flatten_forms(raw_text_doc) == 0


def test_document_form_undo(form_pdf):
    doc = PdfDocument.open(form_pdf)
    xref = field(doc.raw, "size", 1).xref
    doc.set_field_value(0, xref, True)
    assert field(doc.raw, "size", 1).value is True
    doc.history.undo()
    assert field(doc.raw, "size", 1).value is False
    doc.flatten_forms()
    assert doc.form_fields() == []
    doc.history.undo()
    assert len(doc.form_fields()) == 6


# -- layout -------------------------------------------------------------------------
def visual_angle(page, needle: str = "") -> int:
    """On-screen angle of the first text line containing ``needle``."""
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            if needle not in "".join(s["text"] for s in line["spans"]):
                continue
            v = pymupdf.Point(line["dir"]) * page.rotation_matrix - pymupdf.Point(0, 0) * page.rotation_matrix
            return round(math.degrees(math.atan2(-v.y, v.x)))
    raise AssertionError(f"no text line containing {needle!r}")


def test_add_text_watermark_rotated_pages():
    doc = pymupdf.open()
    for rotation in (0, 90):
        page = doc.new_page()
        page.set_rotation(rotation)
    assert layout.add_text_watermark(doc, None, "DRAFT", rotation=30, opacity=0.4) == 2
    for pno in range(2):
        page = doc[pno]
        assert "DRAFT" in page.get_text()
        assert visual_angle(page, "DRAFT") == 30
        hit = page.search_for("DRAFT")[0]
        center = (hit * page.rotation_matrix).normalize()
        assert abs((center.x0 + center.x1) / 2 - page.rect.width / 2) < 10


def test_add_text_watermark_validation(raw_text_doc):
    with pytest.raises(InvalidInput):
        layout.add_text_watermark(raw_text_doc, None, "  ")
    with pytest.raises(InvalidInput):
        layout.add_text_watermark(raw_text_doc, None, "X", opacity=0)


def test_add_image_watermark(raw_text_doc):
    assert layout.add_image_watermark(raw_text_doc, [0, 2], builders.png_bytes(200, 100), scale=0.5) == 2
    page = raw_text_doc[0]
    info = page.get_image_info()[0]
    assert pymupdf.Rect(info["bbox"]).width == pytest.approx(595 * 0.5, abs=1)
    assert raw_text_doc[1].get_image_info() == []


def test_add_image_watermark_bad_scale(raw_text_doc):
    with pytest.raises(InvalidInput):
        layout.add_image_watermark(raw_text_doc, None, builders.png_bytes(), scale=2)


def test_format_template():
    out = layout.format_template("{filename} p{page}/{total} {date} {title}", 3, 9, "a.pdf", "T", dt.date(2026, 1, 2))
    assert out == "a.pdf p3/9 2026-01-02 T"


def test_format_template_without_tokens():
    assert layout.format_template("plain", 1, 1) == "plain"


def test_add_header_footer(raw_text_doc):
    spec = layout.HeaderFooter({"top-left": "{filename}", "bottom-right": "{page} / {total}"}, fontsize=9)
    assert layout.add_header_footer(raw_text_doc, [1, 2], spec, filename="report.pdf") == 2
    assert "report.pdf" in raw_text_doc[1].get_text() and "1 / 2" in raw_text_doc[1].get_text()
    assert "2 / 2" in raw_text_doc[2].get_text() and "report.pdf" not in raw_text_doc[0].get_text()
    footer = raw_text_doc[2].search_for("2 / 2")[0]
    assert footer.y1 > 842 - 28 - 20 and footer.x1 > 595 - 28 - 40


def test_add_header_footer_validation(raw_text_doc):
    with pytest.raises(InvalidInput):
        layout.add_header_footer(raw_text_doc, None, layout.HeaderFooter({"middle": "x"}))
    with pytest.raises(InvalidInput):
        layout.add_header_footer(raw_text_doc, None, layout.HeaderFooter({"top-left": "  "}))


def test_add_page_numbers_on_rotated_page(raw_text_doc):
    raw_text_doc[1].set_rotation(90)
    layout.add_page_numbers(raw_text_doc, None, "Page {page} of {total}", "bottom-center", start_number=5)
    page = raw_text_doc[1]
    assert "Page 6 of 7" in page.get_text() and visual_angle(page, "of 7") == 0
    hit = (page.search_for("Page 6 of 7")[0] * page.rotation_matrix).normalize()
    assert hit.y1 > page.rect.height - 60  # at the visual bottom


def test_add_page_numbers_validation(raw_text_doc):
    with pytest.raises(InvalidInput):
        layout.add_page_numbers(raw_text_doc, None, "no token")
    with pytest.raises(InvalidInput):
        layout.add_page_numbers(raw_text_doc, None, "{page}", position="middle")
