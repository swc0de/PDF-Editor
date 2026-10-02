"""Content tools: add text, edit text in place, insert/move images, place signatures."""

from __future__ import annotations

import os

import pymupdf
from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPen
from PySide6.QtWidgets import QFileDialog, QGraphicsProxyWidget, QGraphicsRectItem, QLineEdit, QMessageBox

from ...core.operations import images as image_ops
from ..annotation_overlay import CURSORS, AnnotationSelectionItem, resized
from ..dialogs.add_text import AddTextDialog
from ..errors import guarded
from .base import PageEvent, Tool
from .rect_tool import RectDrawTool

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp);;All files (*)"


class AddTextTool(RectDrawTool):
    """Click (or drag a box) and type new page text."""

    name, label = "text_add", "Add Text"
    tooltip = "Click where the text should start, or drag a box"
    hint = "Click to place text (drag to set the box width)"
    cursor = Qt.CursorShape.IBeamCursor
    options_used = {"stroke", "font"}

    def click(self, pno: int, event: PageEvent) -> None:
        width = self.viewer.item(pno).page_rect().width() - event.visual.x() - 36
        visual = QRectF(event.visual.x(), event.visual.y() - self.tab.tool_options.font_size,
                        max(width, 120.0), self.tab.tool_options.font_size * 1.6)
        self.finish(pno, visual, self.viewer.visual_rect_to_page(pno, visual))

    def finish(self, pno: int, visual: QRectF, rect: pymupdf.Rect) -> None:
        options = self.tab.tool_options
        dialog = AddTextDialog(self.tab, options.stroke, options.font_size)
        if not dialog.exec():
            return
        text, style = dialog.values()
        with guarded(self.tab, "Cannot add text"):
            self.doc.add_text(pno, rect, text, **style)


class _LineEditor(QObject):
    def __init__(self, tool: "EditTextTool", edit: QLineEdit) -> None:
        super().__init__(edit)
        self.tool, self.edit, self.closed = tool, edit, False
        edit.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.close(False)
            return True
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.close(True)
            return True
        if event.type() == QEvent.Type.FocusOut:
            self.close(True)
        return False

    def close(self, commit: bool) -> None:
        if not self.closed:
            self.closed = True
            self.tool.end_edit(commit, self.edit.text())


class EditTextTool(Tool):
    """Click a line of existing text to edit it in place."""

    name, label = "text_edit", "Edit Text"
    tooltip = "Click existing text to change it"
    hint = "Click a piece of text, edit it, press Enter (Esc cancels)"
    cursor = Qt.CursorShape.IBeamCursor
    options_used: set[str] = set()

    def __init__(self, tab) -> None:
        super().__init__(tab)
        self._hover: QGraphicsRectItem | None = None
        self._proxy: QGraphicsProxyWidget | None = None
        self._span = None

    def hover(self, event: PageEvent) -> None:
        span = self.doc.text_span_at(event.pno, event.point)
        self._clear_hover()
        if span is not None and self._proxy is None:
            item = QGraphicsRectItem(self.viewer.page_rect_to_visual(event.pno, span.bbox), self.viewer.item(event.pno))
            pen = QPen(QColor(30, 120, 255), 0)
            pen.setCosmetic(True)
            item.setPen(pen)
            item.setZValue(20)
            self._hover = item

    def _clear_hover(self) -> None:
        if self._hover is not None and self._hover.scene() is not None:
            self._hover.scene().removeItem(self._hover)
        self._hover = None

    def press(self, event: PageEvent) -> bool:
        span = self.doc.text_span_at(event.pno, event.point)
        if span is None:
            return False
        self._clear_hover()
        self.begin_edit(span)
        return True

    def begin_edit(self, span) -> None:
        self._span = span
        visual = self.viewer.page_rect_to_visual(span.page, span.bbox)
        edit = QLineEdit(span.text)
        font = QFont()
        font.setPixelSize(max(6, int(span.size)))
        font.setBold(span.bold)
        font.setItalic(span.italic)
        edit.setFont(font)
        edit.setStyleSheet("background: #fffbe0; border: 1px solid #2f6fdf; padding: 0px;")
        proxy = QGraphicsProxyWidget(self.viewer.item(span.page))
        proxy.setWidget(edit)
        proxy.setGeometry(visual.adjusted(-2, -2, max(60.0, visual.width() * 0.5), 2))
        proxy.setZValue(40)
        self._proxy = proxy
        _LineEditor(self, edit)
        edit.setFocus()
        edit.selectAll()

    def end_edit(self, commit: bool, text: str) -> None:
        span, proxy = self._span, self._proxy
        self._span = self._proxy = None
        if proxy is not None and proxy.scene() is not None:
            proxy.scene().removeItem(proxy)
            proxy.deleteLater()
        self.viewer.setFocus()
        if not commit or span is None or text == span.text:
            return
        with guarded(self.tab, "Cannot edit text"):
            choice = self.doc.preview_font(span, text)
            if choice.warning:
                answer = QMessageBox.warning(
                    self.tab, "Font not available", f"{choice.warning}\n\nApply the change anyway?",
                    QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                )
                if answer != QMessageBox.StandardButton.Ok:
                    return
            used = self.doc.replace_text(span, text)
            self.tab.show_message(f"Text replaced using {used.description}.")

    def deactivate(self) -> None:
        self._clear_hover()
        if self._proxy is not None:
            self.end_edit(False, "")


