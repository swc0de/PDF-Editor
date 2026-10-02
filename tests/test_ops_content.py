"""Tests for core.operations.textedit and core.operations.images."""

from __future__ import annotations

import io

import pymupdf
import pytest
from PIL import Image

from pdf_editor.core.document import PdfDocument
from pdf_editor.core.errors import InvalidInput, UnsupportedOperation
from pdf_editor.core.operations import images as img_ops
from pdf_editor.core.operations import textedit as ops
from tests.fixtures import builders


def two_tone_png() -> bytes:
    im = Image.new("RGB", (100, 100), (0, 0, 255))
    im.paste((255, 0, 0), (0, 0, 100, 50))  # red top half
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


# -- textedit -----------------------------------------------------------------------
def test_base14_name():
    assert ops.base14_name("Times", bold=True, italic=True) == "tibi"
    assert ops.base14_name("Courier") == "cour"


def test_base14_name_unknown_family():
    with pytest.raises(InvalidInput):
        ops.base14_name("Comic Sans")


def test_text_spans(raw_text_doc):
    spans = ops.text_spans(raw_text_doc[0])
    first = spans[0]
    assert first.text == "Page 1" and first.size == pytest.approx(24) and first.font == "Helvetica"
    blue = [s for s in spans if s.text.startswith("Unique")][0]
    assert blue.color == (0.0, 0.0, 1.0) and blue.mono


def test_text_spans_blank_page():
    doc = pymupdf.open()
    doc.new_page()
    assert ops.text_spans(doc[0]) == []


def test_span_at(raw_text_doc):
    span = ops.span_at(raw_text_doc[0], (80, 65))
    assert span is not None and span.text == "Page 1"


def test_span_at_empty_area(raw_text_doc):
    assert ops.span_at(raw_text_doc[0], (500, 800)) is None


def test_match_font_standard_font_is_exact(raw_text_doc):
    page = raw_text_doc[0]
    span = ops.span_at(page, (80, 65))
    choice = ops.match_font(raw_text_doc, page, span, "New heading")
    assert choice.exact and choice.fontname == "helv" and choice.warning is None


def test_match_font_warns_for_unavailable_font(tmp_path):
    # A span in an embedded TrueType *subset* missing the new glyphs -> fallback with a warning
    import os

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if not os.path.exists(font_path):
        pytest.skip("DejaVu font not installed")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_font(fontname="dv", fontfile=font_path)
    page.insert_text((72, 100), "abc", fontname="dv", fontsize=14)
    doc.subset_fonts()
    doc = pymupdf.open("pdf", doc.tobytes())
    page = doc[0]
    span = ops.span_at(page, (75, 95))
    choice = ops.match_font(doc, page, span, "xyz QRS")
    assert not choice.exact and choice.warning and "DejaVu" in choice.warning


def test_replace_span_text_keeps_neighbours(raw_text_doc):
    page = raw_text_doc[0]
    span = ops.span_at(page, (80, 65))
    choice = ops.replace_span_text(raw_text_doc, 0, span, "Chapter One")
    text = raw_text_doc[0].get_text()
    assert "Chapter One" in text and "Page 1" not in text
    assert "The quick brown fox" in text and choice.exact
    new_span = ops.span_at(raw_text_doc[0], (80, 65))
    assert new_span.size == pytest.approx(24) and new_span.origin.y == pytest.approx(72)


def test_replace_span_text_with_empty_deletes(raw_text_doc):
    span = ops.span_at(raw_text_doc[0], (80, 65))
    ops.replace_span_text(raw_text_doc, 0, span, "")
    assert "Page 1" not in raw_text_doc[0].get_text()


def test_replace_span_text_unicode_fallback(raw_text_doc):
    span = ops.span_at(raw_text_doc[0], (80, 65))
    choice = ops.replace_span_text(raw_text_doc, 0, span, "中文标题")
    assert choice.fontname == ops.FALLBACK_FONT and choice.warning
    assert "中文标题" in raw_text_doc[0].get_text()


def test_replace_span_on_rotated_text_direction():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((100, 300), "Sideways", fontsize=14, rotate=90)
    span = ops.text_spans(page)[0]
    ops.replace_span_text(doc, 0, span, "Upwards")
    assert "Upwards" in doc[0].get_text()


