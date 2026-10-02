"""GUI tests: annotation tools, selection, editing and the panel."""

from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QInputDialog

from tests.gui.conftest import pump
from tests.gui.helpers import drag, page_event

pytestmark = pytest.mark.gui


def kinds(tab, pno=0):
    page = tab.doc.raw[pno]  # PyMuPDF annotations must not outlive their page object
    return [a.type[1] for a in page.annots()]


def annot_rect(tab, xref, pno=0):
    page = tab.doc.raw[pno]
    return pymupdf.Rect(page.load_annot(xref).rect)


def test_highlight_tool_marks_dragged_text(window, text_pdf):
    tab = window.file.open_path(text_pdf)
    tab.set_tool("highlight")
    drag(tab.active_tool, tab, 0, (72, 115), (200, 115))
    page = tab.doc.raw[0]  # keep the page alive while using its annotations
    annots = list(page.annots())
    assert [a.type[1] for a in annots] == ["Highlight"]
    assert annots[0].info["content"].startswith("The quick")
    window.edit.undo()
    assert kinds(tab) == []


def test_underline_and_strikeout_tools(window, text_pdf):
    tab = window.file.open_path(text_pdf)
    for name, expected in (("underline", "Underline"), ("strikeout", "StrikeOut")):
        tab.set_tool(name)
        drag(tab.active_tool, tab, 0, (72, 135), (150, 135))
        assert expected in kinds(tab)


def test_markup_existing_selection_via_menu_action(window, text_pdf):
    tab = window.file.open_path(text_pdf)
    tab.text_selector.begin(0, (72, 115))
    tab.text_selector.extend((200, 115))
    window.actions["annot.highlight_selection"].trigger()
    assert kinds(tab) == ["Highlight"] and not tab.text_selector.has_selection


def test_pen_and_shapes(window, text_pdf):
    tab = window.file.open_path(text_pdf)
    window.tool_options.set(stroke="#0000ff", width=3)
    tab.set_tool("pen")
    drag(tab.active_tool, tab, 0, (100, 300), (200, 360), steps=8)
    for name in ("rectangle", "ellipse", "line", "arrow"):
        tab.set_tool(name)
        drag(tab.active_tool, tab, 0, (300, 300), (400, 380))
    assert kinds(tab) == ["Ink", "Square", "Circle", "Line", "Line"]
    page = tab.doc.raw[0]
    ink = next(page.annots())
    assert ink.colors["stroke"] == [0.0, 0.0, 1.0] and ink.border["width"] == 3


def test_note_textbox_and_stamp(window, text_pdf, monkeypatch):
    tab = window.file.open_path(text_pdf)
    monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *a, **k: ("Hello there", True))
    tab.set_tool("note")
    tab.active_tool.press(page_event(tab, 0, 450, 450))
    tab.set_tool("textbox")
    drag(tab.active_tool, tab, 0, (100, 600), (300, 650))
    window.tool_options.set(stamp="Draft", stamp_image=None)
    tab.set_tool("stamp")
    tab.active_tool.press(page_event(tab, 0, 300, 720))
    tab.active_tool.release(page_event(tab, 0, 300, 720))
    assert kinds(tab) == ["Text", "FreeText", "Stamp"]
    page = tab.doc.raw[0]
    stamp = list(page.annots())[-1]
    assert stamp.info["content"] == "Draft"


def test_image_stamp(window, text_pdf, png_file):
    tab = window.file.open_path(text_pdf)
    window.tool_options.set(stamp_image=png_file)
    tab.set_tool("stamp")
    drag(tab.active_tool, tab, 0, (100, 100), (250, 200))
    assert kinds(tab) == ["Stamp"]


def test_select_move_resize_delete(window, text_pdf):
    tab = window.file.open_path(text_pdf)
    xref = tab.doc.add_shape(0, "rect", (100, 300), (200, 400), (1, 0, 0))
    tab.set_tool("select")
    tool = tab.active_tool
    drag(tool, tab, 0, (150, 350), (200, 380))  # move by (50, 30)
    rect = annot_rect(tab, xref)
    assert rect.x0 == pytest.approx(149, abs=1) and rect.y0 == pytest.approx(329, abs=1)
    assert tool.selected == (0, xref)
    # resize with the bottom-right handle
    br = tool._overlay.rect.bottomRight()
    drag(tool, tab, 0, (br.x(), br.y()), (br.x() + 40, br.y() + 20))
    rect2 = annot_rect(tab, xref)
    assert rect2.width == pytest.approx(rect.width + 40, abs=1)
    # nudge with the keyboard and delete
    tool.key_press(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier))
    assert annot_rect(tab, xref).x0 == pytest.approx(rect2.x0 + 10, abs=0.5)
    tool.key_press(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier))
    assert kinds(tab) == []
    window.edit.undo()
    assert kinds(tab) == ["Square"]


def test_select_on_rotated_page_moves_in_visual_direction(window, text_pdf):
    tab = window.file.open_path(text_pdf)
    tab.doc.rotate_pages([0], 90)
    xref = tab.doc.add_shape(0, "rect", (100, 100), (200, 150), (1, 0, 0))
    tab.set_tool("select")
    visual = tab.viewer.page_rect_to_visual(0, annot_rect(tab, xref))
    c = visual.center()
    drag(tab.active_tool, tab, 0, (c.x(), c.y()), (c.x() + 30, c.y()))
    moved = tab.viewer.page_rect_to_visual(0, annot_rect(tab, xref))
    assert moved.center().x() == pytest.approx(c.x() + 30, abs=1.5)
    assert moved.center().y() == pytest.approx(c.y(), abs=1.5)


def test_properties_dialog_changes_style(window, text_pdf, monkeypatch):
    tab = window.file.open_path(text_pdf)
    xref = tab.doc.add_shape(0, "rect", (100, 300), (200, 400), (1, 0, 0))
    from pdf_editor.app.dialogs import annotation_props

    def fake_exec(dialog):
        dialog.color.color = "#00ff00"
        dialog.width.setValue(4)
        dialog.text.setPlainText("Shape comment")
        return True

    monkeypatch.setattr(annotation_props.AnnotationPropertiesDialog, "exec", fake_exec)
    tab.edit_annotation(0, xref, properties=True)
    info = tab.doc.annotation_info(0, xref)
    assert info.stroke == "#00ff00" and info.width == 4 and info.contents == "Shape comment"
    window.edit.undo()
    assert tab.doc.annotation_info(0, xref).stroke == "#ff0000"


def test_annotations_panel_lists_and_jumps(window, qtbot, annotated_pdf):
    tab = window.file.open_path(annotated_pdf)
    panel = window.annotations_panel
    assert panel.count.text() == "3"
    group = panel.tree.topLevelItem(0)
    target = group.child(1)
    panel._activate(target)
    assert tab.tool_name == "select" and tab.active_tool.selected == target.data(0, Qt.ItemDataRole.UserRole)
    tab.doc.add_sticky_note(1, (100, 100), "page two note", (1, 1, 0))
    pump(qtbot, 0.4)
    assert panel.count.text() == "4" and panel.tree.topLevelItemCount() == 2
    panel.filter.setText("page two")
    assert panel.count.text() == "1"


def test_options_bar_follows_tool(window, text_pdf):
    tab = window.file.open_path(text_pdf)
    def shown(group):
        return all(action.isVisible() for action in window.options_bar._actions[group])

    tab.set_tool("rectangle")
    assert shown("width") and shown("fill") and not shown("stamp")
    tab.set_tool("stamp")
    assert shown("stamp") and not shown("width")
