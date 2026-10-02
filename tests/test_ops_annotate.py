"""Tests for core.operations.annotate and the undoable annotation edits."""

from __future__ import annotations

import pymupdf
import pytest

from pdf_editor.core.document import PdfDocument
from pdf_editor.core.errors import InvalidInput
from pdf_editor.core.operations import annotate as ops
from tests.fixtures import builders


@pytest.fixture
def page(raw_text_doc):
    return raw_text_doc[0]


def kinds(page):
    return [a.type[1] for a in page.annots()]


def test_add_text_markup(page):
    quads = page.search_for("quick brown", quads=True)
    xref = ops.add_text_markup(page, "highlight", quads, (0, 1, 0), opacity=0.5, author="Me", text="note")
    annot = page.load_annot(xref)
    assert annot.type[1] == "Highlight" and annot.info["title"] == "Me" and annot.opacity == pytest.approx(0.5)
    for kind, name in (("underline", "Underline"), ("strikeout", "StrikeOut"), ("squiggly", "Squiggly")):
        assert page.load_annot(ops.add_text_markup(page, kind, quads)).type[1] == name


def test_add_text_markup_errors(page):
    with pytest.raises(InvalidInput):
        ops.add_text_markup(page, "glow", [pymupdf.Rect(0, 0, 10, 10)])
    with pytest.raises(InvalidInput):
        ops.add_text_markup(page, "highlight", [])


def test_add_ink(page):
    xref = ops.add_ink(page, [[(10, 10), (50, 60), (90, 20)], [(100, 100), (120, 140)]], (0, 0, 1), 3)
    annot = page.load_annot(xref)
    assert annot.type[1] == "Ink" and len(annot.vertices) == 2 and annot.border["width"] == 3


def test_add_ink_rejects_dots(page):
    with pytest.raises(InvalidInput):
        ops.add_ink(page, [[(10, 10)]])


@pytest.mark.parametrize("kind,expected", [("rect", "Square"), ("ellipse", "Circle"), ("line", "Line"), ("arrow", "Line")])
def test_add_shape(page, kind, expected):
    xref = ops.add_shape(page, kind, (300, 300), (400, 380), (1, 0, 0), fill=(0, 0, 1) if kind == "rect" else None)
    annot = page.load_annot(xref)
    assert annot.type[1] == expected
    if kind == "arrow":
        assert annot.line_ends[1] == pymupdf.PDF_ANNOT_LE_CLOSED_ARROW
    if kind == "rect":
        assert annot.colors["fill"] == [0.0, 0.0, 1.0]


def test_add_shape_invalid(page):
    with pytest.raises(InvalidInput):
        ops.add_shape(page, "star", (0, 0), (10, 10))
    with pytest.raises(InvalidInput):
        ops.add_shape(page, "rect", (10, 10), (10.2, 10.2))
    with pytest.raises(InvalidInput):
        ops.add_shape(page, "line", (5, 5), (5, 5))


def test_add_sticky_note(page):
    xref = ops.add_sticky_note(page, (500, 500), "Remember this", icon="Comment", author="Ann")
    annot = page.load_annot(xref)
    assert annot.type[1] == "Text" and annot.info["content"] == "Remember this"


def test_add_sticky_note_bad_icon(page):
    with pytest.raises(InvalidInput):
        ops.add_sticky_note(page, (10, 10), "x", icon="Rocket")


def test_add_text_box(page):
    xref = ops.add_text_box(page, (100, 400, 300, 450), "Boxed text", 14, (0, 0, 1), (1, 1, 0.8), 1)
    info = ops.annotation_info(page, page.load_annot(xref))
    assert info.kind == "FreeText" and info.contents == "Boxed text"
    assert info.text_color == "#0000ff" and info.fill == "#ffffcc"


def test_add_text_box_rejects_empty(page):
    with pytest.raises(InvalidInput):
        ops.add_text_box(page, (0, 0, 100, 100), "   ")
    with pytest.raises(InvalidInput):
        ops.add_text_box(page, (0, 0, 2, 2), "x")


def test_add_stamp(page):
    xref = ops.add_stamp(page, (100, 600, 300, 660), "Confidential")
    annot = page.load_annot(xref)
    assert annot.type[1] == "Stamp" and annot.info["content"] == "Confidential"


