"""GUI tests: page operations, thumbnail drag & drop, jobs."""

from __future__ import annotations

import os

import pymupdf
import pytest
from PySide6.QtCore import QItemSelectionModel, QMimeData, QModelIndex, Qt, QUrl
from PySide6.QtWidgets import QFileDialog, QMessageBox

from tests.fixtures import builders

pytestmark = pytest.mark.gui


def first_lines(doc):
    return [doc.raw[i].get_text().split("\n")[0] for i in range(doc.page_count)]


def select(window, pages):
    sel = window.thumbnails.selectionModel()
    sel.clearSelection()
    for p in pages:
        sel.select(window.thumbnails.model().index(p, 0), QItemSelectionModel.SelectionFlag.Select)


def test_rotate_delete_duplicate_with_undo(window, ten_page_pdf):
    tab = window.file.open_path(ten_page_pdf)
    select(window, [1, 2])
    window.pages_ctl.rotate_right()
    assert [tab.doc.raw[p].rotation for p in (0, 1, 2)] == [0, 90, 90]
    assert tab.viewer.item(1).page_rect().width() > tab.viewer.item(0).page_rect().width()
    select(window, [0, 3])
    window.pages_ctl.delete_pages()
    assert tab.doc.page_count == 8
    window.edit.undo()
    assert tab.doc.page_count == 10 and tab.viewer.page_count == 10
    select(window, [4])
    window.pages_ctl.duplicate_pages()
    assert first_lines(tab.doc)[4:6] == ["Page 5", "Page 5"]
    assert tab.doc.is_modified and window.tabs.tabText(0).endswith("*")


def test_insert_blank_page_after_selection(window, text_pdf):
    tab = window.file.open_path(text_pdf)
    select(window, [0])
    window.pages_ctl.insert_blank()
    assert tab.doc.page_count == 4 and tab.doc.raw[1].get_text() == ""


def test_thumbnail_drop_reorders_pages(window, ten_page_pdf):
    tab = window.file.open_path(ten_page_pdf)
    model = tab.thumb_model
    data = model.mimeData([model.index(7), model.index(8)])
    model.dropMimeData(data, Qt.DropAction.MoveAction, 1, 0, QModelIndex())
    assert first_lines(tab.doc)[:4] == ["Page 1", "Page 8", "Page 9", "Page 2"]
    assert window.thumbnails.selected_pages() == [1, 2]
    window.edit.undo()
    assert first_lines(tab.doc)[:3] == ["Page 1", "Page 2", "Page 3"]


def test_files_dropped_on_thumbnails_are_inserted(window, text_pdf, png_file):
    tab = window.file.open_path(text_pdf)
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(png_file)])
    tab.thumb_model.dropMimeData(data, Qt.DropAction.CopyAction, 1, 0, QModelIndex())
    assert tab.doc.page_count == 4 and tab.doc.raw[1].get_images()


def test_insert_from_pdf_dialog(window, text_pdf, outline_pdf, monkeypatch):
    tab = window.file.open_path(text_pdf)
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([outline_pdf], ""))
    from pdf_editor.app.dialogs import insert_pages

    def fake_exec(dialog):
        dialog.start.setChecked(True)
        dialog.range.setText("2-3")
        return True

    monkeypatch.setattr(insert_pages.InsertPagesDialog, "exec", fake_exec)
    window.pages_ctl.insert_from_file()
    assert tab.doc.page_count == 5 and first_lines(tab.doc)[:2] == ["Page 2", "Page 3"]


def test_extract_pages(window, ten_page_pdf, tmp_path, monkeypatch):
    window.file.open_path(ten_page_pdf)
    out = str(tmp_path / "extract.pdf")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    select(window, [2, 5])
    window.pages_ctl.extract_pages()
    assert pymupdf.open(out).page_count == 2


