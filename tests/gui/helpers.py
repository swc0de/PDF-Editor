"""Helpers for driving viewer tools in GUI tests."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt

from pdf_editor.app.tools.base import PageEvent


def page_event(tab, pno: int, x: float, y: float, *, shift: bool = False, ctrl: bool = False) -> PageEvent:
    """A synthetic PageEvent at visual page coordinates ``(x, y)``."""
    visual = QPointF(x, y)
    modifiers = Qt.KeyboardModifier.NoModifier
    if shift:
        modifiers |= Qt.KeyboardModifier.ShiftModifier
    if ctrl:
        modifiers |= Qt.KeyboardModifier.ControlModifier
    item = tab.viewer.item(pno)
    return PageEvent(
        pno=pno,
        visual=visual,
        point=tab.viewer.visual_to_page(pno, visual),
        scene=visual + item.pos(),
        button=Qt.MouseButton.LeftButton,
        buttons=Qt.MouseButton.LeftButton,
        modifiers=modifiers,
        inside=item.page_rect().contains(visual),
        global_pos=QPoint(0, 0),
    )


def drag(tool, tab, pno: int, start: tuple[float, float], end: tuple[float, float], steps: int = 3) -> None:
    """Press at ``start``, move in a few steps and release at ``end``."""
    tool.press(page_event(tab, pno, *start))
    for i in range(1, steps + 1):
        x = start[0] + (end[0] - start[0]) * i / steps
        y = start[1] + (end[1] - start[1]) * i / steps
        tool.move(page_event(tab, pno, x, y))
    tool.release(page_event(tab, pno, *end))