class ImageTool(RectDrawTool):
    """Insert images (click or drag) and move/resize existing ones."""

    name, label = "image", "Image"
    tooltip = "Insert an image, or drag an existing image to move/resize it"
    hint = "Click or drag to insert an image; drag an image (or its handles) to move/resize"
    options_used: set[str] = set()

    def __init__(self, tab) -> None:
        super().__init__(tab)
        self._selected: tuple[int, image_ops.PageImage] | None = None
        self._overlay: AnnotationSelectionItem | None = None
        self._drag: tuple[str, QPointF, QRectF] | None = None

    def _select(self, pno: int, image: image_ops.PageImage | None) -> None:
        if self._overlay is not None and self._overlay.scene() is not None:
            self._overlay.scene().removeItem(self._overlay)
        self._overlay, self._selected = None, None
        if image is not None:
            self._selected = (pno, image)
            self._overlay = AnnotationSelectionItem(self.viewer.page_rect_to_visual(pno, image.bbox), True,
                                                    self.viewer.item(pno))
            self._overlay.scale_hint = self.viewer.transform().m11()

    def press(self, event: PageEvent) -> bool:
        if self._overlay is not None and self._selected and self._selected[0] == event.pno:
            handle = self._overlay.hit_test(event.visual)
            if handle:
                self._drag = (handle, QPointF(event.visual), self._overlay.rect)
                return True
        image = self.doc.image_at(event.pno, event.point)
        if image is not None:
            self._select(event.pno, image)
            self._drag = ("move", QPointF(event.visual), self._overlay.rect)
            return True
        self._select(event.pno, None)
        return super().press(event)

    def move(self, event: PageEvent) -> bool:
        if self._drag is not None and self._overlay is not None:
            handle, start, rect = self._drag
            self._overlay.set_rect(resized(rect, handle, event.visual - start, keep_aspect=not event.shift))
            return True
        return super().move(event)

    def release(self, event: PageEvent) -> bool:
        if self._drag is not None and self._overlay is not None and self._selected is not None:
            _, _, start = self._drag
            self._drag = None
            new = self._overlay.rect
            if abs(new.left() - start.left()) + abs(new.top() - start.top()) + abs(new.width() - start.width()) > 0.5:
                pno, image = self._selected
                with guarded(self.tab, "Cannot move image") as g:
                    self.doc.move_image(pno, image, self.viewer.visual_rect_to_page(pno, new))
                if g.failed:
                    self._overlay.set_rect(start)
                else:
                    moved = self.doc.image_at(pno, self.viewer.visual_rect_to_page(pno, new).tl + (1, 1))
                    self._select(pno, moved)
            return True
        return super().release(event)

    def hover(self, event: PageEvent) -> None:
        if self._overlay is not None and self._selected and self._selected[0] == event.pno:
            handle = self._overlay.hit_test(event.visual)
            if handle:
                self.viewer.viewport().setCursor(CURSORS[handle])
                return
        shape = Qt.CursorShape.SizeAllCursor if self.doc.image_at(event.pno, event.point) else Qt.CursorShape.CrossCursor
        self.viewer.viewport().setCursor(shape)

    def _choose(self) -> bytes | None:
        path, _ = QFileDialog.getOpenFileName(self.tab, "Insert Image", self.settings.last_directory, IMAGE_FILTER)
        if not path:
            return None
        self.settings.last_directory = os.path.dirname(path)
        with guarded(self.tab, "Cannot read image") as g:
            data = image_ops.load_image_bytes(path)
        return None if g.failed else data

    def click(self, pno: int, event: PageEvent) -> None:
        data = self._choose()
        if data is None:
            return
        w_px, h_px = image_ops.image_size(data)
        page_w = self.viewer.item(pno).page_rect().width()
        width = min(w_px * 0.75, page_w * 0.5)
        visual = QRectF(event.visual.x(), event.visual.y(), width, width * h_px / w_px)
        self._insert(pno, visual, data)

    def finish(self, pno: int, visual: QRectF, rect: pymupdf.Rect) -> None:
        data = self._choose()
        if data is not None:
            w_px, h_px = image_ops.image_size(data)
            fitted = image_ops.fit_rect((visual.left(), visual.top(), visual.right(), visual.bottom()), w_px, h_px)
            self._insert(pno, QRectF(fitted.x0, fitted.y0, fitted.width, fitted.height), data)

    def _insert(self, pno: int, visual: QRectF, data: bytes, label: str = "Insert image") -> None:
        with guarded(self.tab, "Cannot insert image"):
            self.doc.insert_image(pno, self.viewer.visual_rect_to_page(pno, visual), data, label)

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._selected is not None:
            self._select(0, None)
            return True
        return super().key_press(event)

    def deactivate(self) -> None:
        self._select(0, None)
        super().deactivate()

    def document_changed(self) -> None:
        self._select(0, None)


