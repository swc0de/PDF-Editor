"""Offer to restore documents autosaved by a session that crashed."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ..autosave import RecoveryEntry


class RecoveryDialog(QDialog):
    """Lists recovery copies; the caller restores the checked ones on accept."""

    DISCARD = 2

    def __init__(self, entries: list[RecoveryEntry], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Recover Documents")
        self.entries = entries
        self.list = QListWidget(self)
        for entry in entries:
            item = QListWidgetItem(entry.label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setToolTip(entry.original_path or "Never saved")
            self.list.addItem(item)
        buttons = QDialogButtonBox(self)
        restore = buttons.addButton("Restore Selected", QDialogButtonBox.ButtonRole.AcceptRole)
        discard = buttons.addButton("Discard All", QDialogButtonBox.ButtonRole.DestructiveRole)
        later = buttons.addButton("Decide Later", QDialogButtonBox.ButtonRole.RejectRole)
        restore.clicked.connect(self.accept)
        discard.clicked.connect(lambda: self.done(self.DISCARD))
        later.clicked.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "PDF Editor did not close properly last time. These documents had unsaved changes "
            "and were autosaved. Restore them?", self, wordWrap=True))
        layout.addWidget(self.list)
        layout.addWidget(buttons)

    def selected(self) -> list[RecoveryEntry]:
        return [e for i, e in enumerate(self.entries)
                if self.list.item(i).checkState() == Qt.CheckState.Checked]
