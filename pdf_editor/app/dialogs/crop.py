"""Crop pages by margins, or confirm a rectangle drawn with the crop tool."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

SCOPES = ("current", "selected", "all")


class CropDialog(QDialog):
    """Margins in millimetres, or (with ``rect_mode``) just the scope for a drawn area."""

    def __init__(self, selected: int, parent: QWidget | None = None, rect_mode: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Crop Pages")
        form = QFormLayout()
        self.margins: dict[str, QDoubleSpinBox] = {}
        if not rect_mode:
            for side in ("Left", "Top", "Right", "Bottom"):
                spin = QDoubleSpinBox(self)
                spin.setRange(0, 500)
                spin.setSuffix(" mm")
                spin.setDecimals(1)
                form.addRow(f"{side}:", spin)
                self.margins[side.lower()] = spin
        self.scope = QComboBox(self)
        self.scope.addItem("Current page", "current")
        self.scope.addItem(f"Selected pages ({selected})", "selected")
        self.scope.addItem("All pages", "all")
        form.addRow("Apply to:", self.scope)
        self.reset = QCheckBox("Remove existing cropping instead", self)
        if not rect_mode:
            form.addRow(self.reset)
            self.reset.toggled.connect(lambda on: [s.setEnabled(not on) for s in self.margins.values()])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        tip = "Crop to the area you drew." if rect_mode else "Tip: use the Crop tool to draw the area on a page."
        layout.addWidget(QLabel(tip, self))
        layout.addLayout(form)
        layout.addWidget(buttons)

    def scope_name(self) -> str:
        return self.scope.currentData()

    def margins_pt(self) -> tuple[float, float, float, float]:
        mm = 72 / 25.4
        return tuple(self.margins[s].value() * mm for s in ("left", "top", "right", "bottom"))  # type: ignore[return-value]
