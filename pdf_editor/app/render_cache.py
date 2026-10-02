"""Lazy page rendering: an LRU image cache plus a prioritised scheduler.

PyMuPDF is not thread-safe and holds the GIL while rendering, so rendering
happens on the GUI thread - but only for pages that are visible (plus a
small buffer), one page per event-loop iteration, highest priority first.
Input events are processed between pages, so scrolling stays smooth even
for documents with hundreds of pages.

Cache keys include the document's per-page revision, so edited pages are
re-rendered automatically and untouched pages stay cached.
"""

from __future__ import annotations

import heapq
import itertools
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Hashable

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QImage

from ..core.document import PdfDocument
from ..core.render import render_page
from .qt_utils import qimage_from_render

log = logging.getLogger(__name__)

DEFAULT_CACHE_BYTES = 256 * 1024 * 1024


class RenderCache:
    """Least-recently-used cache of rendered images, bounded by memory."""

    def __init__(self, max_bytes: int = DEFAULT_CACHE_BYTES) -> None:
        self.max_bytes = max_bytes
        self._items: OrderedDict[Hashable, QImage] = OrderedDict()
        self._bytes = 0

    def get(self, key: Hashable) -> QImage | None:
        image = self._items.get(key)
        if image is not None:
            self._items.move_to_end(key)
        return image

    def put(self, key: Hashable, image: QImage) -> None:
        old = self._items.pop(key, None)
        if old is not None:
            self._bytes -= old.sizeInBytes()
        self._items[key] = image
        self._bytes += image.sizeInBytes()
        while self._bytes > self.max_bytes and len(self._items) > 1:
            _, evicted = self._items.popitem(last=False)
            self._bytes -= evicted.sizeInBytes()

    def discard(self, predicate) -> None:
        """Remove all entries whose key satisfies ``predicate``."""
        for key in [k for k in self._items if predicate(k)]:
            self._bytes -= self._items.pop(key).sizeInBytes()

    def clear(self) -> None:
        self._items.clear()
        self._bytes = 0

    @property
    def size_bytes(self) -> int:
        return self._bytes

    def __len__(self) -> int:
        return len(self._items)


_shared_cache: RenderCache | None = None


def shared_cache() -> RenderCache:
    """The process-wide render cache shared by all open documents."""
    global _shared_cache
    if _shared_cache is None:
        _shared_cache = RenderCache()
    return _shared_cache


@dataclass(order=True)
class _Job:
    priority: int
    seq: int
    key: Hashable = field(compare=False)
    pno: int = field(compare=False)
    scale: float = field(compare=False)
    invert: bool = field(compare=False)
    clip: tuple[float, float, float, float] | None = field(compare=False)
    annots: bool = field(compare=False)


class RenderScheduler(QObject):
    """Queues render requests for one document and fulfils them lazily."""

    rendered = Signal(object)  # the key that is now available in the cache

    PRIORITY_VISIBLE = 0
    PRIORITY_DETAIL = 1
    PRIORITY_BUFFER = 2
    PRIORITY_THUMBNAIL = 3

    def __init__(self, doc: PdfDocument, cache: RenderCache | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.cache = cache or shared_cache()
        self._uid = id(self)
        self._heap: list[_Job] = []
        self._pending: dict[Hashable, _Job] = {}
        self._seq = itertools.count()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._process_one)

    def make_key(
        self, pno: int, scale: float, invert: bool, clip: tuple | None = None, annots: bool = True
    ) -> tuple:
        """Cache key for page ``pno`` rendered with these parameters."""
        return (self._uid, self.doc.page_key(pno), round(scale, 3), invert, clip, annots)

    def request(
        self,
        pno: int,
        scale: float,
        *,
        invert: bool = False,
        priority: int = PRIORITY_VISIBLE,
        clip: tuple[float, float, float, float] | None = None,
        annots: bool = True,
    ) -> tuple[tuple, QImage | None]:
        """Return ``(key, image)``; if not cached yet, schedule it and return ``None``."""
        key = self.make_key(pno, scale, invert, clip, annots)
        image = self.cache.get(key)
        if image is not None:
            return key, image
        existing = self._pending.get(key)
        if existing is None or existing.priority > priority:
            job = _Job(priority, next(self._seq), key, pno, scale, invert, clip, annots)
            self._pending[key] = job
            heapq.heappush(self._heap, job)
        if not self._timer.isActive():
            self._timer.start()
        return key, None

    def cancel_all(self, priorities: set[int] | None = None) -> None:
        """Drop pending jobs (all, or only those with one of ``priorities``)."""
        if priorities is None:
            self._heap.clear()
            self._pending.clear()
            return
        self._heap = [j for j in self._heap if j.priority not in priorities]
        heapq.heapify(self._heap)
        self._pending = {j.key: j for j in self._heap if self._pending.get(j.key) is j}

    def forget_document(self) -> None:
        """Drop all cached images of this scheduler (e.g. when the tab closes)."""
        self.cancel_all()
        uid = self._uid
        self.cache.discard(lambda k: isinstance(k, tuple) and k and k[0] == uid)

    def _process_one(self) -> None:
        while self._heap:
            job = heapq.heappop(self._heap)
            if self._pending.get(job.key) is not job:
                continue  # superseded by a higher-priority duplicate
            del self._pending[job.key]
            if self.doc.raw.is_closed or job.pno >= self.doc.page_count:
                continue
            if job.key != self.make_key(job.pno, job.scale, job.invert, job.clip, job.annots):
                continue  # the page changed since the request; a new one will come
            try:
                rendered = render_page(self.doc.raw, job.pno, job.scale, clip=job.clip, annots=job.annots)
                image = qimage_from_render(rendered)
                if job.invert:
                    image.invertPixels()
            except Exception:  # a broken page must not break the viewer
                log.exception("Rendering page %s failed", job.pno + 1)
                image = QImage(1, 1, QImage.Format.Format_RGB888)
                image.fill(0xFFFFFF)
            self.cache.put(job.key, image)
            self.rendered.emit(job.key)
            break
        if self._heap:
            self._timer.start()

    @property
    def pending_count(self) -> int:
        return len(self._pending)
