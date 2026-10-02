"""GUI tests: opening, navigation, zoom, search, selection, panels."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from tests.fixtures import builders
from tests.gui.conftest import pump

pytestmark = pytest.mark.gui


def test_open_file_creates_tab_and_renders(window, qtbot, text_pdf):
    tab = window.file.open_path(text_pdf)
    assert tab is not None and window.tabs.count() == 1
    pump(qtbot, 0.5)
    assert tab.viewer.page_count == 3
    assert any(tab.viewer.item(p).image is not None for p in tab.viewer.visible_pages())
    assert window.page_box.label.text() == "of 3"
    assert window.settings.recent_files()[0] == text_pdf


def test_opening_same_file_twice_focuses_existing_tab(window, text_pdf):
    first = window.file.open_path(text_pdf)
    second = window.file.open_path(text_pdf)
    assert first is second and window.tabs.count() == 1


def test_open_encrypted_asks_for_password(window, encrypted_pdf, monkeypatch):
    answers = iter(["wrong", "owner"])
    monkeypatch.setattr("pdf_editor.app.controllers.file_ops.ask_password", lambda *a: next(answers))
    tab = window.file.open_path(encrypted_pdf)
    assert tab is not None and tab.doc.page_count == 1


def test_open_cancelled_password(window, encrypted_pdf, monkeypatch):
    monkeypatch.setattr("pdf_editor.app.controllers.file_ops.ask_password", lambda *a: None)
    assert window.file.open_path(encrypted_pdf) is None and window.tabs.count() == 0


def test_open_broken_file_shows_error_not_crash(window, tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.7 garbage")
    assert window.file.open_path(str(bad)) is None


def test_multiple_tabs(window, text_pdf, outline_pdf):
    window.file.open_paths([text_pdf, outline_pdf])
    assert window.tabs.count() == 2
    assert window.current_tab().doc.display_name == "outline.pdf"
    window.view.prev_tab()
    assert window.current_tab().doc.display_name == "text.pdf"


def test_navigation_and_page_box(window, qtbot, ten_page_pdf):
    tab = window.file.open_path(ten_page_pdf)
    pump(qtbot, 0.2)
    tab.viewer.go_to_page(6)
    pump(qtbot, 0.2)
    assert tab.viewer.current_page == 6
    window.view.next_page()
    assert tab.viewer.current_page == 7
    window.page_box.pageRequested.emit(2)
    pump(qtbot, 0.1)
    assert tab.viewer.current_page == 2
    window.view.last_page()
    assert tab.viewer.current_page == 9


def test_zoom_modes(window, qtbot, text_pdf):
    tab = window.file.open_path(text_pdf)
    window.view.actual_size()
    assert tab.viewer.zoom == pytest.approx(1.0)
    window.view.zoom_in()
    assert tab.viewer.zoom > 1.0 and tab.viewer.fit_mode is None
    window.view.fit_width()
    assert tab.viewer.fit_mode == "fit-width"
    width_zoom = tab.viewer.zoom
    window.view.fit_page()
    assert tab.viewer.zoom < width_zoom


def test_ctrl_wheel_zoom(window, qtbot, text_pdf):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QWheelEvent

    tab = window.file.open_path(text_pdf)
    before = tab.viewer.zoom
    event = QWheelEvent(QPointF(100, 100), QPointF(100, 100), QPoint(0, 0), QPoint(0, 120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier, Qt.ScrollPhase.NoScrollPhase, False)
    tab.viewer.wheelEvent(event)
    assert tab.viewer.zoom > before


def test_single_page_mode(window, qtbot, ten_page_pdf):
    tab = window.file.open_path(ten_page_pdf)
    window.view.set_continuous(False)
    tab.viewer.go_to_page(4)
    visible = [p for p in range(10) if tab.viewer.item(p).isVisible()]
    assert visible == [4]
    window.view.set_continuous(True)
    assert all(tab.viewer.item(p).isVisible() for p in range(10))


def test_search_highlights_and_navigation(window, qtbot, ten_page_pdf):
    tab = window.file.open_path(ten_page_pdf)
    tab.search.start("unique marker")
    qtbot.waitUntil(lambda: not tab.search.running, timeout=5000)
    assert tab.search.total == 10
    first = tab.search.current_index()
    tab.search.next()
    assert tab.search.current_index() == (first + 1) % 10
    tab.search.start("UNIQUE", match_case=True)
    qtbot.waitUntil(lambda: not tab.search.running, timeout=5000)
    assert tab.search.total == 0
    tab.search.clear()
    assert tab.search.total == 0 and not tab.search.active


def test_search_bar_status(window, qtbot, text_pdf):
    tab = window.file.open_path(text_pdf)
    window.search_bar.edit.setText("quick")
    window.search_bar._search_now()
    qtbot.waitUntil(lambda: not tab.search.running, timeout=5000)
    assert window.search_bar.status.text().endswith("of 3")


def test_text_selection_and_copy(window, qtbot, text_pdf):
    tab = window.file.open_path(text_pdf)
    selector = tab.text_selector
    selector.begin(0, (72, 115))
    selector.extend((300, 115))
    assert selector.has_selection and selector.selection.text.startswith("The quick")
    window.edit.copy()
    assert QApplication.clipboard().text().startswith("The quick")
    window.edit.select_all()
    assert "Unique marker 001" in selector.selection.text


def test_thumbnail_model_lazy_and_click_navigates(window, qtbot, ten_page_pdf):
    tab = window.file.open_path(ten_page_pdf)
    model = tab.thumb_model
    assert model.rowCount() == 10
    assert model.data(model.index(3), Qt.ItemDataRole.DisplayRole) == "4"
    window.thumbnails.pageActivated.emit(5)
    assert tab.viewer.current_page == 5


def test_outline_panel_navigation(window, qtbot, outline_pdf):
    tab = window.file.open_path(outline_pdf)
    tree = window.outline.tree
    assert tree.topLevelItemCount() == 2
    chapter2 = tree.topLevelItem(1)
    window.outline._on_clicked(chapter2)
    pump(qtbot, 0.1)
    assert tab.viewer.current_page == 3


def test_invert_and_theme(window, qtbot, text_pdf):
    tab = window.file.open_path(text_pdf)
    window.view.toggle_invert(True)
    pump(qtbot, 0.3)
    assert tab.viewer.item(0).inverted and window.settings.invert_pages
    window.view.theme_dark()
    assert window.effective_theme == "dark"
    window.view.theme_light()
    assert window.effective_theme == "light"


def test_recent_files_menu(window, text_pdf, outline_pdf):
    window.file.open_paths([text_pdf, outline_pdf])
    texts = [a.text() for a in window.recent_menu.actions()]
    assert any("outline.pdf" in t for t in texts) and any("text.pdf" in t for t in texts)


def test_large_document_renders_only_nearby_pages(window, qtbot, tmp_path):
    path = builders.text_pdf(str(tmp_path / "large.pdf"), pages=300)
    tab = window.file.open_path(path)
    pump(qtbot, 0.6)
    rendered = [p for p in range(300) if tab.viewer.item(p).image is not None]
    assert rendered and max(rendered) < 15  # lazy: far pages are not rendered
    tab.viewer.go_to_page(250)
    pump(qtbot, 0.6)
    assert tab.viewer.item(250).image is not None
    assert tab.viewer.item(0).image is None  # released


def test_close_tab_shows_welcome(window, text_pdf):
    window.file.open_path(text_pdf)
    window.file.close_current()
    assert window.tabs.count() == 0 and window.stack.currentWidget() is window.welcome
