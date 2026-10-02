"""Mark search terms for redaction, review all marks, and apply them."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..errors import guarded

WARNING = (
    "Applying redactions PERMANENTLY removes the marked text, image areas and drawings. "
    "This cannot be reversed once the file is saved. Make sure you keep an unredacted copy if you need one."
)


class RedactionDialog(QDialog):
    """Search-and-mark plus review/apply, operating on a document tab."""

    jumpRequested = Signal(int, int)

    def __init__(self, tab, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tab = tab
        self.setWindowTitle("Redact")
        self.resize(520, 520)
        self.term = QLineEdit(self)
        self.term.setPlaceholderText("Text to redact everywhere (e.g. a name or account number)")
        self.match_case = QCheckBox("Match case", self)
        mark = QPushButton("Mark All", self)
        mark.clicked.connect(self.mark_term)
        self.term.returnPressed.connect(self.mark_term)
        row = QHBoxLayout()
        row.addWidget(self.term, 1)
        row.addWidget(self.match_case)
        row.addWidget(mark)
        self.list = QListWidget(self)
        self.list.itemDoubleClicked.connect(self._jump)
        remove = QPushButton("Remove Selected Mark", self)
        remove.clicked.connect(self.remove_selected)
        self.scrub = QCheckBox("Also remove hidden information (metadata, JavaScript, attachments, hidden text)", self)
        warning = QLabel(WARNING, self)
        warning.setWordWrap(True)
        warning.setStyleSheet("QLabel { background: #fdecea; color: #7a1c13; padding: 8px; border-radius: 4px; }")
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self.apply_button = self.buttons.addButton("Apply Redactions…", QDialogButtonBox.ButtonRole.ActionRole)
        self.apply_button.clicked.connect(self.apply)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>1. Mark</b> — draw areas with the Redact tool, or search for text:", self))
        layout.addLayout(row)
        layout.addWidget(QLabel("<b>2. Review</b> — double-click a mark to show it:", self))
        layout.addWidget(self.list, 1)
        layout.addWidget(remove, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(QLabel("<b>3. Apply</b>", self))
        layout.addWidget(warning)
        layout.addWidget(self.scrub)
        layout.addWidget(self.buttons)
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        for mark in self.tab.doc.redaction_marks():
            text = mark.contents or "Area"
            item = QListWidgetItem(f"Page {mark.page + 1}: {text}")
            item.setData(Qt.ItemDataRole.UserRole, (mark.page, mark.xref))
            self.list.addItem(item)
        self.apply_button.setEnabled(self.list.count() > 0)

    def mark_term(self) -> None:
        with guarded(self):
            count = self.tab.doc.mark_redaction_text(self.term.text(), self.match_case.isChecked())
            if count == 0:
                QMessageBox.information(self, "Redact", f"'{self.term.text()}' was not found.")
            self.refresh()

    def remove_selected(self) -> None:
        for item in self.list.selectedItems():
            pno, xref = item.data(Qt.ItemDataRole.UserRole)
            with guarded(self):
                self.tab.doc.delete_annotation(pno, xref)
        self.refresh()

    def _jump(self, item: QListWidgetItem) -> None:
        pno, xref = item.data(Qt.ItemDataRole.UserRole)
        self.tab.select_annotation(pno, xref)

    def apply(self) -> None:
        count = self.list.count()
        answer = QMessageBox.warning(
            self, "Apply redactions?",
            f"{WARNING}\n\nRemove the content under {count} mark(s) now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        with guarded(self, "Redaction failed") as g:
            pages = self.tab.doc.apply_redactions(scrub=self.scrub.isChecked())
        if not g.failed:
            QMessageBox.information(
                self, "Redactions applied",
                f"Content was removed from {pages} page(s). Save the document to make it permanent "
                "(the file will be fully rewritten so no trace of the removed content remains).",
            )
            self.accept()