def test_crop_margins_dialog(window, text_pdf, monkeypatch):
    tab = window.file.open_path(text_pdf)
    from pdf_editor.app.dialogs import crop

    def fake_exec(dialog):
        dialog.margins["left"].setValue(10)
        dialog.scope.setCurrentIndex(2)  # all pages
        return True

    monkeypatch.setattr(crop.CropDialog, "exec", fake_exec)
    window.pages_ctl.crop()
    mm10 = 10 * 72 / 25.4
    assert all(abs(tab.doc.raw[p].rect.width - (595 - mm10)) < 0.5 for p in range(3))
    window.edit.undo()
    assert tab.doc.raw[0].rect.width == 595


def test_crop_tool_draws_rectangle(window, qtbot, text_pdf, monkeypatch):
    tab = window.file.open_path(text_pdf)
    from pdf_editor.app.dialogs import crop

    monkeypatch.setattr(crop.CropDialog, "exec", lambda self: True)
    tab.set_tool("crop")
    tool = tab.active_tool
    from tests.gui.helpers import page_event

    tool.press(page_event(tab, 0, 100, 100))
    tool.move(page_event(tab, 0, 300, 400))
    tool.release(page_event(tab, 0, 300, 400))
    assert tab.doc.raw[0].rect == pymupdf.Rect(0, 0, 200, 300)


def test_split_job_runs_in_background(window, qtbot, ten_page_pdf, tmp_path, monkeypatch):
    window.file.open_path(ten_page_pdf)
    from pdf_editor.app.dialogs import split

    out_dir = tmp_path / "parts"
    out_dir.mkdir()

    def fake_exec(dialog):
        dialog.every.setChecked(True)
        dialog.every_n.setValue(3)
        dialog.folder.setText(str(out_dir))
        return True

    monkeypatch.setattr(split.SplitDialog, "exec", fake_exec)
    finished = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: finished.append(a[2]) or QMessageBox.StandardButton.No)
    window.pages_ctl.split()
    qtbot.waitUntil(lambda: bool(finished), timeout=30000)  # wait for the job's completion callback
    assert len(os.listdir(out_dir)) == 4 and "Created 4 file(s)" in finished[0]


def test_merge_job(window, qtbot, tmp_path, monkeypatch):
    a = builders.text_pdf(str(tmp_path / "a.pdf"), pages=2)
    b = builders.text_pdf(str(tmp_path / "b.pdf"), pages=3)
    out = str(tmp_path / "merged.pdf")
    from pdf_editor.app.dialogs import merge

    monkeypatch.setattr(merge.MergeDialog, "exec", lambda self: True)
    monkeypatch.setattr(merge.MergeDialog, "paths", lambda self: [b, a])
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.pages_ctl.merge()
    qtbot.waitUntil(lambda: window.tabs.count() == 1, timeout=30000)
    assert window.current_tab().doc.page_count == 5


def test_merge_dialog_ordering(qtbot, tmp_path):
    from pdf_editor.app.dialogs.merge import MergeDialog

    a = builders.text_pdf(str(tmp_path / "b_second.pdf"), pages=1)
    b = builders.text_pdf(str(tmp_path / "a_first.pdf"), pages=1)
    dialog = MergeDialog(str(tmp_path), [a, b])
    qtbot.addWidget(dialog)
    dialog.list.setCurrentRow(1)
    dialog.move_selected(-1)
    assert dialog.paths() == [b, a]
    dialog.sort_by_name()
    assert [os.path.basename(p) for p in dialog.paths()] == ["a_first.pdf", "b_second.pdf"]


def test_split_dialog_validation(qtbot, tmp_path):
    from pdf_editor.app.dialogs.split import SplitDialog

    dialog = SplitDialog(10, "doc", str(tmp_path))
    qtbot.addWidget(dialog)
    dialog.ranges.setText("1-3, 9-12")
    assert "out of range" in dialog.preview.text()
    dialog.ranges.setText("1-3, 4-")
    assert dialog.groups() == [[0, 1, 2], list(range(3, 10))]
