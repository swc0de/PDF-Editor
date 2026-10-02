"""Annotation creation tools: markup, pen, shapes, notes, text boxes, stamps."""

from __future__ import annotations

import math

import pymupdf
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPathItem, QInputDialog

from ..errors import guarded
from .base import PageEvent, Tool
from .rect_tool import RectDrawTool
from .text_select import TextSelectTool


class _OptionsMixin:
    """Access to the shared tool options."""

    options_used: set[str] = set()
    hint = ""

    @property
    def options(self):
        return self.tab.tool_options

    def _author(self) -> str | None:
        return self.options.author or None


class MarkupTool(_OptionsMixin, TextSelectTool):
    """Drag across text to highlight / underline / strike it out."""

    kind = "highlight"
    cursor = Qt.CursorShape.IBeamCursor
    options_used = {"highlight", "opacity"}
    hint = "Drag across text"

    def release(self, event: PageEvent) -> bool:
        self.selector.extend(event.point)
        selection, pno = self.selector.selection, self.selector.page
        self.selector.clear()
        if selection is None or selection.is_empty or pno is None:
            return True
        color = self.options.highlight_rgb() if self.kind == "highlight" else self.options.stroke_rgb()
        with guarded(self.tab, "Cannot add markup"):
            self.doc.add_text_markup(pno, self.kind, selection.quads, color, self.options.opacity,
                                     self._author(), selection.text)
        return True

    def context_menu(self, event: PageEvent) -> bool:
        return False


class HighlightTool(MarkupTool):
    name, label, kind = "highlight", "Highlight", "highlight"


class UnderlineTool(MarkupTool):
    name, label, kind = "underline", "Underline", "underline"
    options_used = {"stroke", "opacity"}


class StrikeoutTool(MarkupTool):
    name, label, kind = "strikeout", "Strikethrough", "strikeout"
    options_used = {"stroke", "opacity"}


