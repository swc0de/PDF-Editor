"""Split a document: by page ranges, every N pages, or one file per page."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QButtonGroup,
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
from ...core.operations.pages import split_every
from ...core.utils import parse_page_ranges


class SplitDialog(QDialog):
    def __init__(self, page_count: int, base_name: str, start_dir: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Split Document")
        self.page_count = page_count
        self.by_ranges = QRadioButton("By page ranges:", self)
        self.ranges = QLineEdit(self)
        self.ranges.setPlaceholderText("e.g. 1-3, 4-10, 11-")
        self.every = QRadioButton("Every N pages:", self)
        self.every_n = QSpinBox(self)
        self.every_n.setRange(1, max(1, page_count))
        self.every_n.setValue(min(2, max(1, page_count)))
        self.single = QRadioButton("One file per page", self)
        group = QButtonGroup(self)
        for button in (self.by_ranges, self.every, self.single):
            group.addButton(button)
        self.by_ranges.setChecked(True)
        self.ranges.textChanged.connect(lambda: self.by_ranges.setChecked(True))
        self.every_n.valueChanged.connect(lambda: self.every.setChecked(True))

        self.folder = QLineEdit(start_dir, self)
        browse = QPushButton("Browse…", self)
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)
        self.base = QLineEdit(base_name, self)
        self.preview = QLabel(self)

        form = QFormLayout()
        form.addRow(self.by_ranges, self.ranges)
        form.addRow(self.every, self.every_n)
        form.addRow(self.single)
        form.addRow("Save to folder:", folder_row)
        form.addRow("File name prefix:", self.base)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Split")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"The document has {page_count} pages.", self))
        layout.addLayout(form)
        layout.addWidget(self.preview)
        layout.addWidget(buttons)
        for signal in (self.ranges.textChanged, self.every_n.valueChanged, group.buttonClicked):
            signal.connect(self._update_preview)
        self._update_preview()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Output Folder", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def groups(self) -> list[list[int]]:
        """The page groups to write (raises :class:`InvalidInput`)."""
        if self.single.isChecked():
            return split_every(self.page_count, 1)
        if self.every.isChecked():
            return split_every(self.page_count, self.every_n.value())
        return parse_page_ranges(self.ranges.text(), self.page_count)

    def _update_preview(self) -> None:
        try:
            count = len(self.groups())
            self.preview.setText(f"This creates {count} file(s).")
        except InvalidInput as exc:
            self.preview.setText(exc.message)

    def accept(self) -> None:
        try:
            self.groups()
        except InvalidInput as exc:
            self.preview.setText(f"<span style='color:#c0392b'>{exc.message}</span>")
            return
        if not os.path.isdir(self.folder.text()):
            self.preview.setText("<span style='color:#c0392b'>Choose an existing output folder.</span>")
            return
        super().accept()
