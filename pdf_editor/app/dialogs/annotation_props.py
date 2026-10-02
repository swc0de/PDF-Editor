"""Edit an annotation's colours, line width, opacity and comment text."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QPlainTextEdit,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from ...core.operations.annotate import AnnotInfo
from ..qt_utils import qcolor, rgb_floats
from .settings import ColorButton

FILLABLE = {"Square", "Circle", "Polygon", "FreeText"}
NO_WIDTH = {"Highlight", "Underline", "StrikeOut", "Squiggly", "Text", "Stamp"}


class AnnotationPropertiesDialog(QDialog):
    def __init__(self, info: AnnotInfo, parent: QWidget | None = None, focus_text: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{info.kind} Properties")
        self.info = info
        form = QFormLayout()
        main_color = info.text_color if info.kind == "FreeText" else info.stroke
        self.color = None
        if info.kind != "Stamp":
            self.color = ColorButton(main_color or "#000000", self)
            form.addRow("Text colour:" if info.kind == "FreeText" else "Colour:", self.color)
        self.fill_check = QCheckBox("Fill", self)
        self.fill = ColorButton(info.fill or "#ffffff", self)
        if info.kind in FILLABLE:
            self.fill_check.setChecked(info.fill is not None)
            self.fill.setEnabled(info.fill is not None)
            self.fill_check.toggled.connect(self.fill.setEnabled)
            form.addRow(self.fill_check, self.fill)
        self.width = QDoubleSpinBox(self)
        self.width.setRange(0, 30)
        self.width.setSingleStep(0.5)
        self.width.setSuffix(" pt")
        self.width.setValue(info.width)
        if info.kind not in NO_WIDTH:
            form.addRow("Line width:", self.width)
        self.opacity = QSlider(Qt.Orientation.Horizontal, self)
        self.opacity.setRange(10, 100)
        self.opacity.setValue(int(round(info.opacity * 100)))
        form.addRow("Opacity:", self.opacity)
        self.text = QPlainTextEdit(info.contents, self)
        self.text.setMinimumHeight(90)
        form.addRow("Text:" if info.kind == "FreeText" else "Comment:", self.text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        if focus_text:
            self.text.setFocus()

    def changes(self) -> tuple[dict, str | None]:
        """``(style kwargs, new text or None)`` with only what changed."""
        info, style = self.info, {}
        main = info.text_color if info.kind == "FreeText" else info.stroke
        if self.color is not None and self.color.color != (main or "#000000"):
            style["stroke"] = rgb_floats(qcolor(self.color.color))
        if info.kind in FILLABLE:
            if not self.fill_check.isChecked() and info.fill is not None:
                style["fill"] = False
            elif self.fill_check.isChecked() and self.fill.color != info.fill:
                style["fill"] = rgb_floats(qcolor(self.fill.color))
        if info.kind not in NO_WIDTH and abs(self.width.value() - info.width) > 1e-6:
            style["width"] = self.width.value()
        if abs(self.opacity.value() / 100 - info.opacity) > 0.005:
            style["opacity"] = self.opacity.value() / 100
        text = self.text.toPlainText()
        return style, (text if text != info.contents else None)
