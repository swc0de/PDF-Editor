"""Offering autosaved documents after a crash (mixed into ``MainWindow``)."""

from __future__ import annotations

from ..core.document import PdfDocument
from ..core.errors import PasswordRequired, WrongPassword
from .autosave import RecoveryEntry, find_orphans
from .dialogs.password import ask_password
from .errors import show_error


class RecoveryMixin:
    """Restores recovery copies left by a session that did not exit cleanly."""

    def offer_recovery(self) -> int:
        """Offer documents autosaved by a crashed session; returns how many were restored."""
        entries = find_orphans(self.autosave.folder, self.autosave.session)
        if not entries:
            return 0
        from .dialogs.recovery import RecoveryDialog

        dialog = RecoveryDialog(entries, self)
        result = dialog.exec()
        if result == RecoveryDialog.DISCARD:
            for entry in entries:
                entry.discard()
            return 0
        if result != RecoveryDialog.DialogCode.Accepted:
            return 0
        restored = 0
        for entry in dialog.selected():
            if self.restore_entry(entry):
                restored += 1
        return restored

    def restore_entry(self, entry: RecoveryEntry) -> bool:
        """Open one recovery copy as a modified document; True on success."""
        with open(entry.pdf_path, "rb") as fh:
            data = fh.read()
        password, wrong = None, False
        while True:
            try:
                doc = PdfDocument.from_bytes(data, path=entry.original_path, password=password,
                                             name=entry.display_name)
                break
            except (PasswordRequired, WrongPassword) as exc:
                wrong = isinstance(exc, WrongPassword)
                password = ask_password(self, entry.display_name, wrong)
                if password is None:
                    return False
            except Exception as exc:
                show_error(exc, self)
                return False
        doc.mark_modified()
        self.add_document(doc)
        entry.discard()
        return True
