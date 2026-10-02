"""GUI tests: saving, prompts, autosave recovery, settings, shortcuts, errors."""

from __future__ import annotations

import os

import pymupdf
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog, QMessageBox

from pdf_editor.app import autosave
from pdf_editor.settings import Settings

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def isolated_recovery(tmp_path, monkeypatch):
    folder = tmp_path / "recovery"
    folder.mkdir()
    monkeypatch.setattr(autosave, "recovery_dir", lambda: str(folder))
    return str(folder)


def test_save_incremental_clears_asterisk(window, text_pdf):
    tab = window.file.open_path(text_pdf)
    tab.doc.rotate_pages([0], 90)
    assert window.tabs.tabText(0) == "text.pdf *"
    assert window.file.save()
    assert window.tabs.tabText(0) == "text.pdf" and "incrementally" in window.statusBar().currentMessage()
    assert pymupdf.open(text_pdf)[0].rotation == 90


def test_save_as_untitled_document(window, tmp_path, monkeypatch):
    window.file.new_document()
    out = str(tmp_path / "new_doc")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    assert window.file.save()  # untitled -> falls back to Save As
    assert os.path.exists(out + ".pdf") and window.current_tab().doc.path == out + ".pdf"


def test_close_prompt_save_discard_cancel(window, text_pdf, monkeypatch):
    tab = window.file.open_path(text_pdf)
    tab.doc.rotate_pages([0], 90)
    answers = iter([QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Discard])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: next(answers))
    assert not window.file.close_tab(0) and window.tabs.count() == 1
    assert window.file.close_tab(0) and window.tabs.count() == 0
    assert pymupdf.open(text_pdf)[0].rotation == 0  # discarded


def test_close_prompt_save(window, text_pdf, monkeypatch):
    tab = window.file.open_path(text_pdf)
    tab.doc.rotate_pages([1], 180)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Save)
    assert window.file.close_all()
    assert pymupdf.open(text_pdf)[1].rotation == 180


def test_autosave_writes_and_cleans_up(window, text_pdf, isolated_recovery):
    tab = window.file.open_path(text_pdf)
    tab.doc.rotate_pages([0], 90)
    assert window.autosave.autosave_all() == 1
    files = sorted(os.listdir(isolated_recovery))
    assert any(f.endswith(".pdf") for f in files) and any(f.endswith(".json") for f in files)
    window.file.save()
    assert not any(f.endswith(".pdf") for f in os.listdir(isolated_recovery))


def test_crash_recovery_restores_document(window, qtbot, text_pdf, isolated_recovery, monkeypatch):
    tab = window.file.open_path(text_pdf)
    tab.doc.delete_pages([2])
    window.autosave.autosave_all()
    window.autosave._lock.unlock()  # simulate a crash: the lock is gone but the copy stays
    from pdf_editor.app.main_window import MainWindow
    from pdf_editor.app.dialogs.recovery import RecoveryDialog

    second = MainWindow(window.settings)
    monkeypatch.setattr(RecoveryDialog, "exec", lambda self: RecoveryDialog.DialogCode.Accepted)
    assert second.offer_recovery() == 1
    restored = second.current_tab()
    assert restored.doc.page_count == 2 and restored.doc.is_modified and restored.doc.path == text_pdf
    assert autosave.find_orphans(isolated_recovery, second.autosave.session) == []
    second.file.maybe_save = lambda t: True
    second.close()


def test_running_session_copies_are_not_offered(window, text_pdf, isolated_recovery):
    tab = window.file.open_path(text_pdf)
    tab.doc.rotate_pages([0], 90)
    window.autosave.autosave_all()
    assert autosave.find_orphans(isolated_recovery, "another-session") == []  # lock still held


def test_settings_dialog_applies(window, monkeypatch):
    from pdf_editor.app.dialogs.settings import SettingsDialog

    dialog = SettingsDialog(window.settings, window)
    dialog.theme.setCurrentIndex(dialog.theme.findData("dark"))
    dialog.autosave.setValue(7)
    dialog.annot_color.color = "#123456"
    dialog.accept()
    window.apply_settings()
    assert window.settings.theme == "dark" and window.effective_theme == "dark"
    assert window.autosave.timer.interval() == 7 * 60_000 and window.tool_options.stroke == "#123456"


