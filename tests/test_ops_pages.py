"""Tests for core.operations.pages (happy path + edge case per function)."""

from __future__ import annotations

import os

import pymupdf
import pytest

from pdf_editor.core.errors import InvalidInput, OperationCancelled
from pdf_editor.core.operations import pages as ops
from tests.fixtures import builders


def texts(doc):
    return [doc[i].get_text().split("\n")[0] for i in range(doc.page_count)]


# rotate_pages
def test_rotate_pages(raw_text_doc):
    ops.rotate_pages(raw_text_doc, [0, 2], 90)
    assert [p.rotation for p in raw_text_doc] == [90, 0, 90]
    ops.rotate_pages(raw_text_doc, [0], -90)
    assert raw_text_doc[0].rotation == 0


def test_rotate_pages_rejects_odd_angle(raw_text_doc):
    with pytest.raises(InvalidInput):
        ops.rotate_pages(raw_text_doc, [0], 45)


# delete_pages
def test_delete_pages(raw_text_doc):
    ops.delete_pages(raw_text_doc, [0, 2])
    assert texts(raw_text_doc) == ["Page 2"]


def test_delete_all_pages_refused(raw_text_doc):
    with pytest.raises(InvalidInput):
        ops.delete_pages(raw_text_doc, [0, 1, 2])


# duplicate_pages
def test_duplicate_pages(raw_text_doc):
    new = ops.duplicate_pages(raw_text_doc, [0, 2])
    assert new == [1, 4]
    assert texts(raw_text_doc) == ["Page 1", "Page 1", "Page 2", "Page 3", "Page 3"]
    # copies are independent objects
    assert raw_text_doc[0].xref != raw_text_doc[1].xref


def test_duplicate_invalid_page(raw_text_doc):
    with pytest.raises(InvalidInput):
        ops.duplicate_pages(raw_text_doc, [9])


# insert_blank_page
def test_insert_blank_page_copies_neighbour_size(raw_text_doc):
    ops.insert_blank_page(raw_text_doc, 1)
    assert raw_text_doc.page_count == 4
    assert raw_text_doc[1].get_text() == ""
    assert raw_text_doc[1].rect == raw_text_doc[0].rect


def test_insert_blank_page_at_end_and_bad_index(raw_text_doc):
    assert ops.insert_blank_page(raw_text_doc, 3, 200, 300) == 3
    assert raw_text_doc[3].rect == pymupdf.Rect(0, 0, 200, 300)
    with pytest.raises(InvalidInput):
        ops.insert_blank_page(raw_text_doc, 10)


# compute_move_order / reorder / inverse / move
def test_compute_move_order():
    assert ops.compute_move_order(5, [3], 0) == [3, 0, 1, 2, 4]
    assert ops.compute_move_order(5, [0, 1], 5) == [2, 3, 4, 0, 1]


def test_compute_move_order_invalid_target():
    with pytest.raises(InvalidInput):
        ops.compute_move_order(3, [0], 7)


def test_reorder_pages(raw_text_doc):
    ops.reorder_pages(raw_text_doc, [2, 0, 1])
    assert texts(raw_text_doc) == ["Page 3", "Page 1", "Page 2"]


def test_reorder_pages_rejects_incomplete_order(raw_text_doc):
    with pytest.raises(InvalidInput):
        ops.reorder_pages(raw_text_doc, [0, 0, 1])


def test_inverse_order_roundtrip(raw_text_doc):
    order = [2, 0, 1]
    ops.reorder_pages(raw_text_doc, order)
    ops.reorder_pages(raw_text_doc, ops.inverse_order(order))
    assert texts(raw_text_doc) == ["Page 1", "Page 2", "Page 3"]


def test_inverse_order_identity():
    assert ops.inverse_order([]) == []
    assert ops.inverse_order([0, 1]) == [0, 1]


def test_move_pages(raw_text_doc):
    ops.move_pages(raw_text_doc, [2], 0)
    assert texts(raw_text_doc) == ["Page 3", "Page 1", "Page 2"]


def test_move_pages_to_same_place_is_noop(raw_text_doc):
    xrefs = [p.xref for p in raw_text_doc]
    ops.move_pages(raw_text_doc, [1], 1)
    assert [p.xref for p in raw_text_doc] == xrefs


# insert_pdf_pages
def test_insert_pdf_pages(raw_text_doc, tmp_path):
    other = pymupdf.open(builders.text_pdf(str(tmp_path / "o.pdf"), pages=4))
    assert ops.insert_pdf_pages(raw_text_doc, other, 1, pages=[1, 2]) == 2
    assert texts(raw_text_doc) == ["Page 1", "Page 2", "Page 3", "Page 2", "Page 3"]


def test_insert_pdf_pages_bad_position(raw_text_doc, tmp_path):
    other = pymupdf.open(builders.text_pdf(str(tmp_path / "o.pdf"), pages=1))
    with pytest.raises(InvalidInput):
        ops.insert_pdf_pages(raw_text_doc, other, 99)


