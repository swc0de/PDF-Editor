"""Lazy rendering for the viewer: request visible pages, show results (mixin)."""

from __future__ import annotations

import bisect

import pymupdf
from PySide6.QtCore import QRectF

from ..core.render import effective_scale

BUFFER_PAGES = 2
KEEP_IMAGES_DISTANCE = 6  # pages further away than this release their images


class RenderMixin:
    """Mixed into :class:`~pdf_editor.app.viewer.PdfViewer`."""

    def schedule_refresh(self) -> None:
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def visible_pages(self) -> list[int]:
        if not self._items:
            return []
        if not self._continuous:
            return [self._current]
        area = self.mapToScene(self.viewport().rect()).boundingRect()
        first = max(0, bisect.bisect_right(self._tops, area.top()) - 1)
        result = []
        for pno in range(first, len(self._items)):
            if self._items[pno].sceneBoundingRect().top() > area.bottom():
                break
            if self._items[pno].sceneBoundingRect().intersects(area):
                result.append(pno)
        return result

    def shutdown(self) -> None:
        """Stop all timers; the document is about to be closed."""
        self._refresh_timer.stop()
        self.scheduler.cancel_all()
        try:
            self.scheduler.rendered.disconnect(self._on_rendered)
        except (RuntimeError, TypeError):
            pass
        self._items = []

    def refresh_visible(self) -> None:
        """Request renders for visible/buffer pages and update the current page."""
        if self.doc.raw.is_closed:
            return
        visible = self.visible_pages()
        if not visible:
            return
        scale = self.transform().m11() * self.devicePixelRatioF()
        sched = self.scheduler
        sched.cancel_all({sched.PRIORITY_VISIBLE, sched.PRIORITY_DETAIL, sched.PRIORITY_BUFFER})
        area = self.mapToScene(self.viewport().rect()).boundingRect()
        for pno in visible:
            self._request(pno, scale, sched.PRIORITY_VISIBLE)
            self._request_detail(pno, scale, area)
        lo, hi = visible[0], visible[-1]
        for pno in list(range(max(0, lo - BUFFER_PAGES), lo)) + list(range(hi + 1, min(len(self._items), hi + 1 + BUFFER_PAGES))):
            self._request(pno, scale, sched.PRIORITY_BUFFER)
        for pno, item in enumerate(self._items):
            if (pno < lo - KEEP_IMAGES_DISTANCE or pno > hi + KEEP_IMAGES_DISTANCE) and item.image is not None:
                item.clear_images()
        if self._continuous:
            # the current page is the one under the viewport centre (or the most visible one)
            hit = self.page_at(self.mapToScene(self.viewport().rect().center()))
            if hit is None:
                hit = max(visible, key=lambda p: self._items[p].sceneBoundingRect().intersected(area).height())
            self._set_current(hit)

    def _request(self, pno: int, scale: float, priority: int) -> None:
        item = self._items[pno]
        key, image = self.scheduler.request(pno, scale, invert=self._invert, priority=priority)
        if image is not None:
            if item.image_key != key:
                item.set_image(key, image)
        else:
            item.pending_key = key

    def _request_detail(self, pno: int, scale: float, area: QRectF) -> None:
        """At high zoom the full-page image is size-capped; add a sharp tile."""
        item = self._items[pno]
        page_rect = item.page_rect()
        full = pymupdf.Rect(0, 0, page_rect.width(), page_rect.height())
        if effective_scale(full, scale) >= scale * 0.98:
            item.clear_detail()
            return
        visible = area.translated(-item.pos()).intersected(page_rect)
        if visible.isEmpty():
            return
        pad = 0.15
        clip = visible.adjusted(-visible.width() * pad, -visible.height() * pad, visible.width() * pad, visible.height() * pad)
        clip = clip.intersected(page_rect)
        # snap to a coarse grid so small scrolls reuse the tile
        g = 64 / scale
        clip_t = tuple(round(v / g) * g for v in (clip.left(), clip.top(), clip.right(), clip.bottom()))
        key, image = self.scheduler.request(
            pno, scale, invert=self._invert, priority=self.scheduler.PRIORITY_DETAIL, clip=clip_t
        )
        if image is not None:
            item.set_detail(key, image, QRectF(clip_t[0], clip_t[1], clip_t[2] - clip_t[0], clip_t[3] - clip_t[1]))
        else:
            item.pending_detail_key = key

    def _on_rendered(self, key: tuple) -> None:
        for item in self._items:
            if item.pending_key == key:
                image = self.scheduler.cache.get(key)
                if image is not None:
                    item.pending_key = None
                    item.set_image(key, image)
                return
            if item.pending_detail_key == key:
                image = self.scheduler.cache.get(key)
                clip = key[4]
                if image is not None and clip:
                    item.pending_detail_key = None
                    item.set_detail(key, image, QRectF(clip[0], clip[1], clip[2] - clip[0], clip[3] - clip[1]))
                return

    def refresh_pages(self, pages: list[int] | None = None) -> None:
        """Re-render pages whose content changed (others stay cached)."""
        targets = range(len(self._items)) if pages is None else [p for p in pages if 0 <= p < len(self._items)]
        for pno in targets:
            self._items[pno].pending_key = None
            self._items[pno].clear_detail()
        self.refresh_visible()
        self.viewport().update()