class SignatureTool(ImageTool):
    """Click (or drag a box) to place the chosen saved signature."""

    name, label = "signature", "Signature"
    tooltip = "Place your signature"
    hint = "Click to place the signature, or drag a box"
    options_used = {"signature"}

    def press(self, event: PageEvent) -> bool:
        if self.tab.tool_options.signature is None and not self.tab.window().create_signature():
            return True
        return RectDrawTool.press(self, event)

    def move(self, event: PageEvent) -> bool:
        return RectDrawTool.move(self, event)

    def release(self, event: PageEvent) -> bool:
        return RectDrawTool.release(self, event)

    def hover(self, event: PageEvent) -> None:
        self.viewer.viewport().setCursor(Qt.CursorShape.CrossCursor)

    def _choose(self) -> bytes | None:
        return self.tab.tool_options.signature

    def click(self, pno: int, event: PageEvent) -> None:
        data = self._choose()
        if data is None:
            return
        w_px, h_px = image_ops.image_size(data)
        width = 160.0
        height = width * h_px / w_px
        visual = QRectF(event.visual.x() - width / 2, event.visual.y() - height / 2, width, height)
        self._insert(pno, visual, data, "Place signature")

    def finish(self, pno: int, visual: QRectF, rect: pymupdf.Rect) -> None:
        data = self._choose()
        if data is not None:
            w_px, h_px = image_ops.image_size(data)
            fitted = image_ops.fit_rect((visual.left(), visual.top(), visual.right(), visual.bottom()), w_px, h_px)
            self._insert(pno, QRectF(fitted.x0, fitted.y0, fitted.width, fitted.height), data, "Place signature")
