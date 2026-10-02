"""Watermark dialog: text or image, opacity, rotation and pages."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.errors import InvalidInput
from ...core.utils import parse_page_ranges
from ..qt_utils import qcolor, rgb_floats
from .settings import ColorButton


class PageScope(QWidget):
    """All pages / current page / page ranges selector shared by several dialogs."""

    def __init__(self, page_count: int, current: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_count, self.current = page_count, current
        self.all = QRadioButton("All pages", self)
        self.this = QRadioButton(f"Current page ({current + 1})", self)
        self.some = QRadioButton("Pages:", self)
        self.ranges = QLineEdit(self)
        self.ranges.setPlaceholderText("e.g. 1-3, 5")
        self.ranges.textChanged.connect(lambda: self.some.setChecked(True))
        group = QButtonGroup(self)
        for b in (self.all, self.this, self.some):
            group.addButton(b)
        self.all.setChecked(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for w in (self.all, self.this, self.some, self.ranges):
            layout.addWidget(w)

    def pages(self) -> list[int]:
        if self.all.isChecked():
            return list(range(self.page_count))
        if self.this.isChecked():
            return [self.current]
        return sorted({p for group in parse_page_ranges(self.ranges.text(), self.page_count) for p in group})


class WatermarkDialog(QDialog):
    def __init__(self, page_count: int, current: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Watermark")
        self.setMinimumWidth(500)
        self.use_text = QRadioButton("Text:", self)
        self.use_image = QRadioButton("Image:", self)
        kind = QButtonGroup(self)
        kind.addButton(self.use_text)
        kind.addButton(self.use_image)
        self.use_text.setChecked(True)
        self.text = QLineEdit("CONFIDENTIAL", self)
        self.text.textChanged.connect(lambda: self.use_text.setChecked(True))
        self.image_path = QLineEdit(self)
        browse = QPushButton("Browse…", self)
        browse.clicked.connect(self._browse)
        image_row = QHBoxLayout()
        image_row.addWidget(self.image_path, 1)
        image_row.addWidget(browse)
        self.font_size = QSpinBox(self)
        self.font_size.setRange(8, 300)
        self.font_size.setValue(60)
        self.font_size.setSuffix(" pt")
        self.bold = QCheckBox("Bold", self)
        self.bold.setChecked(True)
        self.color = ColorButton("#9e9e9e", self)
        self.scale = QSpinBox(self)
        self.scale.setRange(5, 100)
        self.scale.setValue(50)
        self.scale.setSuffix(" % of page width")
        self.opacity = QSlider(Qt.Orientation.Horizontal, self)
        self.opacity.setRange(5, 100)
        self.opacity.setValue(30)
        self.opacity_label = QLabel("30%", self)
        self.opacity.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v}%"))
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity, 1)
        opacity_row.addWidget(self.opacity_label)
        self.rotation = QDoubleSpinBox(self)
        self.rotation.setRange(-180, 180)
        self.rotation.setValue(45)
        self.rotation.setSuffix("°")
        self.behind = QCheckBox("Place behind page content", self)
        self.scope = PageScope(page_count, current, self)
        self.error = QLabel(self)
        self.error.setStyleSheet("color: #c0392b")
        text_style = QHBoxLayout()
        text_style.addWidget(self.font_size)
        text_style.addWidget(self.bold)
        text_style.addWidget(self.color)
        form = QFormLayout()
        form.addRow(self.use_text, self.text)
        form.addRow("Text style:", text_style)
        form.addRow(self.use_image, image_row)
        form.addRow("Image size:", self.scale)
        form.addRow("Opacity:", opacity_row)
        form.addRow("Rotation:", self.rotation)
        form.addRow("", self.behind)
        form.addRow("Apply to:", self.scope)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Watermark Image", os.path.expanduser("~"),
                                              "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff)")
        if path:
            self.image_path.setText(path)
            self.use_image.setChecked(True)

    def apply_to(self, doc) -> int:
        """Add the configured watermark to ``doc``; returns the number of pages."""
        pages = self.scope.pages()
        common = {"opacity": self.opacity.value() / 100, "rotation": self.rotation.value(),
                  "overlay": not self.behind.isChecked()}
        if self.use_text.isChecked():
            return doc.add_text_watermark(pages, self.text.text(), fontsize=self.font_size.value(),
                                          color=rgb_floats(qcolor(self.color.color)), bold=self.bold.isChecked(),
                                          **common)
        path = self.image_path.text().strip()
        if not os.path.isfile(path):
            raise InvalidInput("Choose an image file for the watermark.")
        with open(path, "rb") as fh:
            return doc.add_image_watermark(pages, fh.read(), scale=self.scale.value() / 100, **common)

    def accept(self) -> None:
        try:
            self.scope.pages()
        except InvalidInput as exc:
            self.error.setText(exc.message)
            return
        super().accept()
