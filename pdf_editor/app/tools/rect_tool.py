"""Base class for tools that drag out a rectangle (crop, redact, shapes...)."""

from __future__ import annotations

import pymupdf
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QKeyEvent, QPen
from PySide6.QtWidgets import QGraphicsRectItem

from .base import PageEvent, Tool

MIN_SIZE = 3.0  # points; smaller drags count as clicks


class RectDrawTool(Tool):
    """Drag to draw a rectangle on one page; subclasses implement :meth:`finish`.

    Hold Shift for a square. A plain click calls :meth:`click` instead.
    """

    cursor = Qt.CursorShape.CrossCursor
    outline = QColor(30, 120, 255)
    fill = QColor(30, 120, 255, 40)
    dashed = True

    def __init__(self, tab) -> None:
        super().__init__(tab)
        self._start: QPointF | None = None
        self._page: int | None = None
        self._item: QGraphicsRectItem | None = None

    def press(self, event: PageEvent) -> bool:
        if not event.inside:
            return False
        self._cancel_drag()
        self._start, self._page = QPointF(event.visual), event.pno
        item = QGraphicsRectItem(QRectF(event.visual, event.visual), self.viewer.item(event.pno))
        pen = QPen(self.outline, 0, Qt.PenStyle.DashLine if self.dashed else Qt.PenStyle.SolidLine)
        pen.setCosmetic(True)
        pen.setWidth(1)
        item.setPen(pen)
        item.setBrush(QBrush(self.fill))
        item.setZValue(20)
        self._item = item
        return True

    def _rect(self, event: PageEvent) -> QRectF:
        assert self._start is not None
        end = QPointF(event.visual)
        if event.shift:
            side = max(abs(end.x() - self._start.x()), abs(end.y() - self._start.y()))
            end = QPointF(self._start.x() + (side if end.x() >= self._start.x() else -side),
                          self._start.y() + (side if end.y() >= self._start.y() else -side))
        return QRectF(self._start, end).normalized()

    def move(self, event: PageEvent) -> bool:
        if self._item is None:
            return False
        self._item.setRect(self._rect(event))
        return True

    def release(self, event: PageEvent) -> bool:
        if self._item is None or self._page is None:
            return False
        visual = self._rect(event)
        pno = self._page
        self._cancel_drag()
        if visual.width() < MIN_SIZE and visual.height() < MIN_SIZE:
            self.click(pno, event)
        else:
            self.finish(pno, visual, self.viewer.visual_rect_to_page(pno, visual))
        return True

    def _cancel_drag(self) -> None:
        if self._item is not None and self._item.scene() is not None:
            self._item.scene().removeItem(self._item)
        self._item = None
        self._start = self._page = None

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._item is not None:
            self._cancel_drag()
            return True
        return False

    def deactivate(self) -> None:
        self._cancel_drag()

    # -- subclass hooks ---------------------------------------------------------
    def finish(self, pno: int, visual: QRectF, rect: pymupdf.Rect) -> None:
        """A rectangle was drawn: ``visual`` in display coords, ``rect`` in page space."""

    def click(self, pno: int, event: PageEvent) -> None:
        """The mouse was clicked without dragging."""
