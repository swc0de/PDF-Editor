"""Panel listing every annotation in the document; click one to jump to it."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMenu, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ..core.events import Change
from ..core.operations.annotate import AnnotInfo
from .qt_utils import color_swatch_icon

ROLE = Qt.ItemDataRole.UserRole


class AnnotationsPanel(QWidget):
    """Grouped by page; updates incrementally when annotations change."""

    annotationActivated = Signal(int, int)  # page, xref
    deleteRequested = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tab = None
        self._by_page: dict[int, list[AnnotInfo]] = {}
        self._dirty_pages: set[int] | None = None
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText("Filter annotations…")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(lambda _t: self._rebuild())
        self.count = QLabel(self)
        top = QHBoxLayout()
        top.addWidget(self.filter, 1)
        top.addWidget(self.count)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemClicked.connect(self._activate)
        self.tree.itemActivated.connect(self._activate)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addLayout(top)
        layout.addWidget(self.tree)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._refresh)

    def set_tab(self, tab) -> None:
        self.tab = tab
        self._by_page = {}
        self._dirty_pages = None
        self._refresh()

    def on_document_event(self, event) -> None:
        """Re-scan only the pages that changed (debounced)."""
        if event.kind == Change.ANNOTATIONS and event.pages and self._dirty_pages is not None:
            self._dirty_pages.update(event.pages)
        elif event.kind in (Change.ANNOTATIONS, Change.STRUCTURE, Change.RELOAD, Change.FORMS, Change.CONTENT):
            self._dirty_pages = None
        else:
            return
        self._timer.start()

    def _refresh(self) -> None:
        if self.tab is None:
            self._by_page = {}
        elif self._dirty_pages is None:
            infos = self.tab.doc.annotations()
            self._by_page = {}
            for info in infos:
                self._by_page.setdefault(info.page, []).append(info)
        else:
            for pno in self._dirty_pages:
                if pno < self.tab.doc.page_count:
                    infos = self.tab.doc.annotations([pno])
                    if infos:
                        self._by_page[pno] = infos
                    else:
                        self._by_page.pop(pno, None)
        self._dirty_pages = set()
        self._rebuild()

    def _rebuild(self) -> None:
        self.tree.clear()
        needle = self.filter.text().strip().lower()
        total = 0
        for pno in sorted(self._by_page):
            items = [i for i in self._by_page[pno] if not needle or needle in i.label.lower() or needle in i.author.lower()]
            if not items:
                continue
            group = QTreeWidgetItem([f"Page {pno + 1}  ({len(items)})"])
            group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tree.addTopLevelItem(group)
            for info in items:
                text = info.label + (f"  — {info.author}" if info.author else "")
                item = QTreeWidgetItem([text])
                item.setData(0, ROLE, (info.page, info.xref))
                item.setToolTip(0, text)
                color = info.stroke or info.text_color or info.fill
                if color:
                    item.setIcon(0, color_swatch_icon(color, 16))
                group.addChild(item)
                total += 1
            group.setExpanded(True)
        self.count.setText(str(total))

    def select(self, pno: int | None, xref: int | None) -> None:
        """Highlight the row of the annotation selected in the viewer."""
        self.tree.blockSignals(True)
        self.tree.clearSelection()
        if pno is not None:
            for i in range(self.tree.topLevelItemCount()):
                group = self.tree.topLevelItem(i)
                for j in range(group.childCount()):
                    child = group.child(j)
                    if child.data(0, ROLE) == (pno, xref):
                        child.setSelected(True)
                        self.tree.scrollToItem(child)
        self.tree.blockSignals(False)

    def _activate(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, ROLE)
        if data:
            self.annotationActivated.emit(*data)

    def _menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        data = item.data(0, ROLE) if item else None
        if not data:
            return
        menu = QMenu(self)
        menu.addAction("Go to Annotation", lambda: self.annotationActivated.emit(*data))
        menu.addAction("Delete", lambda: self.deleteRequested.emit(*data))
        menu.exec(self.tree.viewport().mapToGlobal(pos))
