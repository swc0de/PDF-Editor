"""Selection outline with resize handles for the selected annotation."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

HANDLE_PX = 8  # handle size in screen pixels
HANDLES = ("tl", "t", "tr", "r", "br", "b", "bl", "l")
CURSORS = {
    "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
    "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
    "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
    "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
    "move": Qt.CursorShape.SizeAllCursor,
}


def handle_points(rect: QRectF) -> dict[str, QPointF]:
    c = rect.center()
    return {
        "tl": rect.topLeft(), "t": QPointF(c.x(), rect.top()), "tr": rect.topRight(),
        "r": QPointF(rect.right(), c.y()), "br": rect.bottomRight(), "b": QPointF(c.x(), rect.bottom()),
        "bl": rect.bottomLeft(), "l": QPointF(rect.left(), c.y()),
    }


def resized(rect: QRectF, handle: str, delta: QPointF, keep_aspect: bool = False) -> QRectF:
    """Apply a handle drag of ``delta`` to ``rect`` (visual coordinates)."""
    r = QRectF(rect)
    if handle == "move":
        return r.translated(delta)
    if "l" in handle:
        r.setLeft(r.left() + delta.x())
    if "r" in handle:
        r.setRight(r.right() + delta.x())
    if handle.startswith("t"):
        r.setTop(r.top() + delta.y())
    if handle.startswith("b"):
        r.setBottom(r.bottom() + delta.y())
    r = r.normalized()
    if keep_aspect and rect.width() > 0 and rect.height() > 0 and len(handle) == 2:
        ratio = rect.width() / rect.height()
        if r.width() / max(r.height(), 1e-6) > ratio:
            r.setWidth(r.height() * ratio)
        else:
            r.setHeight(r.width() / ratio)
    return r


class AnnotationSelectionItem(QGraphicsItem):
    """Dashed outline plus handles, drawn as a child of the page item."""

    def __init__(self, rect: QRectF, resizable: bool = True, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self._rect = QRectF(rect)
        self.resizable = resizable
        self.scale_hint = 1.0  # view scale, to keep handles a constant screen size
        self.setZValue(30)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    @property
    def rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = QRectF(rect)
        self.update()

    def _handle_size(self) -> float:
        return HANDLE_PX / max(self.scale_hint, 1e-3)

    def boundingRect(self) -> QRectF:  # noqa: N802
        m = self._handle_size()
        return self._rect.adjusted(-m, -m, m, m)

    def hit_test(self, point: QPointF) -> str | None:
        """Which handle (or ``"move"``) is under ``point`` (visual coordinates)."""
        size = self._handle_size()
        if self.resizable:
            for name, center in handle_points(self._rect).items():
                if abs(point.x() - center.x()) <= size and abs(point.y() - center.y()) <= size:
                    return name
        if self._rect.adjusted(-size / 2, -size / 2, size / 2, size / 2).contains(point):
            return "move"
        return None

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        pen = QPen(QColor(30, 120, 255), 0, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._rect)
        if not self.resizable:
            return
        size = self._handle_size()
        solid = QPen(QColor(30, 120, 255))
        solid.setCosmetic(True)
        painter.setPen(solid)
        painter.setBrush(QBrush(QColor("#ffffff")))
        for center in handle_points(self._rect).values():
            painter.drawRect(QRectF(center.x() - size / 2, center.y() - size / 2, size, size))