# image_to_pdf_bytes / insert_images_as_pages
def test_image_to_pdf_bytes(png_file):
    pdf = pymupdf.open("pdf", ops.image_to_pdf_bytes(png_file))
    assert pdf.page_count == 1
    assert pdf[0].get_images()


def test_image_to_pdf_bytes_rejects_non_image(tmp_path):
    bad = tmp_path / "x.png"
    bad.write_text("not an image")
    with pytest.raises(InvalidInput):
        ops.image_to_pdf_bytes(str(bad))


def test_insert_images_as_pages(raw_text_doc, png_file, jpg_file):
    assert ops.insert_images_as_pages(raw_text_doc, [png_file, jpg_file], 0, page_size=(595, 842), margin=20) == 2
    assert raw_text_doc.page_count == 5
    assert raw_text_doc[0].rect.width == 595 and raw_text_doc[0].get_images()


def test_insert_images_as_pages_empty_list(raw_text_doc):
    with pytest.raises(InvalidInput):
        ops.insert_images_as_pages(raw_text_doc, [], 0)


# extract_pages
def test_extract_pages_keeps_order(raw_text_doc):
    out = ops.extract_pages(raw_text_doc, [2, 0])
    assert texts(out) == ["Page 3", "Page 1"]


def test_extract_pages_requires_selection(raw_text_doc):
    with pytest.raises(InvalidInput):
        ops.extract_pages(raw_text_doc, [])


# merge_files
def test_merge_files(tmp_path):
    a = builders.text_pdf(str(tmp_path / "a.pdf"), pages=2)
    b = builders.text_pdf(str(tmp_path / "b.pdf"), pages=3)
    out = str(tmp_path / "merged.pdf")
    seen = []
    assert ops.merge_files([b, a], out, progress=lambda d, t, m: seen.append(d) or True) == 5
    merged = pymupdf.open(out)
    assert texts(merged)[:3] == ["Page 1", "Page 2", "Page 3"] and merged.page_count == 5
    assert seen


def test_merge_files_can_be_cancelled(tmp_path):
    a = builders.text_pdf(str(tmp_path / "a.pdf"), pages=1)
    with pytest.raises(OperationCancelled):
        ops.merge_files([a, a], str(tmp_path / "m.pdf"), progress=lambda d, t, m: False)


def test_merge_files_encrypted_needs_password(tmp_path, encrypted_pdf):
    with pytest.raises(InvalidInput):
        ops.merge_files([encrypted_pdf], str(tmp_path / "m.pdf"))
    assert ops.merge_files([encrypted_pdf], str(tmp_path / "m.pdf"), passwords={encrypted_pdf: "user"}) == 1


# split_every / split_document
def test_split_every():
    assert ops.split_every(5, 2) == [[0, 1], [2, 3], [4]]


def test_split_every_rejects_zero():
    with pytest.raises(InvalidInput):
        ops.split_every(5, 0)


def test_split_document(raw_ten_doc, tmp_path):
    paths = ops.split_document(raw_ten_doc, ops.split_every(10, 4), str(tmp_path / "parts"), "report")
    assert len(paths) == 3
    assert [pymupdf.open(p).page_count for p in paths] == [4, 4, 2]
    assert os.path.basename(paths[0]) == "report_1_p1-4.pdf"


def test_split_document_nothing_to_split(raw_text_doc, tmp_path):
    with pytest.raises(InvalidInput):
        ops.split_document(raw_text_doc, [], str(tmp_path), "x")


# crop_pages / crop_margins / reset_crop
def test_crop_pages(raw_text_doc):
    ops.crop_pages(raw_text_doc, [0], (50, 50, 300, 400))
    assert raw_text_doc[0].rect == pymupdf.Rect(0, 0, 250, 350)
    # cropping again is relative to the current visible area
    ops.crop_pages(raw_text_doc, [0], (0, 0, 100, 100))
    assert raw_text_doc[0].cropbox == pymupdf.Rect(50, 50, 150, 150)


def test_crop_pages_outside_page(raw_text_doc):
    with pytest.raises(InvalidInput):
        ops.crop_pages(raw_text_doc, [0], (2000, 2000, 2100, 2100))


def test_crop_margins_respects_rotation(raw_text_doc):
    ops.rotate_pages(raw_text_doc, [0], 90)
    ops.crop_margins(raw_text_doc, [0], 10, 20, 30, 40)
    visual = raw_text_doc[0].rect
    assert visual.width == pytest.approx(842 - 40) and visual.height == pytest.approx(595 - 60)


def test_crop_margins_too_large(raw_text_doc):
    with pytest.raises(InvalidInput):
        ops.crop_margins(raw_text_doc, [0], 400, 0, 400, 0)


def test_reset_crop(raw_text_doc):
    ops.crop_pages(raw_text_doc, [1], (10, 10, 100, 100))
    ops.reset_crop(raw_text_doc, [1])
    assert raw_text_doc[1].rect == pymupdf.Rect(0, 0, 595, 842)


def test_reset_crop_invalid_page(raw_text_doc):
    with pytest.raises(InvalidInput):
        ops.reset_crop(raw_text_doc, [5])
