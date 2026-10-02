"""Tests for PdfDocument: opening, edit primitives, undo, saving."""

from __future__ import annotations

import os

import pymupdf
import pytest

from pdf_editor.core.document import PdfDocument
from pdf_editor.core.errors import PasswordRequired, PdfEditorError, PermissionDenied, WrongPassword
from pdf_editor.core.events import Change
from pdf_editor.core.operations.security import EncryptionSettings


def test_open_and_basic_properties(text_pdf):
    doc = PdfDocument.open(text_pdf)
    assert doc.page_count == 3
    assert doc.display_name == "text.pdf"
    assert not doc.is_modified
    doc.close()


def test_open_missing_file_raises_friendly_error(tmp_path):
    with pytest.raises(PdfEditorError):
        PdfDocument.open(str(tmp_path / "nope.pdf"))


def test_open_garbage_file_raises_friendly_error(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf at all")
    with pytest.raises(PdfEditorError):
        PdfDocument.open(str(bad))


def test_open_image_converts_to_pdf(png_file):
    doc = PdfDocument.open(png_file)
    assert doc.page_count == 1
    assert doc.path is None  # must be saved under a new name
    assert doc.display_name == "picture.pdf"


def test_password_handling(encrypted_pdf):
    with pytest.raises(PasswordRequired):
        PdfDocument.open(encrypted_pdf)
    with pytest.raises(WrongPassword):
        PdfDocument.open(encrypted_pdf, "wrong")
    doc = PdfDocument.open(encrypted_pdf, "owner")
    assert doc.is_encrypted


def test_user_password_restricts_modification(encrypted_pdf):
    doc = PdfDocument.open(encrypted_pdf, "user")
    with pytest.raises(PermissionDenied):
        doc.rotate_pages([0], 90)


def test_edit_pages_undo_redo_restores_content(text_pdf):
    doc = PdfDocument.open(text_pdf)
    events = []
    doc.add_listener(events.append)

    def add_text():
        doc.raw[0].insert_text((72, 300), "ADDED TEXT", fontsize=12)

    doc.edit_pages("Add text", [0], add_text)
    assert "ADDED TEXT" in doc.raw[0].get_text()
    assert doc.is_modified
    doc.history.undo()
    assert "ADDED TEXT" not in doc.raw[0].get_text()
    doc.history.redo()
    assert "ADDED TEXT" in doc.raw[0].get_text()
    assert events and events[0].kind == Change.CONTENT and events[0].pages == (0,)


def test_page_key_changes_after_edit(text_pdf):
    doc = PdfDocument.open(text_pdf)
    before, other = doc.page_key(0), doc.page_key(1)
    doc.edit_pages("x", [0], lambda: doc.raw[0].draw_rect((10, 10, 50, 50)))
    assert doc.page_key(0) != before
    assert doc.page_key(1) == other


def test_snapshot_edit_undo(text_pdf):
    doc = PdfDocument.open(text_pdf)
    doc.delete_pages([0, 1])
    assert doc.page_count == 1
    doc.history.undo()
    assert doc.page_count == 3
    assert "Page 1" in doc.raw[0].get_text()
    doc.history.redo()
    assert doc.page_count == 1


def test_failed_action_rolls_back_and_is_not_recorded(text_pdf):
    doc = PdfDocument.open(text_pdf)

    def broken():
        doc.raw[0].insert_text((72, 300), "PARTIAL")
        raise ValueError("fail")

    with pytest.raises(ValueError):
        doc.edit_pages("broken", [0], broken)
    assert "PARTIAL" not in doc.raw[0].get_text()
    assert not doc.is_modified


def test_save_incremental_then_full(tmp_path, text_pdf):
    doc = PdfDocument.open(text_pdf)
    doc.rotate_pages([0], 90)
    result = doc.save()
    assert result.incremental
    assert not doc.is_modified
    reopened = pymupdf.open(text_pdf)
    assert reopened[0].rotation == 90
    reopened.close()
    # deleting pages forces nothing special, but saving elsewhere is always full
    out = str(tmp_path / "copy.pdf")
    result = doc.save(out)
    assert not result.incremental and os.path.exists(out)
    assert doc.path == out


def test_full_save_to_original_keeps_history_valid(text_pdf):
    doc = PdfDocument.open(text_pdf)
    doc.require_full_save()
    doc.edit_pages("text", [0], lambda: doc.raw[0].insert_text((72, 400), "KEEP", fontsize=12))
    result = doc.save()
    assert not result.incremental
    # history still works after the in-place rewrite
    doc.history.undo()
    assert "KEEP" not in doc.raw[0].get_text()
    doc.history.redo()
    assert "KEEP" in doc.raw[0].get_text()
    check = pymupdf.open(text_pdf)
    assert "KEEP" in check[0].get_text()
    check.close()


def test_save_with_new_password(tmp_path, text_pdf):
    doc = PdfDocument.open(text_pdf)
    doc.set_encryption(EncryptionSettings(owner_password="own", user_password="usr"))
    out = str(tmp_path / "protected.pdf")
    doc.save(out)
    check = pymupdf.open(out)
    assert check.needs_pass
    assert check.authenticate("usr")
    check.close()


def test_save_keeps_existing_encryption(tmp_path, encrypted_pdf):
    doc = PdfDocument.open(encrypted_pdf, "owner")
    doc.rotate_pages([0], 90)
    out = str(tmp_path / "still_encrypted.pdf")
    doc.save(out)
    check = pymupdf.open(out)
    assert check.needs_pass and check.authenticate("user")
    assert check[0].rotation == 90


def test_new_document_is_modified_and_needs_path():
    doc = PdfDocument.new()
    assert doc.is_modified
    assert doc.page_count == 1
    with pytest.raises(PdfEditorError):
        doc.save()


def test_from_bytes_roundtrip(text_pdf):
    with open(text_pdf, "rb") as fh:
        doc = PdfDocument.from_bytes(fh.read(), name="mem.pdf")
    assert doc.page_count == 3 and doc.display_name == "mem.pdf"
    with pytest.raises(PdfEditorError):
        PdfDocument.from_bytes(b"junk")
