"""Text selection (drag, double-click word, select all) and copy."""

from __future__ import annotations

from collections import OrderedDict

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QGuiApplication, QKeyEvent, QKeySequence

from ...core.operations import text as text_ops
from .base import PageEvent, Tool


class TextSelector:
    """Caches page characters and turns drags into text selections."""

    MAX_CACHED_PAGES = 8

    def __init__(self, tab) -> None:
        self.tab = tab
        self._chars: OrderedDict[int, tuple[tuple, list[text_ops.CharBox], list[pymupdf.Rect]]] = OrderedDict()
        self.page: int | None = None
        self.selection: text_ops.TextSelection | None = None
        self._anchor: pymupdf.Point | None = None

    def chars(self, pno: int) -> list[text_ops.CharBox]:
        return self._entry(pno)[1]

    def _entry(self, pno: int):
        key = self.tab.doc.page_key(pno)
        entry = self._chars.get(pno)
        if entry is None or entry[0] != key:
            chars = text_ops.page_chars(self.tab.doc.raw[pno])
            lines: dict[int, pymupdf.Rect] = {}
            for ch in chars:
                lines[ch.line] = lines[ch.line] | ch.rect if ch.line in lines else pymupdf.Rect(ch.rect)
            entry = (key, chars, list(lines.values()))
            self._chars[pno] = entry
            while len(self._chars) > self.MAX_CACHED_PAGES:
                self._chars.popitem(last=False)
        self._chars.move_to_end(pno)
        return entry

    def over_text(self, pno: int, point: pymupdf.Point) -> bool:
        return any(r.contains(point) for r in self._entry(pno)[2])

    def begin(self, pno: int, point: pymupdf.Point) -> None:
        self.page, self._anchor = pno, pymupdf.Point(point)
        self.selection = None
        self.tab.viewer.clear_text_selection()

    def extend(self, point: pymupdf.Point) -> None:
        if self.page is None or self._anchor is None:
            return
        chars = self.chars(self.page)
        self.selection = text_ops.select_chars(chars, self._anchor, point)
        self._show()

    def select_word(self, pno: int, point: pymupdf.Point) -> None:
        self.page = pno
        self.selection = text_ops.word_at(self.chars(pno), point)
        self._show()

    def select_all(self, pno: int) -> None:
        self.page = pno
        chars = self.chars(pno)
        self.selection = text_ops.selection_from_range(chars, 0, len(chars) - 1) if chars else None
        self._show()

    def _show(self) -> None:
        if self.page is not None and self.selection is not None and not self.selection.is_empty:
            self.tab.viewer.set_text_selection(self.page, self.selection.rects)
        else:
            self.tab.viewer.clear_text_selection()

    def clear(self) -> None:
        self.page, self.selection, self._anchor = None, None, None
        self.tab.viewer.clear_text_selection()

    def invalidate(self) -> None:
        self._chars.clear()
        self.clear()

    @property
    def has_selection(self) -> bool:
        return self.selection is not None and not self.selection.is_empty

    def copy(self) -> bool:
        if not self.has_selection:
            return False
        QGuiApplication.clipboard().setText(self.selection.text)  # type: ignore[union-attr]
        return True


class TextSelectTool(Tool):
    """Select and copy text."""

    name = "select_text"
    label = "Select Text"
    tooltip = "Select text and copy it (drag, double-click a word, Ctrl+A for the page)"
    cursor = Qt.CursorShape.IBeamCursor

    def __init__(self, tab) -> None:
        super().__init__(tab)
        self.selector = tab.text_selector

    def press(self, event: PageEvent) -> bool:
        self.selector.begin(event.pno, event.point)
        return True

    def move(self, event: PageEvent) -> bool:
        self.selector.extend(event.point)
        return True

    def release(self, event: PageEvent) -> bool:
        self.selector.extend(event.point)
        self.tab.selection_changed()
        return True

    def double_click(self, event: PageEvent) -> bool:
        self.selector.select_word(event.pno, event.point)
        self.tab.selection_changed()
        return True

    def hover(self, event: PageEvent) -> None:
        shape = Qt.CursorShape.IBeamCursor if self.selector.over_text(event.pno, event.point) else Qt.CursorShape.ArrowCursor
        self.viewer.viewport().setCursor(QCursor(shape))

    def key_press(self, event: QKeyEvent) -> bool:
        if event.matches(QKeySequence.StandardKey.Copy):
            return self.selector.copy()
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.selector.select_all(self.viewer.current_page)
            self.tab.selection_changed()
            return True
        if event.key() == Qt.Key.Key_Escape and self.selector.has_selection:
            self.selector.clear()
            self.tab.selection_changed()
            return True
        return False

    def context_menu(self, event: PageEvent) -> bool:
        return self.tab.show_selection_menu(event)

    def deactivate(self) -> None:
        self.selector.clear()
        self.tab.selection_changed()

    def document_changed(self) -> None:
        self.selector.invalidate()


class HandTool(Tool):
    """Pan the view by dragging."""

    name = "hand"
    label = "Hand"
    tooltip = "Scroll by dragging the page"
    cursor = Qt.CursorShape.OpenHandCursor
    hand_drag = True
