"""Page thumbnail sidebar: lazy rendering, multi-select, drag to reorder."""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QAbstractListModel, QByteArray, QMimeData, QModelIndex, QPersistentModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListView, QWidget

from .render_cache import RenderScheduler

MIME_PAGES = "application/x-pdfeditor-pages"
THUMB_WIDTH = 110
THUMB_HEIGHT = 150
MAX_CACHED_PIXMAPS = 400
_Index = QModelIndex | QPersistentModelIndex


class ThumbnailModel(QAbstractListModel):
    """One row per page; images come from the shared render cache."""

    pagesDropped = Signal(list, int)  # page indices, target index
    filesDropped = Signal(list, int)  # file paths, target index

    def __init__(self, doc, scheduler: RenderScheduler, device_ratio: float, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.scheduler = scheduler
        self.ratio = device_ratio
        self._pending: dict[tuple, int] = {}
        self._placeholders: dict[tuple[int, int], QPixmap] = {}
        self._pixmaps: OrderedDict[tuple, QPixmap] = OrderedDict()
        scheduler.rendered.connect(self._on_rendered)

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: N802, B008
        return 0 if parent.isValid() else self.doc.page_count

    def _scale(self, pno: int) -> float:
        rect = self.doc.page_rect(pno)
        return min(THUMB_WIDTH / rect.width, THUMB_HEIGHT / rect.height) * self.ratio

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= self.doc.page_count:
            return None
        pno = index.row()
        if role == Qt.ItemDataRole.DisplayRole:
            return str(pno + 1)
        if role == Qt.ItemDataRole.ToolTipRole:
            rect = self.doc.page_rect(pno)
            return f"Page {pno + 1} - {rect.width / 72 * 25.4:.0f} × {rect.height / 72 * 25.4:.0f} mm"
        if role == Qt.ItemDataRole.DecorationRole:
            key, image = self.scheduler.request(
                pno, self._scale(pno), priority=RenderScheduler.PRIORITY_THUMBNAIL
            )
            if image is not None:
                return self._framed(key, image)
            self._pending[key] = pno
            return self._placeholder(pno)
        return None

    def _framed(self, key: tuple, image) -> QPixmap:
        """Thumbnail pixmap with a thin border (cached; conversion is not free)."""
        pix = self._pixmaps.get(key)
        if pix is None:
            pix = QPixmap.fromImage(image)
            painter = QPainter(pix)
            painter.setPen(QColor("#9a9a9a"))
            painter.drawRect(0, 0, pix.width() - 1, pix.height() - 1)
            painter.end()
            pix.setDevicePixelRatio(self.ratio)
            self._pixmaps[key] = pix
            while len(self._pixmaps) > MAX_CACHED_PIXMAPS:
                self._pixmaps.popitem(last=False)
        else:
            self._pixmaps.move_to_end(key)
        return pix

    def _placeholder(self, pno: int) -> QPixmap:
        rect = self.doc.page_rect(pno)
        s = min(THUMB_WIDTH / rect.width, THUMB_HEIGHT / rect.height)
        size = (max(1, int(rect.width * s)), max(1, int(rect.height * s)))
        if size not in self._placeholders:
            pix = QPixmap(*size)
            pix.fill(QColor("#ffffff"))
            painter = QPainter(pix)
            painter.setPen(QColor("#cccccc"))
            painter.drawRect(0, 0, size[0] - 1, size[1] - 1)
            painter.end()
            self._placeholders[size] = pix
        return self._placeholders[size]

    def _on_rendered(self, key: tuple) -> None:
        row = self._pending.pop(key, None)
        if row is not None and row < self.rowCount():
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])

    def refresh(self, pages: list[int] | None = None) -> None:
        """Re-query thumbnails for changed pages (or reset everything)."""
        if pages is None:
            self.beginResetModel()
            self._pending.clear()
            self._placeholders.clear()
            self._pixmaps.clear()
            self.endResetModel()
            return
        for pno in pages:
            if 0 <= pno < self.rowCount():
                idx = self.index(pno)
                self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])

    # -- drag and drop ----------------------------------------------------------
    def flags(self, index: _Index) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsDropEnabled
        if not index.isValid():
            return base
        return base | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled

    def supportedDropActions(self) -> Qt.DropAction:  # noqa: N802
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

    def mimeTypes(self) -> list[str]:  # noqa: N802
        return [MIME_PAGES, "text/uri-list"]

    def mimeData(self, indexes) -> QMimeData:  # noqa: N802
        rows = sorted({i.row() for i in indexes if i.isValid()})
        data = QMimeData()
        data.setData(MIME_PAGES, QByteArray(",".join(map(str, rows)).encode()))
        return data

    def canDropMimeData(self, data, action, row, column, parent) -> bool:  # noqa: N802
        return data.hasFormat(MIME_PAGES) or data.hasUrls()

    def dropMimeData(self, data, action, row, column, parent) -> bool:  # noqa: N802
        target = row if row >= 0 else (parent.row() if parent.isValid() else self.rowCount())
        if data.hasFormat(MIME_PAGES):
            raw = bytes(data.data(MIME_PAGES).data()).decode()
            pages = [int(p) for p in raw.split(",") if p]
            if pages:
                self.pagesDropped.emit(pages, target)
        elif data.hasUrls():
            paths = [u.toLocalFile() for u in data.urls() if u.isLocalFile()]
            if paths:
                self.filesDropped.emit(paths, target)
        return False  # the document model does the move; never let the view remove rows


class ThumbnailPanel(QListView):
    """Vertical strip of page thumbnails."""

    pageActivated = Signal(int)
    deleteRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setLayoutMode(QListView.LayoutMode.Batched)
        self.setBatchSize(50)
        self.setIconSize(QSize(THUMB_WIDTH, THUMB_HEIGHT))
        self.setGridSize(QSize(THUMB_WIDTH + 24, THUMB_HEIGHT + 30))
        self.setSpacing(4)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setMinimumWidth(THUMB_WIDTH + 40)
        self._syncing = False
        self.clicked.connect(lambda idx: self.pageActivated.emit(idx.row()))
        self.activated.connect(lambda idx: self.pageActivated.emit(idx.row()))

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Delete and self.selected_pages():
            self.deleteRequested.emit()
            return
        super().keyPressEvent(event)

    def selected_pages(self) -> list[int]:
        return sorted(i.row() for i in self.selectionModel().selectedIndexes()) if self.selectionModel() else []

    def sync_current(self, pno: int) -> None:
        """Follow the viewer's current page without stealing the selection."""
        model = self.model()
        if model is None or not 0 <= pno < model.rowCount():
            return
        idx = model.index(pno, 0)
        self._syncing = True
        if len(self.selected_pages()) <= 1:
            self.setCurrentIndex(idx)
        self.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)
        self._syncing = False
