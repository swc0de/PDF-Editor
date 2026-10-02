"""The page canvas: a QGraphicsView showing pages in continuous or single-page mode.

Scene units are PDF points; zoom is applied through the view transform.
Only pages intersecting the viewport (plus a small buffer) are rendered;
far-away pages drop their image references so the LRU cache can evict them.
"""

from __future__ import annotations

import bisect

import pymupdf
from PySide6.QtCore import QPointF, QRectF, QTimer, Signal
from PySide6.QtGui import QPainter, QTransform
from PySide6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView

from ..core.document import PdfDocument
from .overlays import OverlayMixin
from .viewer_input import InputMixin
from .viewer_render import RenderMixin
from .page_item import PageItem
from .render_cache import RenderScheduler
from .tools.base import Tool

ZOOM_STEPS = [0.1, 0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]
MIN_ZOOM, MAX_ZOOM = 0.1, 8.0
PAGE_GAP = 14.0
MARGIN = 18.0


class PdfViewer(InputMixin, RenderMixin, OverlayMixin, QGraphicsView):
    """Continuous-scroll / single-page PDF canvas with lazy rendering."""

    currentPageChanged = Signal(int)
    zoomChanged = Signal(float)
    layoutChanged = Signal()

    def __init__(self, doc: PdfDocument, scheduler: RenderScheduler, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.scheduler = scheduler
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setAcceptDrops(False)  # file drops are handled by the main window
        self.setMouseTracking(True)
        self._items: list[PageItem] = []
        self._geom: list[tuple[pymupdf.Matrix, pymupdf.Matrix]] = []
        self._tops: list[float] = []
        self._zoom = 1.0
        self._fit_mode: str | None = "fit-width"
        self._continuous = True
        self._invert = False
        self._current = 0
        self._tool: Tool | None = None
        self._drag_page: int | None = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(15)
        self._refresh_timer.timeout.connect(self.refresh_visible)
        scheduler.rendered.connect(self._on_rendered)
        self.verticalScrollBar().valueChanged.connect(self.schedule_refresh)
        self.horizontalScrollBar().valueChanged.connect(self.schedule_refresh)
        self.init_overlays()
        self.rebuild()

    # ------------------------------------------------------------------
    # layout
    def rebuild(self, keep_page: bool = True) -> None:
        """(Re)create page items after pages were added, removed, rotated or resized."""
        current = self._current if keep_page else 0
        scene = self.scene()
        self.clear_overlays()
        for item in self._items:
            scene.removeItem(item)
        self._items, self._geom = [], []
        for pno in range(self.doc.page_count):
            page = self.doc.raw[pno]
            rect = page.rect
            item = PageItem(pno, rect.width, rect.height)
            item.inverted = self._invert
            scene.addItem(item)
            self._items.append(item)
            self._geom.append((pymupdf.Matrix(page.rotation_matrix), pymupdf.Matrix(page.derotation_matrix)))
        self._current = max(0, min(current, len(self._items) - 1))
        self._layout()
        if self._fit_mode:
            self._apply_fit()
        self.go_to_page(self._current)
        self.layoutChanged.emit()

    def _layout(self) -> None:
        if not self._items:
            self.scene().setSceneRect(QRectF(0, 0, 100, 100))
            return
        max_w = max(i.page_rect().width() for i in self._items)
        y = MARGIN
        self._tops = []
        for item in self._items:
            r = item.page_rect()
            x = MARGIN + (max_w - r.width()) / 2
            if self._continuous:
                item.setPos(x, y)
                item.setVisible(True)
                self._tops.append(y)
                y += r.height() + PAGE_GAP
            else:
                item.setPos(x, MARGIN)
                item.setVisible(item.pno == self._current)
                self._tops.append(MARGIN)
        if self._continuous:
            height = y - PAGE_GAP + MARGIN
        else:
            height = self._items[self._current].page_rect().height() + 2 * MARGIN
        self.scene().setSceneRect(QRectF(0, 0, max_w + 2 * MARGIN, height))

    def update_page_sizes(self) -> None:
        """Refresh sizes after crop/rotate without losing the scroll position."""
        if len(self._items) != self.doc.page_count:
            self.rebuild()
            return
        for pno, item in enumerate(self._items):
            page = self.doc.raw[pno]
            item.set_size(page.rect.width, page.rect.height)
            self._geom[pno] = (pymupdf.Matrix(page.rotation_matrix), pymupdf.Matrix(page.derotation_matrix))
        self._layout()
        self.refresh_visible()

    # ------------------------------------------------------------------
    # modes
    @property
    def continuous(self) -> bool:
        return self._continuous

    def set_continuous(self, continuous: bool) -> None:
        if continuous == self._continuous:
            return
        page = self._current
        self._continuous = continuous
        self._layout()
        self.go_to_page(page)

    def set_invert(self, invert: bool) -> None:
        self._invert = invert
        for item in self._items:
            item.inverted = invert
            item.clear_images()
        self.refresh_visible()

    # ------------------------------------------------------------------
    # zoom
    def dpi_scale(self) -> float:
        return self.logicalDpiX() / 72.0

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def fit_mode(self) -> str | None:
        return self._fit_mode

    def set_zoom(self, zoom: float, *, anchor: QPointF | None = None, keep_fit: bool = False) -> None:
        """Set zoom (1.0 = 100 %). ``anchor`` is a viewport point that stays fixed."""
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        if not keep_fit:
            self._fit_mode = None
        anchor = anchor if anchor is not None else QPointF(self.viewport().rect().center())
        scene_anchor = self.mapToScene(anchor.toPoint())
        self._zoom = zoom
        s = zoom * self.dpi_scale()
        self.setTransform(QTransform.fromScale(s, s))
        # keep the scene point under the anchor where it was
        delta = self.mapFromScene(scene_anchor) - anchor.toPoint()
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + delta.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + delta.y())
        for item in self._items:
            item.clear_detail()
        self.zoomChanged.emit(zoom)
        self.schedule_refresh()

    def zoom_in(self) -> None:
        self.set_zoom(next((z for z in ZOOM_STEPS if z > self._zoom + 1e-3), MAX_ZOOM))

    def zoom_out(self) -> None:
        self.set_zoom(next((z for z in reversed(ZOOM_STEPS) if z < self._zoom - 1e-3), MIN_ZOOM))

    def fit_width(self) -> None:
        self._fit_mode = "fit-width"
        self._apply_fit()

    def fit_page(self) -> None:
        self._fit_mode = "fit-page"
        self._apply_fit()

    def _apply_fit(self) -> None:
        if not self._items:
            return
        vw = max(50, self.viewport().width() - 2 * MARGIN - 4)
        vh = max(50, self.viewport().height() - 2 * MARGIN - 4)
        dpi = self.dpi_scale()
        if self._fit_mode == "fit-width":
            widest = max(i.page_rect().width() for i in self._items)
            zoom = vw / (widest * dpi)
        else:
            r = self._items[self._current].page_rect()
            zoom = min(vw / (r.width() * dpi), vh / (r.height() * dpi))
        page = self._current
        self.set_zoom(zoom, keep_fit=True)
        self.go_to_page(page)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._fit_mode:
            self._apply_fit()
        self.schedule_refresh()

    # ------------------------------------------------------------------
    # navigation
    @property
    def current_page(self) -> int:
        return self._current

    @property
    def page_count(self) -> int:
        return len(self._items)

    def item(self, pno: int) -> PageItem:
        return self._items[pno]

    def go_to_page(self, pno: int, visual_y: float | None = None) -> None:
        """Show page ``pno``; optionally scroll to ``visual_y`` on that page."""
        if not self._items:
            return
        pno = max(0, min(pno, len(self._items) - 1))
        if not self._continuous and pno != self._current:
            self._current = pno
            self._layout()
        item = self._items[pno]
        top = item.pos().y() + (visual_y if visual_y is not None else 0) - (MARGIN if visual_y is None else 40)
        view_h = self.viewport().height() / self.transform().m11()
        self.centerOn(QPointF(self.sceneRect().center().x(), top + view_h / 2))
        self._set_current(pno)
        self.schedule_refresh()

    def next_page(self) -> None:
        self.go_to_page(self._current + 1)

    def previous_page(self) -> None:
        self.go_to_page(self._current - 1)

    def scroll_to_page_rect(self, pno: int, rect: pymupdf.Rect) -> None:
        """Make an unrotated page rectangle visible (e.g. a search hit)."""
        if not self._continuous and pno != self._current:
            self.go_to_page(pno)
        scene_rect = self.page_rect_to_scene(pno, rect)
        self.ensureVisible(scene_rect, 80, 120)
        self.schedule_refresh()

    def _set_current(self, pno: int) -> None:
        if pno != self._current or not self._continuous:
            changed = pno != self._current
            self._current = pno
            if changed:
                self.currentPageChanged.emit(pno)

    # ------------------------------------------------------------------
    # coordinate mapping
    def page_at(self, scene_pos: QPointF) -> int | None:
        for pno in self._candidate_pages(scene_pos.y()):
            item = self._items[pno]
            if item.isVisible() and item.sceneBoundingRect().contains(scene_pos):
                return pno
        return None

    def _candidate_pages(self, y: float) -> list[int]:
        if not self._continuous:
            return [self._current]
        i = bisect.bisect_right(self._tops, y) - 1
        return [p for p in (i, i + 1, i - 1) if 0 <= p < len(self._items)]

    def visual_to_page(self, pno: int, visual: QPointF) -> pymupdf.Point:
        return pymupdf.Point(visual.x(), visual.y()) * self._geom[pno][1]

    def page_to_visual(self, pno: int, point: pymupdf.Point) -> QPointF:
        p = pymupdf.Point(point) * self._geom[pno][0]
        return QPointF(p.x, p.y)

    def page_rect_to_visual(self, pno: int, rect: pymupdf.Rect) -> QRectF:
        r = (pymupdf.Rect(rect) * self._geom[pno][0]).normalize()
        return QRectF(r.x0, r.y0, r.width, r.height)

    def visual_rect_to_page(self, pno: int, rect: QRectF) -> pymupdf.Rect:
        r = pymupdf.Rect(rect.left(), rect.top(), rect.right(), rect.bottom())
        return (r * self._geom[pno][1]).normalize()

    def page_rect_to_scene(self, pno: int, rect: pymupdf.Rect) -> QRectF:
        return self.page_rect_to_visual(pno, rect).translated(self._items[pno].pos())

    def rotation_matrix(self, pno: int) -> pymupdf.Matrix:
        return self._geom[pno][0]