class PenTool(_OptionsMixin, Tool):
    """Freehand drawing; each stroke becomes an ink annotation."""

    name, label = "pen", "Pen"
    cursor = Qt.CursorShape.CrossCursor
    options_used = {"stroke", "width", "opacity"}
    hint = "Draw freehand"

    def __init__(self, tab) -> None:
        super().__init__(tab)
        self._points: list[pymupdf.Point] = []
        self._path: QPainterPath | None = None
        self._item: QGraphicsPathItem | None = None
        self._page: int | None = None

    def press(self, event: PageEvent) -> bool:
        if not event.inside:
            return False
        self._page = event.pno
        self._points = [event.point]
        self._path = QPainterPath(event.visual)
        self._item = QGraphicsPathItem(self._path, self.viewer.item(event.pno))
        pen = QPen(QColor(self.options.stroke), self.options.width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self._item.setPen(pen)
        self._item.setOpacity(self.options.opacity)
        self._item.setZValue(20)
        return True

    def move(self, event: PageEvent) -> bool:
        if self._item is None or self._path is None:
            return False
        if self._points and abs(event.point.x - self._points[-1].x) + abs(event.point.y - self._points[-1].y) < 0.7:
            return True
        self._points.append(event.point)
        self._path.lineTo(event.visual)
        self._item.setPath(self._path)
        return True

    def release(self, event: PageEvent) -> bool:
        if self._item is None or self._page is None:
            return False
        self._remove_preview()
        points, pno = self._points, self._page
        self._points, self._page = [], None
        if len(points) < 2:
            return True
        with guarded(self.tab, "Cannot add drawing"):
            self.doc.add_ink(pno, [[(p.x, p.y) for p in points]], self.options.stroke_rgb(),
                             self.options.width, self.options.opacity, self._author())
        return True

    def _remove_preview(self) -> None:
        if self._item is not None and self._item.scene() is not None:
            self._item.scene().removeItem(self._item)
        self._item = self._path = None

    def deactivate(self) -> None:
        self._remove_preview()


class ShapeTool(_OptionsMixin, RectDrawTool):
    """Rectangles and ellipses (drag; Shift for a square/circle)."""

    shape = "rect"
    dashed = False
    options_used = {"stroke", "fill", "width", "opacity"}
    hint = "Drag to draw (Shift keeps it square)"

    def press(self, event: PageEvent) -> bool:
        handled = super().press(event)
        if handled and self._item is not None:
            self._item.setPen(QPen(QColor(self.options.stroke), self.options.width))
            self._item.setBrush(QColor(self.options.fill) if self.options.fill else Qt.BrushStyle.NoBrush)
        return handled

    def finish(self, pno: int, visual: QRectF, rect: pymupdf.Rect) -> None:
        with guarded(self.tab, "Cannot add shape"):
            self.doc.add_shape(pno, self.shape, rect.tl, rect.br, self.options.stroke_rgb(), self.options.fill_rgb(),
                               self.options.width, self.options.opacity, self._author())


class RectangleTool(ShapeTool):
    name, label, shape = "rectangle", "Rectangle", "rect"


class EllipseTool(ShapeTool):
    name, label, shape = "ellipse", "Ellipse", "ellipse"

    def press(self, event: PageEvent) -> bool:
        if not super().press(event):
            return False
        # swap the rectangle preview for an ellipse
        old = self._item
        item = QGraphicsEllipseItem(old.rect(), old.parentItem())
        item.setPen(old.pen())
        item.setBrush(old.brush())
        item.setZValue(old.zValue())
        old.scene().removeItem(old)
        self._item = item
        return True


class LineTool(_OptionsMixin, Tool):
    """Straight lines and arrows (Shift snaps to 45°)."""

    name, label, kind = "line", "Line", "line"
    cursor = Qt.CursorShape.CrossCursor
    options_used = {"stroke", "width", "opacity"}
    hint = "Drag to draw (Shift snaps to 45°)"

    def __init__(self, tab) -> None:
        super().__init__(tab)
        self._start: QPointF | None = None
        self._page: int | None = None
        self._item: QGraphicsLineItem | None = None

    def press(self, event: PageEvent) -> bool:
        if not event.inside:
            return False
        self._start, self._page = QPointF(event.visual), event.pno
        self._item = QGraphicsLineItem(QLineF(event.visual, event.visual), self.viewer.item(event.pno))
        self._item.setPen(QPen(QColor(self.options.stroke), self.options.width))
        self._item.setZValue(20)
        return True

    def _end(self, event: PageEvent) -> QPointF:
        assert self._start is not None
        end = QPointF(event.visual)
        if event.shift:
            dx, dy = end.x() - self._start.x(), end.y() - self._start.y()
            angle = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
            length = math.hypot(dx, dy)
            end = QPointF(self._start.x() + length * math.cos(angle), self._start.y() + length * math.sin(angle))
        return end

    def move(self, event: PageEvent) -> bool:
        if self._item is None or self._start is None:
            return False
        self._item.setLine(QLineF(self._start, self._end(event)))
        return True

    def release(self, event: PageEvent) -> bool:
        if self._item is None or self._start is None or self._page is None:
            return False
        end, start, pno = self._end(event), self._start, self._page
        self._cancel()
        if QLineF(start, end).length() < 2:
            return True
        p1, p2 = self.viewer.visual_to_page(pno, start), self.viewer.visual_to_page(pno, end)
        with guarded(self.tab, "Cannot add line"):
            self.doc.add_shape(pno, self.kind, p1, p2, self.options.stroke_rgb(), None, self.options.width,
                               self.options.opacity, self._author())
        return True

    def _cancel(self) -> None:
        if self._item is not None and self._item.scene() is not None:
            self._item.scene().removeItem(self._item)
        self._item = self._start = self._page = None

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._item is not None:
            self._cancel()
            return True
        return False

    def deactivate(self) -> None:
        self._cancel()


class ArrowTool(LineTool):
    name, label, kind = "arrow", "Arrow", "arrow"


class NoteTool(_OptionsMixin, Tool):
    """Click to add a sticky note."""

    name, label = "note", "Sticky Note"
    cursor = Qt.CursorShape.CrossCursor
    options_used = {"stroke", "icon"}
    hint = "Click where the note should go"

    def press(self, event: PageEvent) -> bool:
        if not event.inside:
            return False
        text, ok = QInputDialog.getMultiLineText(self.tab, "Sticky Note", "Comment:")
        if ok and text.strip():
            with guarded(self.tab, "Cannot add note"):
                self.doc.add_sticky_note(event.pno, event.point, text, self.options.stroke_rgb(),
                                         self.options.note_icon, self._author())
        return True


class TextBoxTool(_OptionsMixin, RectDrawTool):
    """Drag (or click) to add a text box."""

    name, label = "textbox", "Text Box"
    options_used = {"stroke", "fill", "font"}
    hint = "Drag a box (or click), then type the text"

    def finish(self, pno: int, visual: QRectF, rect: pymupdf.Rect) -> None:
        text, ok = QInputDialog.getMultiLineText(self.tab, "Text Box", "Text:")
        if ok and text.strip():
            with guarded(self.tab, "Cannot add text box"):
                self.doc.add_text_box(pno, rect, text, self.options.font_size, self.options.stroke_rgb(),
                                      self.options.fill_rgb(), 1 if self.options.fill else 0, author=self._author())

    def click(self, pno: int, event: PageEvent) -> None:
        width, height = 200.0, self.options.font_size * 3
        visual = QRectF(event.visual.x(), event.visual.y(), width, height)
        self.finish(pno, visual, self.viewer.visual_rect_to_page(pno, visual))


class StampTool(_OptionsMixin, RectDrawTool):
    """Click (or drag a box) to place the chosen stamp."""

    name, label = "stamp", "Stamp"
    options_used = {"stamp"}
    hint = "Click to place the stamp, or drag to size it"

    def click(self, pno: int, event: PageEvent) -> None:
        size = (150.0, 150.0) if self.options.stamp_image else (180.0, 54.0)
        visual = QRectF(event.visual.x() - size[0] / 2, event.visual.y() - size[1] / 2, *size)
        self.finish(pno, visual, self.viewer.visual_rect_to_page(pno, visual))

    def finish(self, pno: int, visual: QRectF, rect: pymupdf.Rect) -> None:
        with guarded(self.tab, "Cannot add stamp"):
            if self.options.stamp_image:
                with open(self.options.stamp_image, "rb") as fh:
                    self.doc.add_image_stamp(pno, rect, fh.read(), self._author())
            else:
                self.doc.add_stamp(pno, rect, self.options.stamp or "Approved", self._author())