def test_text_box_height():
    one = ops.text_box_height("short", "helv", 12, 300)
    many = ops.text_box_height("word " * 200, "helv", 12, 300)
    assert many > one * 5


def test_text_box_height_paragraphs():
    assert ops.text_box_height("a\nb\nc", "helv", 10, 100) == pytest.approx(3 * 12 + 5)


def test_add_text_alignment_and_growth(raw_text_doc):
    page = raw_text_doc[0]
    box = ops.add_text(page, (100, 400, 300, 410), "Centered text that will need more than one line to fit",
                       family="Times", bold=True, fontsize=14, color=(1, 0, 0), align="center")
    assert box.height > 10
    span = [s for s in ops.text_spans(raw_text_doc[0]) if s.text.startswith("Centered")][0]
    assert span.font == "Times-Bold" and span.color == (1.0, 0.0, 0.0)


def test_add_text_validation(raw_text_doc):
    page = raw_text_doc[0]
    with pytest.raises(InvalidInput):
        ops.add_text(page, (0, 0, 100, 100), "  ")
    with pytest.raises(InvalidInput):
        ops.add_text(page, (0, 0, 100, 100), "x", align="diagonal")
    with pytest.raises(InvalidInput):
        ops.add_text(page, (0, 0, 100, 100), "x", fontfile="/no/such/font.ttf")


def test_add_text_custom_font_file(raw_text_doc):
    import os

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if not os.path.exists(font_path):
        pytest.skip("DejaVu font not installed")
    ops.add_text(raw_text_doc[0], (72, 600, 400, 650), "Custom font text", fontfile=font_path)
    assert any("DejaVu" in s.font for s in ops.text_spans(raw_text_doc[0]))


# -- images -------------------------------------------------------------------------
def test_load_image_bytes_converts_formats(tmp_path):
    path = tmp_path / "pic.bmp"
    Image.new("RGB", (10, 10), (1, 2, 3)).save(path)
    data = img_ops.load_image_bytes(str(path))
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_load_image_bytes_rejects_garbage():
    with pytest.raises(InvalidInput):
        img_ops.load_image_bytes(b"nope")


def test_image_size_and_fit_rect():
    assert img_ops.image_size(builders.png_bytes(200, 100)) == (200, 100)
    assert img_ops.fit_rect((0, 0, 100, 100), 200, 100) == pymupdf.Rect(0, 25, 100, 75)


def test_fit_rect_tall_image():
    assert img_ops.fit_rect((0, 0, 100, 100), 50, 100) == pymupdf.Rect(25, 0, 75, 100)


def test_insert_image_and_list(raw_text_doc):
    page = raw_text_doc[0]
    xref = img_ops.insert_image(page, (100, 300, 300, 400), builders.png_bytes(200, 100))
    imgs = img_ops.page_images(raw_text_doc[0])
    assert imgs[0].xref == xref and imgs[0].bbox == pymupdf.Rect(100, 300, 300, 400)


def test_insert_image_too_small(raw_text_doc):
    with pytest.raises(InvalidInput):
        img_ops.insert_image(raw_text_doc[0], (0, 0, 0.5, 0.5), builders.png_bytes())


def test_page_images_none(raw_text_doc):
    assert img_ops.page_images(raw_text_doc[0]) == []


def test_image_at(raw_text_doc):
    img_ops.insert_image(raw_text_doc[0], (100, 300, 300, 400), builders.png_bytes(200, 100))
    page = raw_text_doc[0]
    assert img_ops.image_at(page, (150, 350)) is not None and img_ops.image_at(page, (10, 10)) is None


def test_move_image_keeps_orientation(raw_text_doc):
    page = raw_text_doc[0]
    img_ops.insert_image(page, (100, 100, 200, 200), two_tone_png())
    image = img_ops.page_images(raw_text_doc[0])[0]
    img_ops.move_image(raw_text_doc[0], image, (300, 400, 450, 550))
    page = raw_text_doc[0]
    assert img_ops.page_images(page)[0].bbox == pymupdf.Rect(300, 400, 450, 550)
    pix = page.get_pixmap()
    assert pix.pixel(375, 410) == (255, 0, 0) and pix.pixel(375, 540) == (0, 0, 255)


