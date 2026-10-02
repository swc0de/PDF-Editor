"""Password protection (AES-256) with permissions."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.errors import InvalidInput
from ...core.operations.security import PERMISSION_FLAGS, PERMISSION_LABELS, EncryptionSettings


def _password_edit(parent: QWidget) -> QLineEdit:
    edit = QLineEdit(parent)
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    return edit


class ProtectDialog(QDialog):
    """Collects an open password, a permissions password and allowed actions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Password Protection (AES-256)")
        self.user = _password_edit(self)
        self.user_again = _password_edit(self)
        self.owner = _password_edit(self)
        self.owner_again = _password_edit(self)
        form = QFormLayout()
        form.addRow(QLabel("<b>Open password</b> (leave empty to allow opening without a password):", self))
        form.addRow("Password:", self.user)
        form.addRow("Repeat:", self.user_again)
        form.addRow(QLabel("<b>Permissions password</b> (required to change security later):", self))
        form.addRow("Password:", self.owner)
        form.addRow("Repeat:", self.owner_again)
        box = QGroupBox("Allow people who open the file to…", self)
        grid = QGridLayout(box)
        self.permissions: dict[str, QCheckBox] = {}
        for i, name in enumerate(PERMISSION_FLAGS):
            check = QCheckBox(PERMISSION_LABELS[name], box)
            check.setChecked(name in ("print", "print_high_quality", "copy", "accessibility", "fill_forms"))
            grid.addWidget(check, i // 2, i % 2)
            self.permissions[name] = check
        self.error = QLabel(self)
        self.error.setStyleSheet("color: #c0392b")
        note = QLabel("The protection is applied when you save the document.", self)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(box)
        layout.addWidget(note)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    def settings(self) -> EncryptionSettings:
        if self.user.text() != self.user_again.text():
            raise InvalidInput("The two open passwords do not match.")
        if self.owner.text() != self.owner_again.text():
            raise InvalidInput("The two permissions passwords do not match.")
        allowed = frozenset(name for name, check in self.permissions.items() if check.isChecked())
        settings = EncryptionSettings(self.owner.text(), self.user.text(), allowed)
        settings.validate()
        return settings

    def accept(self) -> None:
        try:
            self.settings()
        except InvalidInput as exc:
            self.error.setText(exc.message)
            return
        super().accept()
