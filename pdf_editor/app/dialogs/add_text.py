"""Dialog for adding new text: font, size, colour and alignment."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.operations.textedit import ALIGNMENTS, FAMILIES
from ..qt_utils import qcolor, rgb_floats
from .settings import ColorButton

FONT_FILTER = "Fonts (*.ttf *.otf *.ttc);;All files (*)"


class AddTextDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, color: str = "#000000", size: float = 12,
                 text: str = "", title: str = "Add Text") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self.text = QPlainTextEdit(text, self)
        self.text.setPlaceholderText("Type the text to add…")
        self.family = QComboBox(self)
        self.family.addItems(list(FAMILIES) + ["Custom font file…"])
        self.family.currentTextChanged.connect(self._family_changed)
        self.font_file: str | None = None
        self.bold = QCheckBox("Bold", self)
        self.italic = QCheckBox("Italic", self)
        style = QHBoxLayout()
        style.addWidget(self.family, 1)
        style.addWidget(self.bold)
        style.addWidget(self.italic)
        self.size = QDoubleSpinBox(self)
        self.size.setRange(4, 200)
        self.size.setValue(size)
        self.size.setSuffix(" pt")
        self.color = ColorButton(color, self)
        self.align = QComboBox(self)
        for name in ALIGNMENTS:
            self.align.addItem(name.capitalize(), name)
        self.font_label = QLabel("", self)
        form = QFormLayout()
        form.addRow("Text:", self.text)
        form.addRow("Font:", style)
        form.addRow("", self.font_label)
        form.addRow("Size:", self.size)
        form.addRow("Colour:", self.color)
        form.addRow("Alignment:", self.align)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.text.setFocus()

    def _family_changed(self, name: str) -> None:
        custom = name.startswith("Custom")
        if custom:
            path, _ = QFileDialog.getOpenFileName(self, "Choose Font File", os.path.expanduser("~"), FONT_FILTER)
            if not path:
                self.family.setCurrentIndex(0)
                return
            self.font_file = path
            self.font_label.setText(os.path.basename(path))
        else:
            self.font_file = None
            self.font_label.setText("")
        self.bold.setEnabled(not custom)
        self.italic.setEnabled(not custom)

    def values(self) -> tuple[str, dict]:
        """``(text, style kwargs for PdfDocument.add_text)``."""
        style = {
            "fontsize": self.size.value(),
            "color": rgb_floats(qcolor(self.color.color)),
            "align": self.align.currentData(),
        }
        if self.font_file:
            style["fontfile"] = self.font_file
        else:
            style.update(family=self.family.currentText(), bold=self.bold.isChecked(), italic=self.italic.isChecked())
        return self.text.toPlainText(), style