def test_move_image_refuses_shared_placement(raw_text_doc):
    page = raw_text_doc[0]
    data = builders.png_bytes()
    img_ops.insert_image(page, (100, 100, 200, 200), data)
    img_ops.insert_image(raw_text_doc[0], (300, 300, 400, 400), data)  # same xref drawn twice
    image = img_ops.page_images(raw_text_doc[0])[0]
    with pytest.raises(UnsupportedOperation):
        img_ops.move_image(raw_text_doc[0], image, (0, 0, 50, 50))


def test_find_image(raw_text_doc):
    xref = img_ops.insert_image(raw_text_doc[0], (100, 100, 200, 200), builders.png_bytes())
    assert img_ops.find_image(raw_text_doc[0], xref, (101, 99, 0, 0)).xref == xref


def test_find_image_missing(raw_text_doc):
    with pytest.raises(InvalidInput):
        img_ops.find_image(raw_text_doc[0], 9999, (0, 0, 1, 1))


def test_trim_image():
    im = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    im.paste((0, 0, 0, 255), (50, 40, 80, 60))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    trimmed = img_ops.trim_image(buf.getvalue(), padding=0)
    assert img_ops.image_size(trimmed) == (30, 20)


def test_trim_image_empty():
    buf = io.BytesIO()
    Image.new("RGBA", (20, 20), (0, 0, 0, 0)).save(buf, "PNG")
    with pytest.raises(InvalidInput):
        img_ops.trim_image(buf.getvalue())


def test_white_to_transparent():
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 255, 255)).save(buf, "PNG")
    out = Image.open(io.BytesIO(img_ops.white_to_transparent(buf.getvalue())))
    assert out.getpixel((0, 0))[3] == 0


def test_white_to_transparent_keeps_ink():
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 10, 10)).save(buf, "PNG")
    out = Image.open(io.BytesIO(img_ops.white_to_transparent(buf.getvalue())))
    assert out.getpixel((0, 0))[3] == 255


def test_styled_image_opacity_and_rotation():
    data = img_ops.styled_image(builders.png_bytes(200, 100), opacity=0.5, rotation=90)
    out = Image.open(io.BytesIO(data))
    assert out.size == (100, 200) and out.getpixel((50, 100))[3] == 127


def test_styled_image_invalid_opacity():
    with pytest.raises(InvalidInput):
        img_ops.styled_image(builders.png_bytes(), opacity=0)


# -- document-level undo --------------------------------------------------------------
def test_replace_text_undo_and_insert_image_on_rotated_page(text_pdf):
    doc = PdfDocument.open(text_pdf)
    span = doc.text_span_at(0, (80, 65))
    doc.replace_text(span, "Edited")
    assert "Edited" in doc.raw[0].get_text()
    doc.history.undo()
    assert "Page 1" in doc.raw[0].get_text() and "Edited" not in doc.raw[0].get_text()
    doc.rotate_pages([1], 90)
    rect = (pymupdf.Rect(100, 100, 300, 200) * doc.raw[1].derotation_matrix).normalize()  # visual box
    doc.insert_image(1, rect, two_tone_png())
    page = doc.raw[1]
    pix = page.get_pixmap()  # rendered as displayed: red must be on top
    assert pix.pixel(200, 110) == (255, 0, 0) and pix.pixel(200, 190) == (0, 0, 255)
    image = doc.page_images(1)[0]
    doc.move_image(1, image, image.bbox + (10, 10, 10, 10))
    doc.history.undo()
    assert doc.page_images(1)[0].bbox == image.bbox


def test_add_text_upright_on_rotated_page():
    doc = pymupdf.open()
    page = doc.new_page()
    page.set_rotation(90)
    page = doc[0]
    visual = pymupdf.Rect(72, 72, 400, 90)
    ops.add_text(page, (visual * page.derotation_matrix).normalize(), "Upright text on a rotated page")
    page = doc[0]
    line = page.get_text("dict")["blocks"][0]["lines"][0]
    v = pymupdf.Point(line["dir"]) * page.rotation_matrix - pymupdf.Point(0, 0) * page.rotation_matrix
    assert round(v.x) == 1 and round(v.y) == 0
