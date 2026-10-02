"""Tests for core.operations.text."""

from __future__ import annotations

import pymupdf
import pytest

from pdf_editor.core.errors import InvalidInput, OperationCancelled
from pdf_editor.core.operations import text as ops


def test_page_chars_reading_order(raw_text_doc):
    chars = ops.page_chars(raw_text_doc[0])
    assert "".join(c.char for c in chars).startswith("Page 1")
    assert all(not c.rect.is_empty for c in chars)


def test_page_chars_blank_page():
    doc = pymupdf.open()
    doc.new_page()
    assert ops.page_chars(doc[0]) == []


def test_nearest_char_prefers_line_under_cursor(raw_text_doc):
    chars = ops.page_chars(raw_text_doc[0])
    idx = ops.nearest_char(chars, (75, 115))  # just inside "The quick..." line
    assert chars[idx].char == "T"


def test_nearest_char_empty():
    assert ops.nearest_char([], (0, 0)) is None


def test_select_chars_across_lines(raw_text_doc):
    chars = ops.page_chars(raw_text_doc[0])
    sel = ops.select_chars(chars, (72, 115), (100, 136))
    assert sel.text.startswith("The quick")
    assert "\n" in sel.text
    assert len(sel.rects) == 2


def test_select_chars_no_text():
    sel = ops.select_chars([], (0, 0), (10, 10))
    assert sel.is_empty and sel.rects == ()


def test_selection_from_range_single_char(raw_text_doc):
    chars = ops.page_chars(raw_text_doc[0])
    sel = ops.selection_from_range(chars, 0, 0)
    assert sel.text == "P" and len(sel.quads) == 1


def test_selection_from_range_empty_range(raw_text_doc):
    chars = ops.page_chars(raw_text_doc[0])
    assert ops.selection_from_range(chars, 5, 4).text == ""


def test_select_text_backwards_drag(raw_text_doc):
    forward = ops.select_text(raw_text_doc[0], (72, 115), (200, 115))
    backward = ops.select_text(raw_text_doc[0], (200, 115), (72, 115))
    assert forward.text == backward.text and forward.text


def test_select_text_blank_page():
    doc = pymupdf.open()
    doc.new_page()
    assert ops.select_text(doc[0], (0, 0), (100, 100)).is_empty


def test_select_all(raw_text_doc):
    sel = ops.select_all(raw_text_doc[1])
    assert "Page 2" in sel.text and "Unique marker 002" in sel.text


def test_select_all_blank_page():
    doc = pymupdf.open()
    doc.new_page()
    assert ops.select_all(doc[0]).text == ""


def test_word_at(raw_text_doc):
    chars = ops.page_chars(raw_text_doc[0])
    rect = raw_text_doc[0].search_for("quick")[0]
    assert ops.word_at(chars, rect.tl + (2, 3)).text == "quick"


def test_word_at_whitespace_returns_empty(raw_text_doc):
    chars = ops.page_chars(raw_text_doc[0])
    space = next(c for c in chars if c.char == " ")
    assert ops.word_at(chars, space.rect.tl + (0.05, 1)).text == ""


def test_search_chars_case_insensitive_and_sensitive(raw_text_doc):
    chars = ops.page_chars(raw_text_doc[0])
    assert len(ops.search_chars(chars, "the")) == 2  # "The quick" and "the lazy"
    assert len(ops.search_chars(chars, "the", match_case=True)) == 1
    assert len(ops.search_chars(chars, "THE", match_case=True)) == 0


def test_search_chars_empty_query(raw_text_doc):
    assert ops.search_chars(ops.page_chars(raw_text_doc[0]), "   ") == []


def test_search_page_across_line_break(raw_text_doc):
    hits = ops.search_page(raw_text_doc[0], "dog. Pack")
    assert len(hits) == 1 and len(hits[0].rects) == 2


def test_search_page_no_match(raw_text_doc):
    assert ops.search_page(raw_text_doc[0], "zebra") == []


def test_search_document(raw_text_doc):
    results = ops.search_document(raw_text_doc, "marker 002")
    assert list(results) == [1]


def test_search_document_page_subset(raw_text_doc):
    assert ops.search_document(raw_text_doc, "marker 002", pages=[0, 2]) == {}


def test_page_text(raw_text_doc):
    assert "Page 3" in ops.page_text(raw_text_doc[2])


def test_page_text_blank():
    doc = pymupdf.open()
    doc.new_page()
    assert ops.page_text(doc[0]) == ""


def test_extract_text_with_separators(raw_text_doc):
    text = ops.extract_text(raw_text_doc)
    assert text.count("--- Page") == 3 and "Unique marker 003" in text


def test_extract_text_cancel(raw_text_doc):
    with pytest.raises(OperationCancelled):
        ops.extract_text(raw_text_doc, progress=lambda d, t, m: False)


def test_export_text(raw_text_doc, tmp_path):
    path = tmp_path / "out" / "doc.txt"
    count = ops.export_text(raw_text_doc, str(path), separators=False)
    content = path.read_text(encoding="utf-8")
    assert count == len(content) and "\f" in content and "Page 2" in content


def test_export_text_requires_path(raw_text_doc):
    with pytest.raises(InvalidInput):
        ops.export_text(raw_text_doc, "")
