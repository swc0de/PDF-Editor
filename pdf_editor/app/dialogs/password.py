"""Password prompt for opening protected PDFs."""

from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QLineEdit, QWidget


def ask_password(parent: QWidget | None, filename: str, wrong: bool = False) -> str | None:
    """Ask for a document password; returns ``None`` if the user cancels."""
    prompt = f"'{filename}' is password protected.\nEnter the password to open it:"
    if wrong:
        prompt = f"The password was not correct.\n\n{prompt}"
    text, ok = QInputDialog.getText(parent, "Password Required", prompt, QLineEdit.EchoMode.Password)
    return text if ok else None
