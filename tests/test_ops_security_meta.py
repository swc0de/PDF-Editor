"""Tests for core.operations.security and core.operations.metadata."""

from __future__ import annotations

import pymupdf
import pytest

from pdf_editor.core.errors import InvalidInput
from pdf_editor.core.operations import metadata as meta
from pdf_editor.core.operations import security as sec


def test_permissions_value_and_describe():
    value = sec.permissions_value(["print", "copy"])
    assert value == pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_COPY
    described = sec.describe_permissions(value)
    assert described["print"] and described["copy"] and not described["modify"]


def test_permissions_value_unknown_name():
    with pytest.raises(InvalidInput):
        sec.permissions_value(["teleport"])


def test_describe_permissions_all_denied():
    assert not any(sec.describe_permissions(0).values())


def test_settings_validate():
    sec.EncryptionSettings("owner", "user").validate()
    with pytest.raises(InvalidInput):
        sec.EncryptionSettings("").validate()
    with pytest.raises(InvalidInput):
        sec.EncryptionSettings("same", "same", frozenset({"print"})).validate()


def test_encryption_save_kwargs_variants():
    assert sec.encryption_save_kwargs(sec.KEEP_ENCRYPTION) == {"encryption": pymupdf.PDF_ENCRYPT_KEEP}
    assert sec.encryption_save_kwargs(None) == {"encryption": pymupdf.PDF_ENCRYPT_NONE}
    kw = sec.encryption_save_kwargs(sec.EncryptionSettings("o", "u", frozenset({"print"})))
    assert kw["encryption"] == pymupdf.PDF_ENCRYPT_AES_256 and kw["permissions"] == pymupdf.PDF_PERM_PRINT


def test_encryption_save_kwargs_invalid_settings():
    with pytest.raises(InvalidInput):
        sec.encryption_save_kwargs(sec.EncryptionSettings(""))


def test_save_encrypted_aes256(raw_text_doc, tmp_path):
    out = str(tmp_path / "enc.pdf")
    sec.save_encrypted(raw_text_doc, out, sec.EncryptionSettings("owner", "user", frozenset({"print"})))
    doc = pymupdf.open(out)
    assert doc.needs_pass
    assert sec.authentication_level(doc, "user") == "user"
    assert "AES" in doc.metadata["encryption"] and "256" in doc.metadata["encryption"]
    assert not doc.permissions & pymupdf.PDF_PERM_MODIFY


def test_save_encrypted_without_user_password_opens_freely(raw_text_doc, tmp_path):
    out = str(tmp_path / "enc.pdf")
    sec.save_encrypted(raw_text_doc, out, sec.EncryptionSettings("owner", "", frozenset({"print"})))
    doc = pymupdf.open(out)
    assert not doc.needs_pass  # opens without password but is restricted
    assert not doc.permissions & pymupdf.PDF_PERM_COPY


def test_save_decrypted(encrypted_pdf, tmp_path):
    doc = pymupdf.open(encrypted_pdf)
    doc.authenticate("owner")
    out = str(tmp_path / "plain.pdf")
    sec.save_decrypted(doc, out)
    plain = pymupdf.open(out)
    assert not plain.needs_pass and "Secret content" in plain[0].get_text()


def test_save_decrypted_requires_unlock(encrypted_pdf, tmp_path):
    doc = pymupdf.open(encrypted_pdf)
    with pytest.raises(InvalidInput):
        sec.save_decrypted(doc, str(tmp_path / "x.pdf"))


def test_authentication_level(encrypted_pdf):
    assert sec.authentication_level(pymupdf.open(encrypted_pdf), "owner") == "owner"
    assert sec.authentication_level(pymupdf.open(encrypted_pdf), "user") == "user"


def test_authentication_level_wrong_and_unencrypted(encrypted_pdf, raw_text_doc):
    assert sec.authentication_level(pymupdf.open(encrypted_pdf), "nope") == "none"
    assert sec.authentication_level(raw_text_doc, "anything") == "owner"


def test_has_full_permissions(encrypted_pdf, raw_text_doc):
    assert sec.has_full_permissions(raw_text_doc)
    doc = pymupdf.open(encrypted_pdf)
    doc.authenticate("user")
    assert not sec.has_full_permissions(doc)


def test_get_metadata(raw_text_doc):
    data = meta.get_metadata(raw_text_doc)
    assert data["title"] == "Sample" and data["author"] == "Tester" and data["keywords"] == ""


def test_get_metadata_new_document():
    assert set(meta.get_metadata(pymupdf.open()).values()) == {""}


def test_set_metadata(raw_text_doc):
    meta.set_metadata(raw_text_doc, {"title": " New title ", "keywords": "a, b"})
    data = meta.get_metadata(raw_text_doc)
    assert data["title"] == "New title" and data["keywords"] == "a, b" and data["author"] == "Tester"


def test_set_metadata_unknown_field(raw_text_doc):
    with pytest.raises(InvalidInput):
        meta.set_metadata(raw_text_doc, {"colour": "blue"})


def test_document_info(raw_text_doc):
    info = meta.document_info(raw_text_doc)
    assert info["pages"] == "3" and info["format"].startswith("PDF")


def test_document_info_encrypted(encrypted_pdf):
    doc = pymupdf.open(encrypted_pdf)
    doc.authenticate("owner")
    assert "AES" in meta.document_info(doc)["encryption"]
