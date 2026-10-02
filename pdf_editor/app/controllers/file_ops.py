"""File menu: new, open (dialog/recent/drop/CLI), save, save as, close, print."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Iterable

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from ...core.document import PdfDocument
from ...core.errors import PasswordRequired, WrongPassword
from ..dialogs.password import ask_password
from ..errors import guarded, show_error

if TYPE_CHECKING:  # pragma: no cover
    from ..document_tab import DocumentTab
    from ..main_window import MainWindow

OPEN_FILTER = (
    "PDF files (*.pdf);;Images and other documents (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.xps *.epub *.cbz);;"
    "All files (*)"
)
PDF_FILTER = "PDF files (*.pdf)"


class FileController(QObject):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.w = window

    # -- open -------------------------------------------------------------------
    def new_document(self) -> None:
        self.w.add_document(PdfDocument.new())

    def open_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self.w, "Open", self.w.settings.last_directory, OPEN_FILTER)
        if paths:
            self.w.settings.last_directory = os.path.dirname(paths[0])
            self.open_paths(paths)

    def open_paths(self, paths: Iterable[str]) -> None:
        for path in paths:
            self.open_path(path)

    def open_recent(self, path: str) -> None:
        if not os.path.exists(path):
            QMessageBox.warning(self.w, "File not found", f"'{path}' no longer exists. It was removed from the list.")
            self.w.settings.remove_recent_file(path)
            self.w.refresh_recent()
            return
        self.open_path(path)

    def open_path(self, path: str) -> "DocumentTab | None":
        """Open ``path`` in a new tab (or focus it if already open)."""
        path = os.path.abspath(path)
        existing = self.w.find_tab(path)
        if existing is not None:
            self.w.tabs.setCurrentWidget(existing)
            return existing
        password: str | None = None
        wrong = False
        while True:
            try:
                QApplication.setOverrideCursor(self.w.cursor_busy)
                try:
                    doc = PdfDocument.open(path, password)
                finally:
                    QApplication.restoreOverrideCursor()
                break
            except (PasswordRequired, WrongPassword) as exc:
                wrong = isinstance(exc, WrongPassword)
                password = ask_password(self.w, os.path.basename(path), wrong)
                if password is None:
                    return None
            except Exception as exc:
                show_error(exc, self.w)
                return None
        tab = self.w.add_document(doc)
        if doc.path:
            self.w.settings.add_recent_file(doc.path)
            self.w.refresh_recent()
        return tab

    # -- save -------------------------------------------------------------------
    def save(self, tab: "DocumentTab | None" = None) -> bool:
        """Save the document; returns False if cancelled or failed."""
        tab = tab or self.w.current_tab()
        if tab is None:
            return False
        if not tab.doc.path:
            return self.save_as(tab)
        with guarded(self.w, "Save failed") as g:
            QApplication.setOverrideCursor(self.w.cursor_busy)
            try:
                result = tab.doc.save()
            finally:
                QApplication.restoreOverrideCursor()
            kind = "incrementally" if result.incremental else "(full rewrite)"
            self.w.statusBar().showMessage(f"Saved {os.path.basename(result.path)} {kind}", 4000)
            self.w.on_document_saved(tab)
        return not g.failed

    def save_as(self, tab: "DocumentTab | None" = None) -> bool:
        tab = tab or self.w.current_tab()
        if tab is None:
            return False
        start = tab.doc.path or os.path.join(self.w.settings.last_directory, tab.doc.display_name)
        path, _ = QFileDialog.getSaveFileName(self.w, "Save As", start, PDF_FILTER)
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        other = self.w.find_tab(path)
        if other is not None and other is not tab:
            QMessageBox.warning(self.w, "File is open", "That file is open in another tab. Close it first.")
            return False
        with guarded(self.w, "Save failed") as g:
            QApplication.setOverrideCursor(self.w.cursor_busy)
            try:
                result = tab.doc.save(path)
            finally:
                QApplication.restoreOverrideCursor()
            self.w.settings.last_directory = os.path.dirname(path)
            self.w.settings.add_recent_file(result.path)
            self.w.refresh_recent()
            self.w.statusBar().showMessage(f"Saved {os.path.basename(result.path)}", 4000)
            self.w.on_document_saved(tab)
        return not g.failed

    # -- close ------------------------------------------------------------------
    def maybe_save(self, tab: "DocumentTab") -> bool:
        """Ask "Save changes?" for a modified tab; False means the user cancelled."""
        if not tab.doc.is_modified:
            return True
        self.w.tabs.setCurrentWidget(tab)
        answer = QMessageBox.question(
            self.w,
            "Save changes?",
            f"Do you want to save the changes to '{tab.doc.display_name}' before closing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save(tab)
        return answer == QMessageBox.StandardButton.Discard

    def close_tab(self, index: int) -> bool:
        tab = self.w.tabs.widget(index)
        if tab is None or not self.maybe_save(tab):
            return False
        self.w.remove_tab(tab)
        return True

    def close_current(self) -> None:
        index = self.w.tabs.currentIndex()
        if index >= 0:
            self.close_tab(index)

    def close_all(self) -> bool:
        while self.w.tabs.count():
            if not self.close_tab(self.w.tabs.count() - 1):
                return False
        return True

    def print_document(self) -> None:
        tab = self.w.current_tab()
        if tab is None:
            return
        from ..printing import print_document

        with guarded(self.w, "Printing failed"):
            print_document(self.w, tab)

    def quit(self) -> None:
        self.w.close()
