"""Base class for interactive viewer tools (one subclass per tool)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pymupdf
from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QCursor, QKeyEvent

if TYPE_CHECKING:  # pragma: no cover
    from ..document_tab import DocumentTab


@dataclass
class PageEvent:
    """A mouse event translated into page coordinates.

    ``visual`` is in displayed page coordinates (points, rotation applied),
    ``point`` is the same location in unrotated PyMuPDF page space - the
    coordinates used by annotations, text extraction and editing.
    """

    pno: int
    visual: QPointF
    point: pymupdf.Point
    scene: QPointF
    button: Qt.MouseButton
    buttons: Qt.MouseButton
    modifiers: Qt.KeyboardModifier
    inside: bool
    global_pos: QPoint

    @property
    def shift(self) -> bool:
        return bool(self.modifiers & Qt.KeyboardModifier.ShiftModifier)

    @property
    def ctrl(self) -> bool:
        return bool(self.modifiers & Qt.KeyboardModifier.ControlModifier)


class Tool(QObject):
    """An interactive mode of the viewer (select text, draw, place stamp...).

    Handlers return ``True`` when they consumed the event.
    """

    name = "tool"
    label = "Tool"
    tooltip = ""
    cursor: Qt.CursorShape = Qt.CursorShape.ArrowCursor
    hand_drag = False  # let the view pan with the mouse (hand tool)

    def __init__(self, tab: "DocumentTab") -> None:
        super().__init__(tab)
        self.tab = tab

    @property
    def viewer(self):
        return self.tab.viewer

    @property
    def doc(self):
        return self.tab.doc

    @property
    def settings(self):
        return self.tab.settings

    def activate(self) -> None:
        """Called when the tool becomes active."""
        self.viewer.viewport().setCursor(QCursor(self.cursor))

    def deactivate(self) -> None:
        """Called when another tool is chosen; clean up temporary items."""

    def press(self, event: PageEvent) -> bool:
        return False

    def move(self, event: PageEvent) -> bool:
        return False

    def release(self, event: PageEvent) -> bool:
        return False

    def double_click(self, event: PageEvent) -> bool:
        return False

    def hover(self, event: PageEvent) -> None:
        """Mouse moved without a button pressed."""

    def key_press(self, event: QKeyEvent) -> bool:
        return False

    def context_menu(self, event: PageEvent) -> bool:
        return False

    def document_changed(self) -> None:
        """The document changed (e.g. undo); drop stale state."""
