"""Bookmarks panel: navigate the outline and edit it (add, rename, delete, nest)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.operations import outline as ops
from .errors import guarded
from .qt_utils import glyph_icon

PATH_ROLE = Qt.ItemDataRole.UserRole


class _Tree(QTreeWidget):
    """Tree that reports internal drag & drop moves instead of applying them."""

    moved = Signal(tuple, tuple, int)  # path, new parent path, index

    def dropEvent(self, event) -> None:  # noqa: N802
        source = self.currentItem()
        target = self.itemAt(event.position().toPoint())
        if source is None:
            event.ignore()
            return
        path = source.data(0, PATH_ROLE)
        pos = self.dropIndicatorPosition()
        if target is None:
            parent, index = (), self.topLevelItemCount()
        elif pos == QAbstractItemView.DropIndicatorPosition.OnItem:
            parent = target.data(0, PATH_ROLE)
            index = target.childCount()
        else:
            tpath = target.data(0, PATH_ROLE)
            parent = tpath[:-1]
            index = tpath[-1] + (1 if pos == QAbstractItemView.DropIndicatorPosition.BelowItem else 0)
        event.ignore()  # we rebuild the tree from the document instead
        self.moved.emit(path, parent, index)


class OutlinePanel(QWidget):
    """Shows the document outline; edits go through ``PdfDocument.set_bookmarks``."""

    pageRequested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tab = None
        self.tree = _Tree(self)
        self.tree.setHeaderHidden(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.itemClicked.connect(self._on_clicked)
        self.tree.itemActivated.connect(self._on_clicked)
        self.tree.moved.connect(self._on_moved)
        bar = QHBoxLayout()
        bar.setContentsMargins(2, 2, 2, 2)
        bar.setSpacing(1)
        self.buttons = {}
        for name, glyph, tip, slot in (
            ("add", "+", "Add bookmark for the current page", self.add_bookmark),
            ("rename", "✎", "Rename bookmark", self.rename_bookmark),
            ("delete", "✕", "Delete bookmark", self.delete_bookmark),
            ("indent", "→", "Nest under previous bookmark", self.indent),
            ("outdent", "←", "Move one level up", self.outdent),
            ("up", "↑", "Move up", lambda: self.move_by(-1)),
            ("down", "↓", "Move down", lambda: self.move_by(1)),
        ):
            button = QToolButton(self)
            button.setIcon(glyph_icon(glyph, bold=True))
            button.setToolTip(tip)
            button.setAutoRaise(True)
            button.clicked.connect(slot)
            bar.addWidget(button)
            self.buttons[name] = button
        bar.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(bar)
        layout.addWidget(self.tree)
        self._tree: list[ops.Bookmark] = []
        self._update_buttons()

    # -- data -------------------------------------------------------------------
    def set_tab(self, tab) -> None:
        self.tab = tab
        self.reload()

    def reload(self) -> None:
        self.tree.clear()
        self._tree = self.tab.doc.bookmarks() if self.tab is not None else []
        expanded = []

        def add(nodes: list[ops.Bookmark], parent, prefix: tuple) -> None:
            for i, node in enumerate(nodes):
                item = QTreeWidgetItem([node.title])
                item.setData(0, PATH_ROLE, prefix + (i,))
                item.setToolTip(0, f"{node.title} (page {node.page + 1})" if node.page >= 0 else node.title)
                (parent.addChild(item) if parent is not None else self.tree.addTopLevelItem(item))
                add(node.children, item, prefix + (i,))
                expanded.append(item)

        add(self._tree, None, ())
        for item in expanded:
            item.setExpanded(True)
        self._update_buttons()

    def _update_buttons(self) -> None:
        has_doc = self.tab is not None
        for name, button in self.buttons.items():
            button.setEnabled(has_doc and (name == "add" or self.tree.currentItem() is not None))

    def _current_path(self) -> tuple | None:
        item = self.tree.currentItem()
        return item.data(0, PATH_ROLE) if item is not None else None

    def _on_clicked(self, item: QTreeWidgetItem) -> None:
        self._update_buttons()
        path = item.data(0, PATH_ROLE)
        node = ops.get_node(self._tree, path)
        if node.page >= 0:
            self.pageRequested.emit(node.page)

    # -- editing ------------------------------------------------------------------
    def _commit(self, tree: list[ops.Bookmark], label: str, select: tuple | None = None) -> None:
        if self.tab is None:
            return
        with guarded(self):
            self.tab.doc.set_bookmarks(tree, label)
            self.reload()
            if select is not None:
                self._select(select)

    def _select(self, path: tuple) -> None:
        item = None
        for i, index in enumerate(path):
            item = self.tree.topLevelItem(index) if i == 0 else (item.child(index) if item else None)
        if item is not None:
            self.tree.setCurrentItem(item)
        self._update_buttons()

    def add_bookmark(self) -> None:
        if self.tab is None:
            return
        page = self.tab.viewer.current_page
        title, ok = QInputDialog.getText(self, "Add Bookmark", "Title:", text=f"Page {page + 1}")
        if not ok:
            return
        tree = ops.clone_tree(self._tree)
        current = self._current_path()
        with guarded(self):
            if current is None:
                path = ops.add_bookmark(tree, title, page)
            else:
                path = ops.add_bookmark(tree, title, page, parent=current[:-1], index=current[-1] + 1)
            self._commit(tree, "Add bookmark", path)

    def rename_bookmark(self) -> None:
        path = self._current_path()
        if path is None:
            return
        node = ops.get_node(self._tree, path)
        title, ok = QInputDialog.getText(self, "Rename Bookmark", "Title:", text=node.title)
        if ok:
            tree = ops.clone_tree(self._tree)
            with guarded(self):
                ops.rename_bookmark(tree, path, title)
                self._commit(tree, "Rename bookmark", path)

    def delete_bookmark(self) -> None:
        path = self._current_path()
        if path is None:
            return
        tree = ops.clone_tree(self._tree)
        ops.delete_bookmark(tree, path)
        self._commit(tree, "Delete bookmark")

    def indent(self) -> None:
        self._edit_path(ops.indent_bookmark, "Nest bookmark")

    def outdent(self) -> None:
        self._edit_path(ops.outdent_bookmark, "Un-nest bookmark")

    def _edit_path(self, func, label: str) -> None:
        path = self._current_path()
        if path is None:
            return
        tree = ops.clone_tree(self._tree)
        with guarded(self):
            new_path = func(tree, path)
            self._commit(tree, label, new_path)

    def move_by(self, delta: int) -> None:
        path = self._current_path()
        if path is None:
            return
        target = path[-1] + delta + (1 if delta > 0 else 0)
        if target < 0:
            return
        self._on_moved(path, path[:-1], target)

    def _on_moved(self, path: tuple, parent: tuple, index: int) -> None:
        tree = ops.clone_tree(self._tree)
        with guarded(self):
            new_path = ops.move_bookmark(tree, path, parent, index)
            self._commit(tree, "Move bookmark", new_path)
