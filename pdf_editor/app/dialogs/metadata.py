"""Document properties: edit title, author, subject and keywords."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ...core.operations.metadata import document_info
from ...core.utils import file_size, format_size


class MetadataDialog(QDialog):
    FIELDS = (("title", "Title"), ("author", "Author"), ("subject", "Subject"), ("keywords", "Keywords"))

    def __init__(self, tab, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Document Properties")
        self.setMinimumWidth(460)
        self.tab = tab
        values = tab.doc.metadata()
        form = QFormLayout()
        self.edits: dict[str, QLineEdit] = {}
        for key, label in self.FIELDS:
            edit = QLineEdit(values.get(key, ""), self)
            form.addRow(f"{label}:", edit)
            self.edits[key] = edit
        self.edits["keywords"].setPlaceholderText("comma, separated, words")
        info = document_info(tab.doc.raw)
        form.addRow(QLabel("<b>Information</b>"))
        form.addRow("File:", QLabel(tab.doc.path or "(not saved)"))
        form.addRow("Size:", QLabel(format_size(file_size(tab.doc.path)) if tab.doc.path else "-"))
        form.addRow("Pages:", QLabel(info["pages"]))
        form.addRow("PDF version:", QLabel(info["format"]))
        form.addRow("Security:", QLabel(info["encryption"]))
        form.addRow("Producer:", QLabel(values.get("producer", "")))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict[str, str]:
        return {key: edit.text() for key, edit in self.edits.items()}
