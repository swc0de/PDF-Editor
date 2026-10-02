"""Small Qt helpers: image conversion, colours, geometry and icons."""

from __future__ import annotations

from typing import Sequence

import pymupdf
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QApplication

from ..core.render import RenderedPage


def qimage_from_render(rendered: RenderedPage) -> QImage:
    """Copy a :class:`RenderedPage` into a ``QImage`` (which owns its data)."""
    fmt = QImage.Format.Format_RGBA8888 if rendered.alpha else QImage.Format.Format_RGB888
    image = QImage(rendered.samples, rendered.width, rendered.height, rendered.stride, fmt)
    return image.copy()  # detach from the Python bytes buffer


def qcolor(value: str | Sequence[float] | QColor | None, fallback: str = "#000000") -> QColor:
    """Build a QColor from ``#rrggbb``, a float RGB triple or a QColor."""
    if value is None:
        return QColor(fallback)
    if isinstance(value, QColor):
        return QColor(value)
    if isinstance(value, str):
        color = QColor(value)
        return color if color.isValid() else QColor(fallback)
    if len(value) == 3:
        return QColor.fromRgbF(*[max(0.0, min(1.0, float(v))) for v in value])
    if len(value) == 1:
        g = max(0.0, min(1.0, float(value[0])))
        return QColor.fromRgbF(g, g, g)
    return QColor(fallback)


def rgb_floats(color: QColor) -> tuple[float, float, float]:
    """QColor -> PyMuPDF float triple."""
    return (color.redF(), color.greenF(), color.blueF())


def rect_to_qrectf(rect: pymupdf.Rect | Sequence[float]) -> QRectF:
    r = pymupdf.Rect(rect)
    return QRectF(r.x0, r.y0, r.width, r.height)


def qrectf_to_rect(rect: QRectF) -> pymupdf.Rect:
    r = rect.normalized()
    return pymupdf.Rect(r.left(), r.top(), r.right(), r.bottom())


def qpoint_to_point(point: QPointF) -> pymupdf.Point:
    return pymupdf.Point(point.x(), point.y())


def is_dark_palette() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


_icon_cache: dict[tuple[str, bool], QIcon] = {}


def glyph_icon(glyph: str, *, bold: bool = False, color: str | None = None, size: int = 64) -> QIcon:
    """An icon drawn from a text glyph, coloured to match the current palette.

    Using glyphs keeps the app free of binary icon files while still giving
    every tool a recognisable symbol.
    """
    dark = is_dark_palette()
    key = (f"{glyph}|{bold}|{color}", dark)
    if key in _icon_cache:
        return _icon_cache[key]
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont()
    font.setPixelSize(int(size * (0.62 if len(glyph) == 1 else 0.38)))
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(QColor(color) if color else QColor("#e8e8e8" if dark else "#303030"))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    icon = QIcon(pixmap)
    _icon_cache[key] = icon
    return icon


def clear_icon_cache() -> None:
    """Forget cached icons (call after switching themes)."""
    _icon_cache.clear()


def color_swatch_icon(color: str, size: int = 32) -> QIcon:
    """A filled square icon showing ``color``."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(QColor("#555555"))
    painter.drawRoundedRect(QRectF(3, 3, size - 6, size - 6), 4, 4)
    painter.end()
    return QIcon(pixmap)
