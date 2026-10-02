"""GUI tests: redaction, security, compression, OCR, exports, metadata, bookmarks."""

from __future__ import annotations

import os

import pymupdf
import pytest
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from pdf_editor.core.operations import ocr as ocr_ops
from tests.conftest import requires_tesseract
from tests.gui.helpers import drag

pytestmark = pytest.mark.gui


def test_redact_tool_and_dialog_apply(window, text_pdf, monkeypatch):
    tab = window.file.open_path(text_pdf)
    tab.set_tool("redact")
    drag(tab.active_tool, tab, 0, (60, 100), (320, 125))
    assert len(tab.doc.redaction_marks()) == 1
    from pdf_editor.app.dialogs.redaction import RedactionDialog

    dialog = RedactionDialog(tab, window)
    dialog.term.setText("marker 003")
    dialog.mark_term()
    assert dialog.list.count() == 2
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dialog.apply()
    assert "quick brown" not in tab.doc.raw[0].get_text() and "marker 003" not in tab.doc.raw[2].get_text()
    assert tab.doc.redaction_marks() == [] and tab.doc.needs_full_save


def test_protect_and_remove_password(window, text_pdf, tmp_path, monkeypatch):
    tab = window.file.open_path(text_pdf)
    from pdf_editor.app.dialogs import security

    def fill(dialog):
        dialog.user.setText("open")
        dialog.user_again.setText("open")
        dialog.owner.setText("boss")
        dialog.owner_again.setText("boss")
        return True

    monkeypatch.setattr(security.ProtectDialog, "exec", fill)
    window.tools.protect()
    out = str(tmp_path / "protected.pdf")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    window.file.save_as()
    check = pymupdf.open(out)
    assert check.needs_pass and check.authenticate("open") and "AES" in check.metadata["encryption"]
    check.close()
    # re-open the protected copy with the open password: editing security needs the owner password
    window.file.close_current()
    monkeypatch.setattr("pdf_editor.app.controllers.file_ops.ask_password", lambda *a: "open")
    tab = window.file.open_path(out)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("boss", True))
    window.tools.remove_password()
    tab.doc.save()
    assert not pymupdf.open(out).needs_pass


def test_compress_job(window, qtbot, image_pdf, tmp_path, monkeypatch):
    window.file.open_path(image_pdf)
    out = str(tmp_path / "small.pdf")
    from pdf_editor.app.dialogs import tools_dialogs

    monkeypatch.setattr(tools_dialogs.CompressDialog, "exec", lambda self: True)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    results = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: results.append(a[2]) or QMessageBox.StandardButton.No)
    window.tools.compress()
    qtbot.waitUntil(lambda: bool(results), timeout=60000)
    assert os.path.getsize(out) < os.path.getsize(image_pdf) and "smaller" in results[0]


def test_ocr_dialog_explains_missing_tesseract(window, text_pdf, monkeypatch):
    window.file.open_path(text_pdf)
    missing = ocr_ops.OcrStatus(False, None, (), "Tesseract OCR is not installed.\n\n" + ocr_ops.install_instructions())
    monkeypatch.setattr(ocr_ops, "tesseract_status", lambda tessdata=None: missing)
    window.refresh_ocr_action()
    assert "not installed" in window.actions["tools.ocr"].text()
    from pdf_editor.app.dialogs.tools_dialogs import OcrDialog

    seen = []
    monkeypatch.setattr(OcrDialog, "exec", lambda self: seen.append(self) or False)
    window.tools.ocr()
    dialog = seen[0]
    from PySide6.QtWidgets import QDialogButtonBox

    assert not dialog.box.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    assert not dialog.language.isEnabled()


@requires_tesseract
def test_ocr_job_makes_scan_searchable_with_undo(window, qtbot, scanned_pdf, monkeypatch):
    tab = window.file.open_path(scanned_pdf)
    from pdf_editor.app.dialogs import tools_dialogs

    monkeypatch.setattr(tools_dialogs.OcrDialog, "exec", lambda self: (self.dpi.setValue(150), True)[1])
    done = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: done.append(a[2]))
    window.tools.ocr()
    qtbot.waitUntil(lambda: bool(done), timeout=60000)
    assert "invoice" in tab.doc.raw[0].get_text()
    window.edit.undo()
    assert tab.doc.raw[0].get_text().strip() == ""


def test_export_images_and_text_jobs(window, qtbot, text_pdf, tmp_path, monkeypatch):
    window.file.open_path(text_pdf)
    from pdf_editor.app.dialogs import tools_dialogs

    folder = tmp_path / "pngs"
    folder.mkdir()

    def configure(dialog):
        dialog.folder.setText(str(folder))
        dialog.dpi.setValue(50)
        return True

    monkeypatch.setattr(tools_dialogs.ExportImagesDialog, "exec", configure)
    finished = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: finished.append(a[2]) or QMessageBox.StandardButton.No)
    window.tools.export_images()
    qtbot.waitUntil(lambda: bool(finished), timeout=60000)
    assert len(os.listdir(folder)) == 3
    txt = str(tmp_path / "doc.txt")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (txt, ""))
    window.tools.export_text()
    qtbot.waitUntil(lambda: "Exported" in window.statusBar().currentMessage(), timeout=60000)
    assert "Unique marker 002" in open(txt, encoding="utf-8").read()


def test_metadata_dialog(window, text_pdf, monkeypatch):
    tab = window.file.open_path(text_pdf)
    from pdf_editor.app.dialogs import metadata

    def edit(dialog):
        dialog.edits["title"].setText("Quarterly Report")
        dialog.edits["keywords"].setText("finance, q3")
        return True

    monkeypatch.setattr(metadata.MetadataDialog, "exec", edit)
    window.tools.edit_metadata()
    assert tab.doc.metadata()["title"] == "Quarterly Report" and tab.doc.metadata()["keywords"] == "finance, q3"
    window.edit.undo()
    assert tab.doc.metadata()["title"] == "Sample"


def test_bookmark_editing_through_panel(window, outline_pdf, monkeypatch):
    tab = window.file.open_path(outline_pdf)
    panel = window.outline
    tab.viewer.go_to_page(4)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Appendix", True))
    panel.tree.setCurrentItem(panel.tree.topLevelItem(1))
    panel.add_bookmark()
    assert [t[1] for t in tab.doc.raw.get_toc()] == ["Chapter 1", "Section 1.1", "Section 1.2", "Chapter 2", "Appendix"]
    panel.tree.setCurrentItem(panel.tree.topLevelItem(2))
    panel.indent()
    assert tab.doc.raw.get_toc()[-1][0] == 2  # nested under Chapter 2
    panel.tree.setCurrentItem(panel.tree.topLevelItem(0))
    panel.delete_bookmark()
    assert [t[1] for t in tab.doc.raw.get_toc()][0] == "Chapter 2"
    window.edit.undo()
    window.edit.undo()
    window.edit.undo()
    assert len(tab.doc.raw.get_toc()) == 4
