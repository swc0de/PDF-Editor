"""Merge several PDFs: choose files and their order."""

from __future__ import annotations

import os

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.utils import file_size, format_size

MERGE_FILTER = "PDF and image files (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp);;All files (*)"


class MergeDialog(QDialog):
    """Pick input files and arrange them; :meth:`paths` returns them in order."""

    def __init__(self, start_dir: str, initial: list[str] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Merge PDFs")
        self.resize(620, 420)
        self.start_dir = start_dir
        self.list = QListWidget(self)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        buttons = QVBoxLayout()
        for text, slot in (
            ("Add Files…", self.add_files),
            ("Remove", self.remove_selected),
            ("Move Up", lambda: self.move_selected(-1)),
            ("Move Down", lambda: self.move_selected(1)),
            ("Sort by Name", self.sort_by_name),
        ):
            button = QPushButton(text, self)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        body = QHBoxLayout()
        body.addWidget(self.list, 1)
        body.addLayout(buttons)
        self.summary = QLabel(self)
        self.box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.box.button(QDialogButtonBox.StandardButton.Ok).setText("Merge…")
        self.box.accepted.connect(self.accept)
        self.box.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Files are merged from top to bottom. Drag to reorder.", self))
        layout.addLayout(body)
        layout.addWidget(self.summary)
        layout.addWidget(self.box)
        self.list.model().rowsMoved.connect(lambda *_: self._update())
        for path in initial or []:
            self._add(path)
        self._update()

    def _add(self, path: str) -> None:
        pages = "?"
        try:
            with pymupdf.open(path) as doc:
                pages = "locked" if doc.needs_pass else str(doc.page_count)
        except Exception:
            pages = "unreadable"
        item = QListWidgetItem(f"{os.path.basename(path)}   ({pages} pages, {format_size(file_size(path))})")
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setToolTip(path)
        self.list.addItem(item)

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Files", self.start_dir, MERGE_FILTER)
        for path in paths:
            self._add(path)
        if paths:
            self.start_dir = os.path.dirname(paths[0])
        self._update()

    def remove_selected(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self._update()

    def move_selected(self, delta: int) -> None:
        rows = sorted(self.list.row(i) for i in self.list.selectedItems())
        if not rows:
            return
        if delta > 0:
            rows.reverse()
        for row in rows:
            target = row + delta
            if 0 <= target < self.list.count():
                item = self.list.takeItem(row)
                self.list.insertItem(target, item)
                item.setSelected(True)
        self._update()

    def sort_by_name(self) -> None:
        paths = sorted(self.paths(), key=lambda p: os.path.basename(p).lower())
        self.list.clear()
        for path in paths:
            self._add(path)
        self._update()

    def paths(self) -> list[str]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]

    def _update(self) -> None:
        count = self.list.count()
        self.summary.setText(f"{count} file(s) selected." + ("" if count >= 2 else " Add at least two files."))
        self.box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(count >= 2)
