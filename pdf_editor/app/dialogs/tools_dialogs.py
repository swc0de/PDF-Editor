"""Compression, OCR and image-export dialogs."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.errors import InvalidInput
from ...core.operations.ocr import OcrStatus
from ...core.operations.optimize import PRESETS
from ...core.utils import format_size
from .watermark import PageScope


def _buttons(dialog: QDialog, ok_text: str) -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
    box.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


class CompressDialog(QDialog):
    def __init__(self, current_size: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Reduce File Size")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Current size: <b>{format_size(current_size)}</b>", self))
        self.group = QButtonGroup(self)
        for key, preset in PRESETS.items():
            button = QRadioButton(f"{preset.name} — {preset.description}", self)
            button.setProperty("preset", key)
            self.group.addButton(button)
            layout.addWidget(button)
            if key == "medium":
                button.setChecked(True)
        layout.addWidget(QLabel("A compressed copy is saved as a new file; the original stays untouched.", self))
        layout.addWidget(_buttons(self, "Compress…"))

    def preset(self) -> str:
        return self.group.checkedButton().property("preset")


class OcrDialog(QDialog):
    def __init__(self, status: OcrStatus, page_count: int, current: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Recognize Text (OCR)")
        layout = QVBoxLayout(self)
        message = QLabel(status.message, self)
        message.setWordWrap(True)
        message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if not status.available:
            message.setStyleSheet("QLabel { background: #fff3cd; color: #5c4400; padding: 8px; }")
        layout.addWidget(message)
        form = QFormLayout()
        self.language = QComboBox(self)
        self.language.setEditable(True)
        self.language.addItems(list(status.languages))
        if "eng" in status.languages:
            self.language.setCurrentText("eng")
        self.dpi = QSpinBox(self)
        self.dpi.setRange(72, 600)
        self.dpi.setValue(300)
        self.dpi.setSuffix(" dpi")
        self.skip = QCheckBox("Skip pages that already contain text", self)
        self.skip.setChecked(True)
        self.scope = PageScope(page_count, current, self)
        form.addRow("Language:", self.language)
        form.addRow("Resolution:", self.dpi)
        form.addRow("", self.skip)
        form.addRow("Pages:", self.scope)
        layout.addLayout(form)
        layout.addWidget(QLabel("Tip: combine languages with '+', e.g. eng+deu.", self))
        self.box = _buttons(self, "Recognize")
        layout.addWidget(self.box)
        for widget in (self.language, self.dpi, self.skip, self.scope):
            widget.setEnabled(status.available)
        self.box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(status.available)


class ExportImagesDialog(QDialog):
    def __init__(self, page_count: int, current: int, folder: str, base: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Pages as Images")
        self.format = QComboBox(self)
        self.format.addItem("PNG (lossless)", "png")
        self.format.addItem("JPG (smaller)", "jpg")
        self.dpi = QSpinBox(self)
        self.dpi.setRange(18, 1200)
        self.dpi.setValue(150)
        self.dpi.setSuffix(" dpi")
        self.quality = QSpinBox(self)
        self.quality.setRange(10, 100)
        self.quality.setValue(90)
        self.format.currentIndexChanged.connect(lambda _i: self.quality.setEnabled(self.format.currentData() == "jpg"))
        self.quality.setEnabled(False)
        self.folder = QLineEdit(folder, self)
        browse = QPushButton("Browse…", self)
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        self.base = QLineEdit(base, self)
        self.scope = PageScope(page_count, current, self)
        self.error = QLabel(self)
        self.error.setStyleSheet("color: #c0392b")
        form = QFormLayout(self)
        form.addRow("Format:", self.format)
        form.addRow("Resolution:", self.dpi)
        form.addRow("JPG quality:", self.quality)
        form.addRow("Pages:", self.scope)
        form.addRow("Folder:", row)
        form.addRow("File name prefix:", self.base)
        form.addRow(self.error)
        form.addRow(_buttons(self, "Export"))

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Export To", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def accept(self) -> None:
        try:
            self.scope.pages()
        except InvalidInput as exc:
            self.error.setText(exc.message)
            return
        if not os.path.isdir(self.folder.text()):
            self.error.setText("Choose an existing folder.")
            return
        super().accept()
