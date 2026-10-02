"""Tests for objstate, render, jobs and utils."""

from __future__ import annotations

import threading

import pymupdf
import pytest

from pdf_editor.core import jobs, objstate, render, utils
from pdf_editor.core.errors import InvalidInput, JobFailed, OperationCancelled


# -- objstate -------------------------------------------------------------
def test_capture_restore_page_objects(raw_text_doc):
    xrefs = objstate.page_object_xrefs(raw_text_doc, 0)
    state = objstate.capture_objects(raw_text_doc, xrefs)
    raw_text_doc[0].insert_text((72, 500), "EXTRA")
    raw_text_doc[0].add_rect_annot((10, 10, 40, 40))
    objstate.restore_objects(raw_text_doc, state)
    page = raw_text_doc[0]
    assert "EXTRA" not in page.get_text() and not list(page.annots())
    assert objstate.state_size(state) > 0


def test_capture_ignores_invalid_xrefs(raw_text_doc):
    assert objstate.capture_objects(raw_text_doc, [0, 10**6]) == {}


def test_annot_object_xrefs_includes_appearance(annotated_pdf):
    doc = pymupdf.open(annotated_pdf)
    annot = next(doc[0].annots())
    xrefs = objstate.annot_object_xrefs(doc, annot.xref)
    assert xrefs[0] == annot.xref and len(xrefs) >= 2


def test_annot_object_xrefs_widget_includes_siblings(form_pdf):
    doc = pymupdf.open(form_pdf)
    widget = next(w for w in doc[0].widgets() if w.field_type == pymupdf.PDF_WIDGET_TYPE_CHECKBOX)
    assert widget.xref in objstate.annot_object_xrefs(doc, widget.xref)


# -- render ---------------------------------------------------------------
def test_render_page_scale(raw_text_doc):
    out = render.render_page(raw_text_doc, 0, 0.5)
    assert (out.width, out.height) == (round(595 * 0.5), 421) and len(out.samples) == out.stride * out.height


def test_render_page_clamps_huge_scale(raw_text_doc):
    out = render.render_page(raw_text_doc, 0, 50, max_pixels=1_000_000)
    assert out.width * out.height <= 1_000_000 * 1.01 and out.scale < 50


def test_render_clip_on_rotated_page():
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.draw_rect((0, 0, 100, 50), fill=(1, 0, 0))  # top-left block, unrotated
    page.set_rotation(90)  # block is now shown at the visual top-right
    out = render.render_page(doc, 0, 1.0, clip=(750, 0, 800, 100))
    assert (out.width, out.height) == (50, 100)
    center = 50 * out.stride + 25 * 3
    assert out.samples[center : center + 3] == bytes([255, 0, 0])


def test_page_sizes_reflect_rotation(raw_text_doc):
    raw_text_doc[1].set_rotation(90)
    sizes = render.page_sizes(raw_text_doc)
    assert sizes[0] == (595, 842) and sizes[1] == (842, 595)


def test_effective_scale_no_clamp_for_small_pages():
    assert render.effective_scale(pymupdf.Rect(0, 0, 100, 100), 2.0) == 2.0


# -- jobs -----------------------------------------------------------------
def test_run_job_inline_progress():
    seen = []
    result = jobs.run_job(
        "tests.job_targets:count_to", {"n": 3}, on_progress=lambda d, t, m: seen.append(d), in_process=False
    )
    assert result == 3 and seen == [0, 1, 2]


def test_run_job_in_subprocess():
    seen = []
    assert jobs.run_job("tests.job_targets:count_to", {"n": 4}, on_progress=lambda d, t, m: seen.append(d)) == 4
    assert seen == [0, 1, 2, 3]


def test_run_job_subprocess_error_type_is_preserved():
    with pytest.raises(InvalidInput):
        jobs.run_job("tests.job_targets:fail_invalid", {})


def test_run_job_subprocess_crash_becomes_job_failed():
    with pytest.raises(JobFailed):
        jobs.run_job("tests.job_targets:crash", {})


def test_run_job_cancel_subprocess():
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(OperationCancelled):
        jobs.run_job("tests.job_targets:slow", {"seconds": 30}, cancel=cancel)


def test_resolve_target_invalid():
    with pytest.raises(ValueError):
        jobs.resolve_target("no_colon_here")


# -- utils ----------------------------------------------------------------
def test_color_conversions():
    assert utils.rgb_from_hex("#ff0000") == (1.0, 0.0, 0.0)
    assert utils.rgb_from_hex("0f0") == (0.0, 1.0, 0.0)
    assert utils.hex_from_rgb((0, 0, 1)) == "#0000ff"
    assert utils.hex_from_rgb((0.5,)) == "#808080"
    assert utils.hex_from_rgb((0, 0, 0, 1)) == "#000000"
    assert utils.rgb_from_int(0x00FF00) == (0.0, 1.0, 0.0)


def test_color_conversion_errors():
    with pytest.raises(InvalidInput):
        utils.rgb_from_hex("nothex")
    assert utils.hex_from_rgb(None) is None and utils.hex_from_rgb((1, 2)) is None


def test_parse_page_ranges():
    assert utils.parse_page_ranges("1-3, 5, 8-", 9) == [[0, 1, 2], [4], [7, 8]]
    assert utils.parse_page_ranges("-2; 3-2", 5) == [[0, 1], [2, 1]]


@pytest.mark.parametrize("spec", ["", "0", "4-12", "a-b", "1,,x"])
def test_parse_page_ranges_invalid(spec):
    with pytest.raises(InvalidInput):
        utils.parse_page_ranges(spec, 10)


def test_normalize_pages():
    assert utils.normalize_pages([2, 0, 2], 3) == [0, 2]
    assert utils.normalize_pages(None, 2) == [0, 1]
    with pytest.raises(InvalidInput):
        utils.normalize_pages([3], 3)


def test_format_size_and_file_size(tmp_path):
    assert utils.format_size(512) == "512 bytes"
    assert utils.format_size(1536) == "1.5 KB"
    assert utils.format_size(5 * 1024**3) == "5.0 GB"
    f = tmp_path / "f.bin"
    f.write_bytes(b"abc")
    assert utils.file_size(str(f)) == 3 and utils.file_size(str(tmp_path / "missing")) == 0


def test_coordinate_helpers_roundtrip(raw_text_doc):
    page = raw_text_doc[0]
    page.set_rotation(90)
    point = pymupdf.Point(50, 80)
    visual = utils.page_to_visual(page, point)
    assert utils.visual_to_page(page, visual) == point
    rect = utils.visual_rect_to_page(page, (0, 0, 100, 50))
    assert rect.width == pytest.approx(50) and rect.height == pytest.approx(100)


def test_safe_filename():
    assert utils.safe_filename('a/b:c*?.pdf') == "a_b_c__.pdf"
    assert utils.safe_filename("...") == "document"


def test_normalized_rect():
    assert utils.normalized_rect(10, 20, 0, 5) == pymupdf.Rect(0, 5, 10, 20)


def test_core_never_imports_pyside6():
    """The core layer must stay GUI-free (checked in a fresh interpreter)."""
    import subprocess
    import sys

    code = (
        "import importlib, pkgutil, sys, pdf_editor.core as core\n"
        "for m in pkgutil.walk_packages(core.__path__, 'pdf_editor.core.'):\n"
        "    importlib.import_module(m.name)\n"
        "print('PySide6' in sys.modules)\n"
    )
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=root, check=True)
    assert out.stdout.strip() == "False"
