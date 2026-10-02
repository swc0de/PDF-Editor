"""Tools menu: properties, security, redaction, compression, OCR, exports, bookmarks."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QInputDialog, QLineEdit, QMessageBox

from ...core.operations import ocr as ocr_ops
from ...core.operations.security import has_full_permissions
from ...core.utils import file_size, format_size
from ..errors import guarded
from ..workers import remove_quietly, start_job, write_temp_copy

if TYPE_CHECKING:  # pragma: no cover
    from ..document_tab import DocumentTab
    from ..main_window import MainWindow


class ToolsController(QObject):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.w = window
        self._ocr_status: ocr_ops.OcrStatus | None = None

    def _tab(self) -> "DocumentTab | None":
        return self.w.current_tab()

    def _stem(self, tab: "DocumentTab") -> str:
        return os.path.splitext(tab.doc.display_name)[0]

    def _folder(self, tab: "DocumentTab") -> str:
        return os.path.dirname(tab.doc.path) if tab.doc.path else self.w.settings.last_directory

    # -- properties -----------------------------------------------------------
    def edit_metadata(self) -> None:
        tab = self._tab()
        if tab is None:
            return
        from ..dialogs.metadata import MetadataDialog

        dialog = MetadataDialog(tab, self.w)
        if dialog.exec():
            with guarded(self.w):
                tab.doc.set_metadata(dialog.values())

    def add_bookmark(self) -> None:
        if self._tab() is not None:
            self.w.docks["outline"].show()
            self.w.docks["outline"].raise_()
            self.w.outline.add_bookmark()

    # -- security --------------------------------------------------------------
    def owner_password(self) -> bool:
        """Unlock all permissions of a restricted document."""
        tab = self._tab()
        if tab is None:
            return False
        if has_full_permissions(tab.doc.raw):
            self.w.statusBar().showMessage("You already have full access to this document.", 4000)
            return True
        password, ok = QInputDialog.getText(self.w, "Owner Password", "Permissions (owner) password:",
                                            QLineEdit.EchoMode.Password)
        if not ok:
            return False
        if tab.doc.authenticate_owner(password):
            self.w.statusBar().showMessage("Full access granted.", 4000)
            return True
        QMessageBox.warning(self.w, "Owner Password", "That is not the owner password of this document.")
        return False

    def protect(self) -> None:
        tab = self._tab()
        if tab is None:
            return
        if tab.doc.is_encrypted and not has_full_permissions(tab.doc.raw) and not self.owner_password():
            return
        from ..dialogs.security import ProtectDialog

        dialog = ProtectDialog(self.w)
        if dialog.exec():
            with guarded(self.w, "Cannot set password"):
                tab.doc.set_encryption(dialog.settings())
                self.w.statusBar().showMessage("Password protection will be applied when you save.", 6000)

    def remove_password(self) -> None:
        tab = self._tab()
        if tab is None:
            return
        if not tab.doc.is_encrypted and tab.doc.encryption_policy is None:
            self.w.statusBar().showMessage("This document is not password protected.", 4000)
            return
        if not has_full_permissions(tab.doc.raw) and not self.owner_password():
            return
        with guarded(self.w, "Cannot remove password"):
            tab.doc.set_encryption(None)
            self.w.statusBar().showMessage("The password will be removed when you save.", 6000)

    # -- redaction ---------------------------------------------------------------
    def redact(self) -> None:
        tab = self._tab()
        if tab is None:
            return
        from ..dialogs.redaction import RedactionDialog

        RedactionDialog(tab, self.w).exec()

    # -- compression ----------------------------------------------------------------
    def compress(self) -> None:
        tab = self._tab()
        if tab is None:
            return
        from ..dialogs.tools_dialogs import CompressDialog

        before = file_size(tab.doc.path) if tab.doc.path and not tab.doc.is_modified else len(tab.doc.snapshot())
        dialog = CompressDialog(before, self.w)
        if not dialog.exec():
            return
        start = os.path.join(self._folder(tab), f"{self._stem(tab)}_compressed.pdf")
        output, _ = QFileDialog.getSaveFileName(self.w, "Save Compressed Copy As", start, "PDF files (*.pdf)")
        if not output:
            return
        if self.w.find_tab(output) is not None:
            QMessageBox.warning(self.w, "File is open", "Choose a file that is not open in a tab.")
            return
        source = write_temp_copy(tab.doc)

        def done(result) -> None:
            answer = QMessageBox.question(
                self.w, "Compression finished",
                f"Before: {format_size(result.before)}\nAfter: {format_size(result.after)} "
                f"({result.saved_percent:.0f}% smaller)\n\nOpen the compressed copy?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.w.file.open_path(result.path)

        start_job(self.w, "Compressing…", "pdf_editor.core.tasks:compress_task",
                  {"source": source, "output": output, "preset": dialog.preset(),
                   "password": tab.doc.password, "original_size": before},
                  on_success=done, on_finally=lambda: remove_quietly(source))

    # -- OCR ----------------------------------------------------------------------
    def ocr_status(self, refresh: bool = False) -> ocr_ops.OcrStatus:
        if self._ocr_status is None or refresh or not self._ocr_status.available:
            self._ocr_status = ocr_ops.tesseract_status()
        return self._ocr_status

    def ocr(self) -> None:
        tab = self._tab()
        if tab is None:
            return
        from ..dialogs.tools_dialogs import OcrDialog

        status = self.ocr_status(refresh=True)
        dialog = OcrDialog(status, tab.doc.page_count, tab.viewer.current_page, self.w)
        if not dialog.exec() or not status.available:
            return
        with guarded(self.w):
            pages = dialog.scope.pages()
        source = write_temp_copy(tab.doc)
        output = source + ".ocr.pdf"

        def done(result) -> None:
            if result.processed:
                with open(output, "rb") as fh:
                    tab.doc.replace_content("Recognize text (OCR)", fh.read())
            skipped = f", {len(result.skipped)} skipped (already had text)" if result.skipped else ""
            QMessageBox.information(self.w, "OCR finished",
                                    f"Recognised {result.words} words on {len(result.processed)} page(s){skipped}.")

        start_job(self.w, "Recognizing text…", "pdf_editor.core.tasks:ocr_task",
                  {"source": source, "output": output, "pages": pages, "language": dialog.language.currentText(),
                   "dpi": dialog.dpi.value(), "skip_text_pages": dialog.skip.isChecked(),
                   "password": tab.doc.password},
                  on_success=done, on_finally=lambda: (remove_quietly(source), remove_quietly(output)))

    # -- exports -------------------------------------------------------------------
    def _open_folder_prompt(self, title: str, message: str, folder: str) -> None:
        answer = QMessageBox.question(self.w, title, f"{message}\n\nOpen the folder?")
        if answer == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def export_images(self) -> None:
        tab = self._tab()
        if tab is None:
            return
        from ..dialogs.tools_dialogs import ExportImagesDialog

        dialog = ExportImagesDialog(tab.doc.page_count, tab.viewer.current_page, self._folder(tab), self._stem(tab), self.w)
        if not dialog.exec():
            return
        source, folder = write_temp_copy(tab.doc), dialog.folder.text()
        start_job(self.w, "Exporting pages…", "pdf_editor.core.tasks:export_images_task",
                  {"source": source, "output_dir": folder, "pages": dialog.scope.pages(),
                   "fmt": dialog.format.currentData(), "dpi": dialog.dpi.value(), "base_name": dialog.base.text(),
                   "jpg_quality": dialog.quality.value(), "password": tab.doc.password},
                  on_success=lambda paths: self._open_folder_prompt("Export finished", f"Saved {len(paths)} image(s).", folder),
                  on_finally=lambda: remove_quietly(source))

    def extract_images(self) -> None:
        tab = self._tab()
        if tab is None:
            return
        folder = QFileDialog.getExistingDirectory(self.w, "Extract Images To", self._folder(tab))
        if not folder:
            return
        source = write_temp_copy(tab.doc)
        start_job(self.w, "Extracting images…", "pdf_editor.core.tasks:extract_images_task",
                  {"source": source, "output_dir": folder, "base_name": self._stem(tab), "password": tab.doc.password},
                  on_success=lambda paths: self._open_folder_prompt(
                      "Extraction finished", f"Saved {len(paths)} image(s)." if paths else "The document has no images.",
                      folder),
                  on_finally=lambda: remove_quietly(source))

    def export_text(self) -> None:
        tab = self._tab()
        if tab is None:
            return
        start = os.path.join(self._folder(tab), f"{self._stem(tab)}.txt")
        output, _ = QFileDialog.getSaveFileName(self.w, "Export Text As", start, "Text files (*.txt)")
        if not output:
            return
        source = write_temp_copy(tab.doc)
        start_job(self.w, "Exporting text…", "pdf_editor.core.tasks:export_text_task",
                  {"source": source, "output": output, "password": tab.doc.password},
                  on_success=lambda n: self.w.statusBar().showMessage(f"Exported {n} characters to {output}", 6000),
                  on_finally=lambda: remove_quietly(source))
