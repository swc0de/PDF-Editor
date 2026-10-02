"""Mouse, wheel and keyboard handling for the viewer (dispatch to tools)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QGraphicsView

from .tools.base import PageEvent, Tool


class InputMixin:
    """Mixed into :class:`~pdf_editor.app.viewer.PdfViewer`."""

    @property
    def tool(self) -> Tool | None:
        return self._tool

    def set_tool(self, tool: Tool | None) -> None:
        if self._tool is not None:
            self._tool.deactivate()
        self._tool = tool
        hand = bool(tool and tool.hand_drag)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if hand else QGraphicsView.DragMode.NoDrag)
        if tool is not None:
            tool.activate()

    def _page_event(self, event: QMouseEvent, pno: int | None = None) -> PageEvent | None:
        scene = self.mapToScene(event.position().toPoint())
        hit = self.page_at(scene)
        if pno is None:
            pno = hit
        if pno is None:
            return None
        visual = scene - self._items[pno].pos()
        rect = self._items[pno].page_rect()
        inside = rect.contains(visual)
        clamped = QPointF(min(max(visual.x(), 0.0), rect.width()), min(max(visual.y(), 0.0), rect.height()))
        return PageEvent(
            pno, clamped, self.visual_to_page(pno, clamped), scene, event.button(), event.buttons(),
            event.modifiers(), inside, event.globalPosition().toPoint(),
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pe = self._page_event(event)
        if pe is not None and self._tool is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag_page = pe.pno
            if self._tool.press(pe):
                event.accept()
                return
        if pe is not None and self._tool is not None and event.button() == Qt.MouseButton.RightButton:
            if self._tool.context_menu(pe):
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._tool is not None:
            if self._drag_page is not None and event.buttons() & Qt.MouseButton.LeftButton:
                pe = self._page_event(event, self._drag_page)
                if pe is not None and self._tool.move(pe):
                    event.accept()
                    return
            elif not event.buttons():
                pe = self._page_event(event)
                if pe is not None:
                    self._tool.hover(pe)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._tool is not None and self._drag_page is not None and event.button() == Qt.MouseButton.LeftButton:
            pe = self._page_event(event, self._drag_page)
            self._drag_page = None
            if pe is not None and self._tool.release(pe):
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pe = self._page_event(event)
        if pe is not None and self._tool is not None and self._tool.double_click(pe):
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = event.angleDelta().y() / 120.0
            if steps:
                self.set_zoom(self._zoom * (1.15 ** steps), anchor=event.position())
            event.accept()
            return
        if not self._continuous:
            bar = self.verticalScrollBar()
            dy = event.angleDelta().y()
            if dy < 0 and bar.value() >= bar.maximum() and self._current < len(self._items) - 1:
                self.go_to_page(self._current + 1)
                event.accept()
                return
            if dy > 0 and bar.value() <= bar.minimum() and self._current > 0:
                self.go_to_page(self._current - 1)
                bar.setValue(bar.maximum())
                event.accept()
                return
        super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if self._tool is not None and self._tool.key_press(event):
            event.accept()
            return
        key = event.key()
        if not self._continuous and key in (Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
            self.next_page() if key == Qt.Key.Key_PageDown else self.previous_page()
            return
        if key == Qt.Key.Key_Home and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.go_to_page(0)
            return
        if key == Qt.Key.Key_End and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.go_to_page(len(self._items) - 1)
            return
        super().keyPressEvent(event)
