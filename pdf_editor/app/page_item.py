"""A graphics item showing one rendered page in the viewer."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget


class PageItem(QGraphicsItem):
    """Draws the best available image of a page.

    Item coordinates are *visual* page coordinates in points: ``(0, 0)`` is
    the top-left corner of the page as displayed (after rotation/cropping).
    Overlay items (highlights, selection handles) are children using the
    same coordinates.
    """

    def __init__(self, pno: int, width: float, height: float) -> None:
        super().__init__()
        self.pno = pno
        self._rect = QRectF(0, 0, width, height)
        self.image: QImage | None = None
        self.image_key: tuple | None = None
        self.detail: QImage | None = None
        self.detail_rect: QRectF | None = None
        self.detail_key: tuple | None = None
        self.pending_key: tuple | None = None
        self.pending_detail_key: tuple | None = None
        self.inverted = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)

    # -- geometry -----------------------------------------------------------
    def boundingRect(self) -> QRectF:  # noqa: N802 (Qt naming)
        return self._rect.adjusted(-1, -1, 3, 3)  # room for border and shadow

    def page_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_size(self, width: float, height: float) -> None:
        if width != self._rect.width() or height != self._rect.height():
            self.prepareGeometryChange()
            self._rect = QRectF(0, 0, width, height)
            self.clear_images()

    # -- images -------------------------------------------------------------
    def set_image(self, key: tuple, image: QImage) -> None:
        self.image, self.image_key = image, key
        self.update()

    def set_detail(self, key: tuple, image: QImage, rect: QRectF) -> None:
        self.detail, self.detail_key, self.detail_rect = image, key, rect
        self.update()

    def clear_detail(self) -> None:
        if self.detail is not None:
            self.detail = self.detail_rect = self.detail_key = None
            self.update()

    def clear_images(self) -> None:
        """Release images (they stay in the shared cache)."""
        self.image = self.image_key = None
        self.detail = self.detail_rect = self.detail_key = None
        self.pending_key = self.pending_detail_key = None
        self.update()

    # -- painting -------------------------------------------------------------
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        rect = self._rect
        painter.fillRect(rect.translated(2, 2), QColor(0, 0, 0, 60))  # drop shadow
        painter.fillRect(rect, QColor("#111111") if self.inverted else QColor("#ffffff"))
        if self.image is not None:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawImage(rect, self.image)
        else:
            painter.setPen(QColor("#9a9a9a"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self.pno + 1}")
        if self.detail is not None and self.detail_rect is not None:
            painter.drawImage(self.detail_rect, self.detail)
        pen = QPen(QColor(0, 0, 0, 70))
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
