"""Shared options for drawing tools (colour, width, opacity...) and their toolbar."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QLabel,
    QSlider,
    QSpinBox,
    QToolBar,
    QToolButton,
    QWidget,
)

from ..core.operations.annotate import NOTE_ICONS, STAMPS
from ..settings import Settings
from .qt_utils import color_swatch_icon, qcolor, rgb_floats

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff);;All files (*)"


class ToolOptions(QObject):
    """Current settings used by annotation tools (shared by all tabs)."""

    changed = Signal()

    def __init__(self, settings: Settings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.stroke = settings.annotation_color
        self.highlight = settings.highlight_color
        self.fill: str | None = None
        self.width = 2.0
        self.opacity = 1.0
        self.font_size = 12.0
        self.stamp = "Approved"
        self.stamp_image: str | None = None
        self.note_icon = "Note"
        self.author = settings.author
        self.signature: bytes | None = None

    def stroke_rgb(self) -> tuple[float, float, float]:
        return rgb_floats(qcolor(self.stroke))

    def highlight_rgb(self) -> tuple[float, float, float]:
        return rgb_floats(qcolor(self.highlight))

    def fill_rgb(self) -> tuple[float, float, float] | None:
        return rgb_floats(qcolor(self.fill)) if self.fill else None

    def set(self, **values) -> None:
        for key, value in values.items():
            setattr(self, key, value)
        self.changed.emit()


class ToolOptionsBar(QToolBar):
    """Shows the options relevant to the active tool."""

    signatureNewRequested = Signal()
    signatureDeleteRequested = Signal(int)

    def __init__(self, options: ToolOptions, parent: QWidget | None = None, settings: Settings | None = None) -> None:
        super().__init__("Tool Options", parent)
        self.setObjectName("toolOptionsToolbar")
        self.options = options
        self.settings = settings
        self._actions: dict[str, list] = {}

        self.color_button = self._color_button("Colour", lambda: options.stroke, lambda c: options.set(stroke=c))
        self.highlight_button = self._color_button(
            "Highlight colour", lambda: options.highlight, lambda c: options.set(highlight=c)
        )
        self.fill_check = QCheckBox("Fill", self)
        self.fill_check.toggled.connect(self._fill_toggled)
        self.fill_button = self._color_button("Fill colour", lambda: options.fill or "#ffffff",
                                              lambda c: options.set(fill=c))
        self.width = QDoubleSpinBox(self)
        self.width.setRange(0.25, 30)
        self.width.setSingleStep(0.5)
        self.width.setSuffix(" pt")
        self.width.setValue(options.width)
        self.width.valueChanged.connect(lambda v: options.set(width=v))
        self.opacity = QSlider(Qt.Orientation.Horizontal, self)
        self.opacity.setRange(10, 100)
        self.opacity.setFixedWidth(90)
        self.opacity.setValue(int(options.opacity * 100))
        self.opacity.setToolTip("Opacity")
        self.opacity.valueChanged.connect(lambda v: options.set(opacity=v / 100))
        self.font_size = QSpinBox(self)
        self.font_size.setRange(4, 144)
        self.font_size.setSuffix(" pt")
        self.font_size.setValue(int(options.font_size))
        self.font_size.valueChanged.connect(lambda v: options.set(font_size=float(v)))
        self.stamp = QComboBox(self)
        self.stamp.addItems(list(STAMPS) + ["Custom image…"])
        self.stamp.currentTextChanged.connect(self._stamp_changed)
        self.icon = QComboBox(self)
        self.icon.addItems(list(NOTE_ICONS))
        self.icon.currentTextChanged.connect(lambda t: options.set(note_icon=t))

        self._add("stroke", [QLabel(" Colour ", self), self.color_button])
        self._add("highlight", [QLabel(" Colour ", self), self.highlight_button])
        self._add("fill", [self.fill_check, self.fill_button])
        self._add("width", [QLabel(" Width ", self), self.width])
        self._add("opacity", [QLabel(" Opacity ", self), self.opacity])
        self._add("font", [QLabel(" Size ", self), self.font_size])
        self._add("stamp", [QLabel(" Stamp ", self), self.stamp])
        self._add("icon", [QLabel(" Icon ", self), self.icon])
        self.signature = QComboBox(self)
        self.signature.setMinimumWidth(150)
        self.signature.currentIndexChanged.connect(self._signature_changed)
        new_sig = QToolButton(self)
        new_sig.setText("New…")
        new_sig.clicked.connect(self.signatureNewRequested)
        del_sig = QToolButton(self)
        del_sig.setText("Delete")
        del_sig.clicked.connect(lambda: self.signatureDeleteRequested.emit(self.signature.currentIndex()))
        self._add("signature", [QLabel(" Signature ", self), self.signature, new_sig, del_sig])
        self.hint = QLabel("", self)
        self.hint.setContentsMargins(10, 0, 0, 0)
        self.addWidget(self.hint)
        self.show_for(set(), "")

    def _color_button(self, tip: str, getter, setter) -> QToolButton:
        button = QToolButton(self)
        button.setToolTip(tip)
        button.setIcon(color_swatch_icon(getter()))

        def pick() -> None:
            color = QColorDialog.getColor(QColor(getter()), self, tip)
            if color.isValid():
                setter(color.name())
                button.setIcon(color_swatch_icon(color.name()))

        button.clicked.connect(pick)
        return button

    def _add(self, name: str, widgets: list[QWidget]) -> None:
        self._actions[name] = [self.addWidget(w) for w in widgets]

    def _fill_toggled(self, checked: bool) -> None:
        self.options.set(fill=(self.options.fill or "#ffffff") if checked else None)
        self.fill_button.setEnabled(checked)

    def _stamp_changed(self, text: str) -> None:
        if text == "Custom image…":
            path, _ = QFileDialog.getOpenFileName(self, "Choose Stamp Image", os.path.expanduser("~"), IMAGE_FILTER)
            if path:
                self.options.set(stamp_image=path, stamp="")
                self.stamp.setToolTip(path)
            else:
                self.stamp.setCurrentIndex(0)
        else:
            self.options.set(stamp=text, stamp_image=None)

    def refresh_signatures(self, select: int | None = None) -> None:
        """Reload the saved signatures into the picker."""
        signatures = self.settings.signatures() if self.settings is not None else []
        self.signature.blockSignals(True)
        self.signature.clear()
        for sig in signatures:
            self.signature.addItem(sig.name)
        self.signature.blockSignals(False)
        if signatures:
            index = len(signatures) - 1 if select is None else max(0, min(select, len(signatures) - 1))
            self.signature.setCurrentIndex(index)
            self._signature_changed(index)
        elif self.settings is not None:
            self.options.set(signature=None)

    def _signature_changed(self, index: int) -> None:
        signatures = self.settings.signatures() if self.settings is not None else []
        if 0 <= index < len(signatures):
            self.options.set(signature=signatures[index].png)

    def show_for(self, names: set[str], hint: str) -> None:
        """Show only the option groups in ``names``."""
        for name, actions in self._actions.items():
            for action in actions:
                action.setVisible(name in names)
        self.fill_button.setEnabled(self.fill_check.isChecked())
        self.hint.setText(hint)
