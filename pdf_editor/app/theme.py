"""Light and dark themes (Fusion style with custom palettes)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

from .qt_utils import clear_icon_cache

_original_style: str | None = None
_original_palette: QPalette | None = None

# Colour of the empty area around pages in the viewer.
CANVAS_LIGHT = QColor("#d6d8dc")
CANVAS_DARK = QColor("#2b2d31")


def _dark_palette() -> QPalette:
    p = QPalette()
    base, alt, text = QColor("#1f2125"), QColor("#2a2c31"), QColor("#e6e6e6")
    window, button = QColor("#2d2f34"), QColor("#35383e")
    highlight = QColor("#3d7eea")
    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, alt)
    p.setColor(QPalette.ColorRole.ToolTipBase, window)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, button)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, QColor("#ff6b6b"))
    p.setColor(QPalette.ColorRole.Link, QColor("#7aa7ff"))
    p.setColor(QPalette.ColorRole.Highlight, highlight)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8a8d93"))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor("#777a80"))
    return p


def _light_palette() -> QPalette:
    p = QStyleFactory.create("Fusion").standardPalette()
    p.setColor(QPalette.ColorRole.Highlight, QColor("#2f6fdf"))
    return p


def system_prefers_dark() -> bool:
    hints = QGuiApplication.styleHints()
    try:
        return hints.colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt < 6.5
        return False


def resolve_theme(theme: str) -> str:
    """Map ``system`` to ``light``/``dark``."""
    if theme == "system":
        return "dark" if system_prefers_dark() else "light"
    return theme


def apply_theme(app: QApplication, theme: str) -> str:
    """Apply ``light``, ``dark`` or ``system``; returns the effective theme."""
    global _original_style, _original_palette
    if _original_style is None:
        _original_style = app.style().name()
        _original_palette = app.palette()
    effective = resolve_theme(theme)
    app.setStyle("Fusion")
    app.setPalette(_dark_palette() if effective == "dark" else _light_palette())
    clear_icon_cache()
    return effective


def canvas_color(theme: str) -> QColor:
    return CANVAS_DARK if theme == "dark" else CANVAS_LIGHT