def test_add_stamp_unknown(page):
    with pytest.raises(InvalidInput):
        ops.add_stamp(page, (0, 0, 10, 10), "Banana")


def test_add_image_stamp(page):
    xref = ops.add_image_stamp(page, (100, 100, 300, 300), builders.png_bytes(200, 100))
    annot = page.load_annot(xref)
    assert annot.type[1] == "Stamp" and annot.rect.height == pytest.approx(100, abs=1)  # aspect kept


def test_add_image_stamp_invalid_data(page):
    with pytest.raises(InvalidInput):
        ops.add_image_stamp(page, (0, 0, 50, 50), b"not an image")


def test_list_annotations_and_info(annotated_pdf):
    doc = pymupdf.open(annotated_pdf)
    infos = ops.list_annotations(doc)
    assert [i.kind for i in infos] == ["Highlight", "Square", "Text"]
    square = infos[1]
    assert square.stroke == "#ff0000" and square.page == 0
    assert infos[2].label.startswith("Text: “A sticky note")


def test_list_annotations_none(raw_text_doc):
    assert ops.list_annotations(raw_text_doc) == []


def test_annotation_info_freetext_colors(page):
    xref = ops.add_text_box(page, (10, 10, 200, 60), "x", text_color=(1, 0, 0))
    assert ops.annotation_info(page, page.load_annot(xref)).text_color == "#ff0000"


def test_annotation_info_label_truncates(page):
    xref = ops.add_sticky_note(page, (10, 10), "word " * 40)
    assert len(ops.annotation_info(page, page.load_annot(xref)).label) < 80


def test_annot_at(page):
    lower = ops.add_shape(page, "rect", (100, 100), (300, 300))
    upper = ops.add_shape(page, "rect", (150, 150), (250, 250))
    assert ops.annot_at(page, (200, 200)) == upper
    assert ops.annot_at(page, (110, 110)) == lower


def test_annot_at_misses(page):
    assert ops.annot_at(page, (5, 5)) is None


def test_set_annotation_rect_box_and_vertices(page):
    rect_xref = ops.add_shape(page, "rect", (100, 100), (200, 200))
    ops.set_annotation_rect(page, rect_xref, (300, 300, 500, 350))
    assert page.load_annot(rect_xref).rect.tl == pymupdf.Point(300, 300)
    ink = ops.add_ink(page, [[(100, 100), (200, 200)]], width=2)
    old = page.load_annot(ink).rect
    ops.set_annotation_rect(page, ink, old + (100, 50, 100, 50))
    moved = page.load_annot(ink)
    assert moved.vertices[0][0] == pytest.approx((200, 150), abs=0.01)


def test_set_annotation_rect_on_cropped_page_line():
    doc = pymupdf.open()
    page = doc.new_page()
    page.set_cropbox(pymupdf.Rect(50, 50, 500, 700))
    page = doc[0]
    xref = ops.add_shape(page, "line", (100, 100), (200, 150))
    old = page.load_annot(xref).rect
    ops.set_annotation_rect(page, xref, old + (10, 20, 10, 20))
    assert page.load_annot(xref).vertices[0] == pytest.approx((110, 120), abs=0.01)


def test_set_annotation_rect_errors(page):
    xref = ops.add_shape(page, "rect", (100, 100), (200, 200))
    with pytest.raises(InvalidInput):
        ops.set_annotation_rect(page, xref, (10, 10, 10, 10))
    with pytest.raises(InvalidInput):
        ops.set_annotation_rect(page, 99999, (0, 0, 50, 50))


def test_move_annotation(page):
    xref = ops.add_stamp(page, (100, 100, 300, 160), "Draft")
    before = page.load_annot(xref).rect
    ops.move_annotation(page, xref, 10, -5)
    after = page.load_annot(xref).rect
    assert after.x0 == pytest.approx(before.x0 + 10) and after.y0 == pytest.approx(before.y0 - 5)


def test_repeated_moves_do_not_drift(page):
    xref = ops.add_shape(page, "rect", (100, 100), (200, 200), width=4)
    start = page.load_annot(xref).rect
    for _ in range(5):
        ops.move_annotation(page, xref, 10, 0)
    end = page.load_annot(xref).rect
    assert end.width == pytest.approx(start.width, abs=0.01) and end.x0 == pytest.approx(start.x0 + 50, abs=0.01)


