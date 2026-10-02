"""Overlay graphics on top of pages: search hits and text selection."""

from __future__ import annotations

from typing import Iterable

import pymupdf
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem

HIT_COLOR = QColor(255, 200, 0, 90)
CURRENT_HIT_COLOR = QColor(255, 120, 0, 140)
SELECTION_COLOR = QColor(40, 120, 255, 80)
MAX_HIGHLIGHT_ITEMS = 5000


def _rect_item(parent, rect: QRectF, color: QColor, z: float) -> QGraphicsRectItem:
    item = QGraphicsRectItem(rect, parent)
    item.setBrush(QBrush(color))
    item.setPen(QPen(Qt.PenStyle.NoPen))
    item.setZValue(z)
    item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
    return item


class OverlayMixin:
    """Mixed into :class:`~pdf_editor.app.viewer.PdfViewer`."""

    def init_overlays(self) -> None:
        self._hit_items: list[QGraphicsRectItem] = []
        self._current_hit_items: list[QGraphicsRectItem] = []
        self._selection_items: list[QGraphicsRectItem] = []
        self._selection_page: int | None = None
        self._selection_rects: list[pymupdf.Rect] = []

    def clear_overlays(self) -> None:
        self.clear_search_highlights()
        self.clear_text_selection()

    # -- search -------------------------------------------------------------
    def clear_search_highlights(self) -> None:
        for item in self._hit_items + self._current_hit_items:
            if item.scene() is not None:
                item.scene().removeItem(item)
        self._hit_items, self._current_hit_items = [], []

    def add_search_highlights(self, pno: int, hits: Iterable[Iterable[pymupdf.Rect]]) -> None:
        """Add highlight boxes for all hits on one page (unrotated rects)."""
        if pno >= self.page_count:
            return
        parent = self.item(pno)
        for rects in hits:
            for rect in rects:
                if len(self._hit_items) >= MAX_HIGHLIGHT_ITEMS:
                    return
                self._hit_items.append(_rect_item(parent, self.page_rect_to_visual(pno, rect), HIT_COLOR, 5))

    def set_current_hit(self, pno: int | None, rects: Iterable[pymupdf.Rect] = ()) -> None:
        """Emphasise the current search hit and scroll it into view."""
        for item in self._current_hit_items:
            if item.scene() is not None:
                item.scene().removeItem(item)
        self._current_hit_items = []
        if pno is None or pno >= self.page_count:
            return
        rects = list(rects)
        for rect in rects:
            self._current_hit_items.append(
                _rect_item(self.item(pno), self.page_rect_to_visual(pno, rect), CURRENT_HIT_COLOR, 6)
            )
        if rects:
            union = pymupdf.Rect(rects[0])
            for r in rects[1:]:
                union |= r
            self.scroll_to_page_rect(pno, union)

    # -- text selection ---------------------------------------------------------
    def set_text_selection(self, pno: int, rects: Iterable[pymupdf.Rect]) -> None:
        self.clear_text_selection()
        if pno >= self.page_count:
            return
        self._selection_page = pno
        self._selection_rects = [pymupdf.Rect(r) for r in rects]
        for rect in self._selection_rects:
            self._selection_items.append(
                _rect_item(self.item(pno), self.page_rect_to_visual(pno, rect), SELECTION_COLOR, 7)
            )

    def clear_text_selection(self) -> None:
        for item in self._selection_items:
            if item.scene() is not None:
                item.scene().removeItem(item)
        self._selection_items = []
        self._selection_page = None
        self._selection_rects = []
