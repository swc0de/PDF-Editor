"""GUI tests: text, images, forms, signatures, watermark, header/footer."""

from __future__ import annotations

import os

import pymupdf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from pdf_editor.settings import SavedSignature
from tests.fixtures import builders
from tests.gui.helpers import drag, page_event

pytestmark = pytest.mark.gui


def field(tab, name, index=0):
    return [f for f in tab.doc.form_fields() if f.name == name][index]


def test_form_checkbox_radio_and_choice(window, form_pdf, monkeypatch):
    tab = window.file.open_path(form_pdf)
    tool = tab.tool("select")
    tab.set_tool("select")
    agree = field(tab, "agree")
    c = agree.rect.tl + (5, 5)
    tool.press(page_event(tab, 0, c.x, c.y))
    assert field(tab, "agree").value is True
    large = field(tab, "size", 1)
    tool.press(page_event(tab, 0, large.rect.x0 + 5, large.rect.y0 + 5))
    assert field(tab, "size", 1).value is True and field(tab, "size", 0).value is False
    monkeypatch.setattr(tab.form_filler, "choose_option", lambda field, pos: "Green")
    color = field(tab, "color")
    tool.press(page_event(tab, 0, color.rect.x0 + 5, color.rect.y0 + 5))
    assert field(tab, "color").value == "Green"
    window.edit.undo()
    assert field(tab, "color").value == "Red"


def test_form_text_field_inline_editor(window, qtbot, form_pdf):
    tab = window.file.open_path(form_pdf)
    tab.set_tool("select")
    name = field(tab, "name")
    tab.active_tool.press(page_event(tab, 0, name.rect.x0 + 5, name.rect.y0 + 5))
    proxy = tab.form_filler._proxy
    assert proxy is not None
    editor = proxy.widget()
    editor.setText("Ada Lovelace")
    QApplication.sendEvent(editor, QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
    assert field(tab, "name").value == "Ada Lovelace" and tab.form_filler._proxy is None


def test_add_text_tool(window, text_pdf, monkeypatch):
    tab = window.file.open_path(text_pdf)
    from pdf_editor.app.dialogs import add_text

    def fake_exec(dialog):
        dialog.text.setPlainText("Inserted by the tool")
        dialog.family.setCurrentText("Courier")
        dialog.size.setValue(16)
        return True

    monkeypatch.setattr(add_text.AddTextDialog, "exec", fake_exec)
    tab.set_tool("text_add")
    tab.active_tool.press(page_event(tab, 0, 72, 400))
    tab.active_tool.release(page_event(tab, 0, 72, 400))
    assert "Inserted by the tool" in tab.doc.raw[0].get_text()
    span = tab.doc.text_span_at(0, tab.doc.raw[0].search_for("Inserted")[0].tl + (2, 2))
    assert span.font.startswith("Courier") and span.size == pytest.approx(16)


def test_edit_text_tool_in_place(window, text_pdf):
    tab = window.file.open_path(text_pdf)
    tab.set_tool("text_edit")
    tab.active_tool.press(page_event(tab, 0, 80, 65))
    editor = tab.active_tool._proxy.widget()
    editor.setText("Renamed heading")
    QApplication.sendEvent(editor, QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
    text = tab.doc.raw[0].get_text()
    assert "Renamed heading" in text and "Page 1" not in text
    window.edit.undo()
    assert "Page 1" in tab.doc.raw[0].get_text()


def test_edit_text_warns_when_font_cannot_be_matched(window, tmp_path, monkeypatch):
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if not os.path.exists(font_path):
        pytest.skip("DejaVu font not installed")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_font(fontname="dv", fontfile=font_path)
    page.insert_text((72, 100), "abc", fontname="dv", fontsize=14)
    doc.subset_fonts()
    path = str(tmp_path / "subset.pdf")
    doc.save(path)
    tab = window.file.open_path(path)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]) or QMessageBox.StandardButton.Cancel)
    tab.set_tool("text_edit")
    tab.active_tool.press(page_event(tab, 0, 75, 95))
    tab.active_tool.end_edit(True, "xyz QRS")
    assert warnings and "DejaVu" in warnings[0]
    assert "abc" in tab.doc.raw[0].get_text()  # cancelled: unchanged


def test_image_tool_insert_and_move(window, text_pdf, png_file, monkeypatch):
    tab = window.file.open_path(text_pdf)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (png_file, ""))
    tab.set_tool("image")
    drag(tab.active_tool, tab, 0, (100, 300), (400, 500))
    images = tab.doc.page_images(0)
    assert len(images) == 1
    box = images[0].bbox
    c = box.tl + (box.width / 2, box.height / 2)
    visual_c = tab.viewer.page_to_visual(0, c)
    drag(tab.active_tool, tab, 0, (visual_c.x(), visual_c.y()), (visual_c.x() + 50, visual_c.y() + 20))
    moved = tab.doc.page_images(0)[0].bbox
    assert moved.x0 == pytest.approx(box.x0 + 50, abs=1) and moved.y0 == pytest.approx(box.y0 + 20, abs=1)


def test_signature_tool_places_saved_signature(window, text_pdf):
    window.settings.add_signature(SavedSignature("Test", builders.png_bytes(300, 100, alpha=True)))
    window.options_bar.refresh_signatures()
    tab = window.file.open_path(text_pdf)
    tab.set_tool("signature")
    tab.active_tool.press(page_event(tab, 0, 300, 600))
    tab.active_tool.release(page_event(tab, 0, 300, 600))
    images = tab.doc.page_images(0)
    assert len(images) == 1 and images[0].bbox.width == pytest.approx(160, abs=1)
    assert window.actions["edit.undo"].text().endswith("Place signature")


def test_signature_dialog_draw_and_type(qtbot):
    from pdf_editor.app.dialogs.signature import SignatureDialog, render_typed_signature

    dialog = SignatureDialog()
    qtbot.addWidget(dialog)
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPainterPath

    path = QPainterPath(QPointF(20, 80))
    path.cubicTo(QPointF(80, 10), QPointF(140, 150), QPointF(260, 60))
    dialog.pad.paths.append(path)
    dialog.accept()
    assert dialog.png and dialog.png[:4] == b"\x89PNG"
    typed = render_typed_signature("Ada Lovelace", "Sans Serif")
    from pdf_editor.core.operations.images import image_size

    w, h = image_size(typed)
    assert w > h > 10


def test_watermark_and_header_footer_dialogs(window, text_pdf, monkeypatch):
    tab = window.file.open_path(text_pdf)
    from pdf_editor.app.dialogs import header_footer, watermark

    monkeypatch.setattr(watermark.WatermarkDialog, "exec", lambda self: (self.text.setText("SECRET"), True)[1])
    window.content_ctl.watermark()
    assert all("SECRET" in tab.doc.raw[p].get_text() for p in range(3))

    def numbers(dialog):
        dialog.number_format.setCurrentText("{page} / {total}")
        return True

    monkeypatch.setattr(header_footer.HeaderFooterDialog, "exec", numbers)
    window.content_ctl.page_numbers()
    assert "3 / 3" in tab.doc.raw[2].get_text()
    window.edit.undo()
    window.edit.undo()
    assert "SECRET" not in tab.doc.raw[0].get_text()


def test_flatten_forms_action(window, form_pdf, monkeypatch):
    tab = window.file.open_path(form_pdf)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.content_ctl.flatten_forms()
    assert tab.doc.form_fields() == []
    window.edit.undo()
    assert len(tab.doc.form_fields()) == 6