def test_move_annotation_missing(page):
    with pytest.raises(InvalidInput):
        ops.move_annotation(page, 123456, 1, 1)


def test_set_annotation_style(page):
    xref = ops.add_shape(page, "rect", (100, 100), (200, 200), stroke=(1, 0, 0), fill=(0, 1, 0))
    ops.set_annotation_style(page, xref, stroke=(0, 0, 1), width=5, opacity=0.5)
    info = ops.annotation_info(page, page.load_annot(xref))
    assert info.stroke == "#0000ff" and info.fill == "#00ff00" and info.width == 5 and info.opacity == pytest.approx(0.5)
    ops.set_annotation_style(page, xref, fill=False)
    assert ops.annotation_info(page, page.load_annot(xref)).fill is None


def test_set_annotation_style_freetext(page):
    xref = ops.add_text_box(page, (10, 10, 200, 60), "x", fill_color=(1, 1, 1))
    ops.set_annotation_style(page, xref, stroke=(0, 0.5, 0), fill=(1, 0.8, 0.8))
    info = ops.annotation_info(page, page.load_annot(xref))
    assert info.text_color == "#008000" and info.fill == "#ffcccc"


def test_set_annotation_contents(page):
    xref = ops.add_sticky_note(page, (10, 10), "old")
    ops.set_annotation_contents(page, xref, "new text")
    assert page.load_annot(xref).info["content"] == "new text"


def test_set_annotation_contents_missing(page):
    with pytest.raises(InvalidInput):
        ops.set_annotation_contents(page, 4242, "x")


def test_delete_annotation(page):
    xref = ops.add_sticky_note(page, (10, 10), "bye")
    ops.delete_annotation(page, xref)
    assert kinds(page) == []


def test_delete_annotation_missing(page):
    with pytest.raises(InvalidInput):
        ops.delete_annotation(page, 4242)


# -- document level: undo and persistence -------------------------------------------
def test_annotation_undo_redo(text_pdf):
    doc = PdfDocument.open(text_pdf)

    def info():
        # load a fresh page each time: Page objects must not be kept across edits
        page = doc.raw[0]
        return ops.annotation_info(page, page.load_annot(xref))

    xref = doc.add_shape(0, "rect", (100, 100), (200, 200), (1, 0, 0))
    doc.set_annotation_style(0, xref, stroke=(0, 0, 1))
    doc.move_annotation(0, xref, 50, 0)
    doc.history.undo()
    assert info().rect.x0 == pytest.approx(99, abs=1.5)
    doc.history.undo()
    assert info().stroke == "#ff0000"
    doc.history.undo()
    assert kinds(doc.raw[0]) == []
    doc.history.redo()
    doc.history.redo()
    assert info().stroke == "#0000ff"
    doc.delete_annotation(0, xref)
    doc.history.undo()
    assert kinds(doc.raw[0]) == ["Square"]


def test_annotations_are_real_pdf_annotations(text_pdf, tmp_path):
    doc = PdfDocument.open(text_pdf)
    quads = doc.raw[0].search_for("lazy dog", quads=True)
    doc.add_text_markup(0, "highlight", quads, (1, 1, 0))
    doc.add_ink(0, [[(50, 500), (80, 540), (120, 520)]], (0, 0, 1), 2)
    doc.add_shape(0, "arrow", (300, 300), (400, 350), (1, 0, 0))
    doc.add_sticky_note(0, (500, 100), "Check this", (1, 0.8, 0))
    doc.add_text_box(0, (100, 600, 300, 650), "Text box", 12)
    doc.add_stamp(0, (300, 700, 500, 760), "Approved")
    out = str(tmp_path / "annotated.pdf")
    doc.save(out)
    fresh = pymupdf.open(out)
    page = fresh[0]
    assert sorted(kinds(page)) == sorted(["Highlight", "Ink", "Line", "Text", "FreeText", "Stamp"])
    for annot in page.annots():
        kind, _ = fresh.xref_get_key(annot.xref, "AP")
        assert kind != "null", f"{annot.type[1]} has no appearance stream"