def test_shortcuts_dialog_lists_common_shortcuts(window):
    from pdf_editor.app.dialogs.shortcuts import ShortcutsDialog

    dialog = ShortcutsDialog(window)
    rows = []
    for i in range(dialog.tree.topLevelItemCount()):
        group = dialog.tree.topLevelItem(i)
        rows += [(group.child(j).text(0), group.child(j).text(1)) for j in range(group.childCount())]
    names = {name for name, _ in rows}
    assert {"Open", "Save", "Undo", "Find", "Keyboard Shortcuts", "Zoom In", "Highlight Text"} <= names
    dialog.filter.setText("zoom")
    group_hidden = [dialog.tree.topLevelItem(i).isHidden() for i in range(dialog.tree.topLevelItemCount())]
    assert any(group_hidden) and not all(group_hidden)


def test_window_state_is_remembered(tmp_path, qtbot):
    from pdf_editor.app.main_window import MainWindow

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    first = MainWindow(settings)
    first.resize(700, 500)  # the offscreen test screen is only 800x600
    first.show()
    first.docks["annotations"].show()
    first.docks["thumbnails"].hide()
    size = (first.width(), first.height())
    first.close()
    second = MainWindow(settings)
    second.show()
    assert second.docks["annotations"].isVisible() and not second.docks["thumbnails"].isVisible()
    assert (second.width(), second.height()) == size
    second.close()


def test_unexpected_errors_are_logged_and_shown(window, tmp_path, monkeypatch):
    from pdf_editor.app import errors

    log_path = str(tmp_path / "test.log")
    monkeypatch.setattr(errors, "_log_path", log_path)
    errors.setup_logging()
    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.text()))
    try:
        raise ZeroDivisionError("boom")
    except ZeroDivisionError as exc:
        errors.show_error(exc, window)
    assert shown and "unexpected error" in shown[0] and "ZeroDivisionError" in shown[0]
    for handler in errors.log.handlers:
        handler.flush()


def test_print_page_range():
    from PySide6.QtPrintSupport import QPrinter

    from pdf_editor.app.printing import page_range

    printer = QPrinter()
    assert page_range(printer, 5, 2) == [0, 1, 2, 3, 4]
    printer.setPrintRange(QPrinter.PrintRange.PageRange)
    printer.setFromTo(2, 3)
    assert page_range(printer, 5, 0) == [1, 2]
    printer.setPrintRange(QPrinter.PrintRange.CurrentPage)
    assert page_range(printer, 5, 3) == [3]


def test_status_bar_shows_page_zoom_and_size(window, text_pdf):
    window.file.open_path(text_pdf)
    window.view.actual_size()
    status = window.status
    assert status.page.text() == "Page 1 of 3" and status.zoom.text() == "100%" and "KB" in status.size.text()


def test_no_two_actions_share_a_shortcut(window):
    from PySide6.QtGui import QKeySequence

    seen: dict[str, str] = {}
    for key, action in window.actions.items():
        for seq in action.shortcuts():
            text = seq.toString(QKeySequence.SequenceFormat.PortableText)
            assert text not in seen, f"{text} is used by both {seen[text]} and {key}"
            seen[text] = key
    assert len(seen) > 60


def test_job_finishing_after_window_closed_does_not_crash(qtbot, tmp_path, settings):
    """A background job that completes after its window is gone only cleans up."""
    from pdf_editor.app import workers
    from pdf_editor.app.main_window import MainWindow

    win = MainWindow(settings)
    cleaned, called = [], []
    job = workers.start_job(win, "Test", "tests.job_targets:count_to", {"n": 3},
                            on_success=lambda r: called.append(r), on_finally=lambda: cleaned.append(True))
    win.file.maybe_save = lambda tab: True
    win.close()
    win.deleteLater()
    qtbot.wait(50)  # let deleteLater run before the job finishes
    qtbot.waitUntil(lambda: bool(cleaned), timeout=30000)
    assert called == [] and job not in workers._active_jobs
