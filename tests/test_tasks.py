"""Tests for the file-based job entry points in core.tasks."""

from __future__ import annotations

import os

import pymupdf
import pytest

from pdf_editor.core import tasks
from pdf_editor.core.errors import InvalidInput, PasswordRequired
from tests.fixtures import builders


def test_open_source_unlocks(encrypted_pdf):
    doc = tasks.open_source(encrypted_pdf, "user")
    assert doc.page_count == 1


def test_open_source_wrong_password(encrypted_pdf):
    with pytest.raises(PasswordRequired):
        tasks.open_source(encrypted_pdf, "nope")


def test_merge_task(tmp_path):
    a = builders.text_pdf(str(tmp_path / "a.pdf"), pages=1)
    b = builders.text_pdf(str(tmp_path / "b.pdf"), pages=2)
    out = str(tmp_path / "m.pdf")
    assert tasks.merge_task([a, b], out) == {"path": out, "pages": 3}


def test_merge_task_missing_file(tmp_path):
    with pytest.raises(Exception):
        tasks.merge_task([str(tmp_path / "missing.pdf")], str(tmp_path / "m.pdf"))


def test_split_task(ten_page_pdf, tmp_path):
    paths = tasks.split_task(ten_page_pdf, [[0, 1], [9]], str(tmp_path), "part")
    assert [pymupdf.open(p).page_count for p in paths] == [2, 1]
    assert all(os.path.dirname(p) == str(tmp_path) for p in paths)


def test_split_task_rejects_bad_pages(text_pdf, tmp_path):
    with pytest.raises(InvalidInput):
        tasks.split_task(text_pdf, [[0, 7]], str(tmp_path), "part")
