"""Headers, footers and page numbers."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.errors import InvalidInput
from ...core.operations.layout import POSITIONS, HeaderFooter
from ..qt_utils import qcolor, rgb_floats
from .settings import ColorButton
from .watermark import PageScope

NUMBER_FORMATS = ["Page {page} of {total}", "{page}", "{page} / {total}", "- {page} -", "Page {page}"]


class HeaderFooterDialog(QDialog):
    """Six text slots (or just page numbers) with typography and page range."""

    def __init__(self, page_count: int, current: int, parent: QWidget | None = None,
                 numbers_only: bool = False) -> None:
        super().__init__(parent)
        self.numbers_only = numbers_only
        self.setWindowTitle("Add Page Numbers" if numbers_only else "Add Header & Footer")
        self.slots: dict[str, QLineEdit] = {}
        layout = QVBoxLayout(self)
        if numbers_only:
            form = QFormLayout()
            self.number_format = QComboBox(self)
            self.number_format.setEditable(True)
            self.number_format.addItems(NUMBER_FORMATS)
            self.position = QComboBox(self)
            for pos in POSITIONS:
                self.position.addItem(pos.replace("-", " ").capitalize(), pos)
            self.position.setCurrentIndex(POSITIONS.index("bottom-center"))
            form.addRow("Format:", self.number_format)
            form.addRow("Position:", self.position)
            layout.addLayout(form)
        else:
            box = QGroupBox("Text (placeholders: {page} {total} {date} {filename} {title})", self)
            grid = QGridLayout(box)
            for col, name in enumerate(("Left", "Center", "Right")):
                grid.addWidget(QLabel(name, box), 0, col + 1)
            for row, vertical in enumerate(("top", "bottom")):
                grid.addWidget(QLabel("Header:" if vertical == "top" else "Footer:", box), row + 1, 0)
                for col, horizontal in enumerate(("left", "center", "right")):
                    edit = QLineEdit(box)
                    grid.addWidget(edit, row + 1, col + 1)
                    self.slots[f"{vertical}-{horizontal}"] = edit
            self.slots["bottom-right"].setText("Page {page} of {total}")
            layout.addWidget(box)
        form = QFormLayout()
        self.font_size = QDoubleSpinBox(self)
        self.font_size.setRange(4, 72)
        self.font_size.setValue(10)
        self.font_size.setSuffix(" pt")
        self.family = QComboBox(self)
        self.family.addItems(["Helvetica", "Times", "Courier"])
        self.color = ColorButton("#000000", self)
        self.margin = QDoubleSpinBox(self)
        self.margin.setRange(0, 200)
        self.margin.setValue(10)
        self.margin.setSuffix(" mm")
        self.start = QSpinBox(self)
        self.start.setRange(0, 100000)
        self.start.setValue(1)
        self.scope = PageScope(page_count, current, self)
        form.addRow("Font:", self.family)
        form.addRow("Size:", self.font_size)
        form.addRow("Colour:", self.color)
        form.addRow("Distance from edge:", self.margin)
        form.addRow("First number:", self.start)
        form.addRow("Apply to:", self.scope)
        layout.addLayout(form)
        layout.addWidget(QLabel("Numbering counts the pages you apply it to.", self))
        self.error = QLabel(self)
        self.error.setStyleSheet("color: #c0392b")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def spec(self) -> HeaderFooter:
        if self.numbers_only:
            texts = {self.position.currentData(): self.number_format.currentText()}
        else:
            texts = {pos: edit.text() for pos, edit in self.slots.items() if edit.text().strip()}
        spec = HeaderFooter(texts, self.font_size.value(), self.family.currentText(),
                            rgb_floats(qcolor(self.color.color)), self.margin.value() * 72 / 25.4, self.start.value())
        spec.validate()
        if self.numbers_only and "{page}" not in self.number_format.currentText():
            raise InvalidInput("The format must contain {page}.")
        return spec

    def accept(self) -> None:
        try:
            self.spec()
            self.scope.pages()
        except InvalidInput as exc:
            self.error.setText(exc.message)
            return
        super().accept()
