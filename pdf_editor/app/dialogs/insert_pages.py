"""Insert pages from another PDF or from images."""

from __future__ import annotations

import os

import pymupdf
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ...core.errors import InvalidInput
from ...core.utils import parse_page_ranges

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp")
PAGE_SIZES = {"Same as image": None, "A4": (595.0, 842.0), "Letter": (612.0, 792.0)}


def is_image(path: str) -> bool:
    return path.lower().endswith(IMAGE_EXTENSIONS)


class InsertPagesDialog(QDialog):
    """Where to insert, which pages (for PDFs) and page size (for images)."""

    def __init__(self, paths: list[str], current_page: int, page_count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insert Pages")
        self.paths = paths
        self.current_page = current_page
        self.page_count = page_count
        self.images = all(is_image(p) for p in paths)
        form = QFormLayout()
        names = ", ".join(os.path.basename(p) for p in paths[:3]) + (" …" if len(paths) > 3 else "")
        form.addRow("From:", QLabel(names, self))
        self.before = QRadioButton(f"Before page {current_page + 1}", self)
        self.after = QRadioButton(f"After page {current_page + 1}", self)
        self.start = QRadioButton("At the beginning", self)
        self.end = QRadioButton("At the end", self)
        group = QButtonGroup(self)
        position = QVBoxLayout()
        for button in (self.after, self.before, self.start, self.end):
            group.addButton(button)
            position.addWidget(button)
        self.after.setChecked(True)
        form.addRow("Position:", position)
        self.source_pages = 0
        self.range = QLineEdit(self)
        if not self.images and len(paths) == 1:
            try:
                with pymupdf.open(paths[0]) as src:
                    self.source_pages = src.page_count
            except Exception:
                self.source_pages = 0
            self.range.setPlaceholderText(f"All pages (1-{self.source_pages})")
            form.addRow("Pages to insert:", self.range)
        self.size = QComboBox(self)
        self.margin = QDoubleSpinBox(self)
        if self.images:
            self.size.addItems(list(PAGE_SIZES))
            form.addRow("Page size:", self.size)
            self.margin.setRange(0, 144)
            self.margin.setSuffix(" pt")
            form.addRow("Margin:", self.margin)
        self.error = QLabel(self)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    def index(self) -> int:
        if self.before.isChecked():
            return self.current_page
        if self.after.isChecked():
            return self.current_page + 1
        return 0 if self.start.isChecked() else self.page_count

    def source_page_list(self) -> list[int] | None:
        text = self.range.text().strip()
        if not text or not self.source_pages:
            return None
        return [p for group in parse_page_ranges(text, self.source_pages) for p in group]

    def page_size(self) -> tuple[float, float] | None:
        return PAGE_SIZES.get(self.size.currentText())

    def accept(self) -> None:
        try:
            self.source_page_list()
        except InvalidInput as exc:
            self.error.setText(f"<span style='color:#c0392b'>{exc.message}</span>")
            return
        super().accept()
