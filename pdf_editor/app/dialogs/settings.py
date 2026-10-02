"""Preferences: theme, default zoom, autosave interval, annotation colours."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...settings import Settings
from ..qt_utils import color_swatch_icon


class ColorButton(QPushButton):
    """A button that shows and edits a colour."""

    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.color = color
        self._refresh()
        self.clicked.connect(self._pick)

    def _refresh(self) -> None:
        self.setText(self.color)
        self.setIcon(color_swatch_icon(self.color))

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(QColor(self.color), self, "Choose colour")
        if chosen.isValid():
            self.color = chosen.name()
            self._refresh()


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = settings
        form = QFormLayout()

        self.theme = QComboBox(self)
        for label, value in (("Follow system", "system"), ("Light", "light"), ("Dark", "dark")):
            self.theme.addItem(label, value)
        self.theme.setCurrentIndex(max(0, self.theme.findData(settings.theme)))
        form.addRow("Theme:", self.theme)

        self.zoom = QComboBox(self)
        for label, value in (
            ("Fit width", "fit-width"),
            ("Fit page", "fit-page"),
            ("Actual size (100%)", "actual"),
            ("75%", "75"),
            ("125%", "125"),
            ("150%", "150"),
        ):
            self.zoom.addItem(label, value)
        index = self.zoom.findData(settings.default_zoom)
        if index < 0:
            self.zoom.addItem(f"{settings.default_zoom}%", settings.default_zoom)
            index = self.zoom.count() - 1
        self.zoom.setCurrentIndex(index)
        form.addRow("Default zoom:", self.zoom)

        self.autosave = QSpinBox(self)
        self.autosave.setRange(0, 120)
        self.autosave.setSuffix(" min")
        self.autosave.setSpecialValueText("Off")
        self.autosave.setValue(settings.autosave_minutes)
        self.autosave.setToolTip("How often recovery copies of modified documents are written (0 = off)")
        form.addRow("Autosave recovery every:", self.autosave)

        self.annot_color = ColorButton(settings.annotation_color, self)
        form.addRow("Default annotation colour:", self.annot_color)
        self.highlight_color = ColorButton(settings.highlight_color, self)
        form.addRow("Default highlight colour:", self.highlight_color)

        self.author = QLineEdit(settings.author, self)
        form.addRow("Author name for annotations:", self.author)

        self.undo_memory = QSpinBox(self)
        self.undo_memory.setRange(16, 4096)
        self.undo_memory.setSuffix(" MB")
        self.undo_memory.setValue(settings.undo_memory_mb)
        self.undo_memory.setToolTip("Memory limit for the undo history of each document (applies to newly opened files)")
        form.addRow("Undo memory per document:", self.undo_memory)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def accept(self) -> None:
        s = self.settings
        s.theme = self.theme.currentData()
        s.default_zoom = self.zoom.currentData()
        s.autosave_minutes = self.autosave.value()
        s.annotation_color = self.annot_color.color
        s.highlight_color = self.highlight_color.color
        s.author = self.author.text().strip()
        s.undo_memory_mb = self.undo_memory.value()
        s.sync()
        super().accept()
