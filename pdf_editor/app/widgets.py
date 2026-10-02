"""Small reusable widgets: page box, zoom box, welcome page, status labels."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.utils import file_size, format_size


class PageNumberBox(QWidget):
    """``[ 3 ] of 12`` - type a number and press Enter to jump."""

    pageRequested = Signal(int)  # 0-based

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)
        self.edit = QLineEdit(self)
        self.edit.setFixedWidth(52)
        self.edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.edit.setToolTip("Current page - type a page number and press Enter (Ctrl+G)")
        self.validator = QIntValidator(1, 1, self)
        self.edit.setValidator(self.validator)
        self.edit.returnPressed.connect(self._jump)
        self.label = QLabel("of 0", self)
        layout.addWidget(self.edit)
        layout.addWidget(self.label)
        self._count = 0

    def set_state(self, current: int, count: int) -> None:
        self._count = count
        self.validator.setRange(1, max(1, count))
        if not self.edit.hasFocus():
            self.edit.setText(str(current + 1) if count else "")
        self.label.setText(f"of {count}")
        self.setEnabled(count > 0)

    def _jump(self) -> None:
        text = self.edit.text().strip()
        if text.isdigit() and 1 <= int(text) <= self._count:
            self.pageRequested.emit(int(text) - 1)
        self.edit.clearFocus()

    def focus(self) -> None:
        self.edit.setFocus()
        self.edit.selectAll()


class ZoomBox(QComboBox):
    """Editable zoom selector with fit modes and common percentages."""

    zoomRequested = Signal(object)  # float zoom, or "fit-width" / "fit-page"

    PRESETS = [("Fit Width", "fit-width"), ("Fit Page", "fit-page")] + [
        (f"{p}%", p / 100) for p in (25, 50, 75, 100, 125, 150, 200, 300, 400, 800)
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMinimumContentsLength(8)
        self.setToolTip("Zoom (Ctrl + mouse wheel)")
        for text, value in self.PRESETS:
            self.addItem(text, value)
        self.activated.connect(self._on_activated)
        self.lineEdit().returnPressed.connect(self._on_edited)

    def set_zoom(self, zoom: float, fit_mode: str | None) -> None:
        self.blockSignals(True)
        self.setEditText(f"{zoom * 100:.0f}%")
        self.blockSignals(False)

    def _on_activated(self, index: int) -> None:
        self.zoomRequested.emit(self.itemData(index))

    def _on_edited(self) -> None:
        text = self.currentText().replace("%", "").strip()
        try:
            self.zoomRequested.emit(max(10.0, min(800.0, float(text))) / 100)
        except ValueError:
            pass


class WelcomePage(QWidget):
    """Shown when no document is open: open button, drop hint, recent files."""

    openRequested = Signal()
    recentRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 50, 60, 50)
        title = QLabel("<h1>PDF Editor</h1>", self)
        hint = QLabel("Open a PDF with <b>Ctrl+O</b> or drag and drop files onto this window.", self)
        button = QPushButton("Open PDF…", self)
        button.setFixedWidth(160)
        button.clicked.connect(self.openRequested)
        self.recent_label = QLabel("<b>Recent files</b>", self)
        self.recent = QListWidget(self)
        self.recent.itemActivated.connect(lambda item: self.recentRequested.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.recent.itemClicked.connect(lambda item: self.recentRequested.emit(item.data(Qt.ItemDataRole.UserRole)))
        for w in (title, hint, button):
            layout.addWidget(w)
        layout.addSpacing(20)
        layout.addWidget(self.recent_label)
        layout.addWidget(self.recent, 1)

    def set_recent(self, paths: list[str]) -> None:
        self.recent.clear()
        for path in paths:
            item = QListWidgetItem(f"{os.path.basename(path)}    —    {os.path.dirname(path)}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            if not os.path.exists(path):
                item.setForeground(Qt.GlobalColor.gray)
                item.setToolTip("File not found")
            self.recent.addItem(item)
        self.recent_label.setVisible(bool(paths))
        self.recent.setVisible(bool(paths))


class StatusLabels:
    """Page, zoom and file size indicators for the status bar."""

    def __init__(self, status_bar) -> None:
        self.page = QLabel()
        self.zoom = QLabel()
        self.size = QLabel()
        for label in (self.page, self.zoom, self.size):
            label.setContentsMargins(8, 0, 8, 0)
            status_bar.addPermanentWidget(label)

    def update(self, tab) -> None:
        if tab is None:
            for label in (self.page, self.zoom, self.size):
                label.setText("")
            return
        viewer = tab.viewer
        self.page.setText(f"Page {viewer.current_page + 1} of {viewer.page_count}")
        self.zoom.setText(f"{viewer.zoom * 100:.0f}%")
        size = file_size(tab.doc.path)
        self.size.setText(format_size(size) if size else "Not saved")
