"""Edit Content menu: signatures, watermarks, headers/footers, page numbers, flattening."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMessageBox

from ...settings import SavedSignature
from ..errors import guarded

if TYPE_CHECKING:  # pragma: no cover
    from ..main_window import MainWindow


class ContentController(QObject):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.w = window

    def new_signature(self) -> bool:
        """Create a signature (draw/type/import); returns True if one was made."""
        from ..dialogs.signature import SignatureDialog

        dialog = SignatureDialog(self.w)
        if not dialog.exec() or dialog.png is None:
            return False
        if dialog.save.isChecked():
            name = dialog.save_name.text().strip() or "Signature"
            self.w.settings.add_signature(SavedSignature(name, dialog.png))
            self.w.options_bar.refresh_signatures()
        else:
            self.w.tool_options.set(signature=dialog.png)
        tab = self.w.current_tab()
        if tab is not None:
            tab.set_tool("signature")
        return True

    def delete_signature(self, index: int) -> None:
        signatures = self.w.settings.signatures()
        if not 0 <= index < len(signatures):
            return
        answer = QMessageBox.question(self.w, "Delete signature", f"Delete the saved signature '{signatures[index].name}'?")
        if answer == QMessageBox.StandardButton.Yes:
            self.w.settings.remove_signature(index)
            self.w.options_bar.refresh_signatures()

    def watermark(self) -> None:
        tab = self.w.current_tab()
        if tab is None:
            return
        from ..dialogs.watermark import WatermarkDialog

        dialog = WatermarkDialog(tab.doc.page_count, tab.viewer.current_page, self.w)
        if dialog.exec():
            with guarded(self.w, "Cannot add watermark"):
                count = dialog.apply_to(tab.doc)
                self.w.statusBar().showMessage(f"Watermark added to {count} page(s).", 4000)

    def _header_footer(self, numbers_only: bool) -> None:
        tab = self.w.current_tab()
        if tab is None:
            return
        from ..dialogs.header_footer import HeaderFooterDialog

        dialog = HeaderFooterDialog(tab.doc.page_count, tab.viewer.current_page, self.w, numbers_only)
        if dialog.exec():
            with guarded(self.w, "Cannot add header/footer"):
                tab.doc.add_header_footer(dialog.scope.pages(), dialog.spec())

    def header_footer(self) -> None:
        self._header_footer(False)

    def page_numbers(self) -> None:
        self._header_footer(True)

    def flatten_forms(self) -> None:
        tab = self.w.current_tab()
        if tab is None:
            return
        if not tab.doc.form_fields():
            self.w.statusBar().showMessage("This document has no form fields.", 4000)
            return
        answer = QMessageBox.question(
            self.w, "Flatten form",
            "Flattening turns all form fields into ordinary page content: the values stay visible "
            "but can no longer be edited. You can undo this until you close the document. Continue?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            with guarded(self.w, "Cannot flatten form"):
                count = tab.doc.flatten_forms()
                self.w.statusBar().showMessage(f"Flattened {count} form field(s).", 4000)
