"""Edit menu (undo, copy, find, settings), tool switching and help."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from ... import APP_NAME, __version__
from ..errors import log_file_path

if TYPE_CHECKING:  # pragma: no cover
    from ..main_window import MainWindow


class EditController(QObject):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.w = window

    def undo(self) -> None:
        if (tab := self.w.current_tab()) is not None:
            tab.history.undo()

    def redo(self) -> None:
        if (tab := self.w.current_tab()) is not None:
            tab.history.redo()

    def copy(self) -> None:
        tab = self.w.current_tab()
        if tab is None:
            return
        tool = tab.active_tool
        if tool is not None and hasattr(tool, "copy") and tool.copy():
            return
        if not tab.text_selector.copy():
            self.w.statusBar().showMessage("Nothing selected to copy.", 3000)

    def select_all(self) -> None:
        tab = self.w.current_tab()
        if tab is not None:
            tab.text_selector.select_all(tab.viewer.current_page)
            tab.selection_changed()

    def find(self) -> None:
        self.w.search_bar.focus()

    def find_next(self) -> None:
        self.w.search_bar.find_next()

    def find_previous(self) -> None:
        self.w.search_bar.find_previous()

    def settings(self) -> None:
        from ..dialogs.settings import SettingsDialog

        dialog = SettingsDialog(self.w.settings, self.w)
        if dialog.exec():
            self.w.apply_settings()


class ToolController(QObject):
    """Switches the active interactive tool of the current document."""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.w = window

    def set(self, name: str) -> None:
        tab = self.w.current_tab()
        if tab is not None:
            tab.set_tool(name)


class HelpController(QObject):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.w = window

    def shortcuts(self) -> None:
        from ..dialogs.shortcuts import ShortcutsDialog

        ShortcutsDialog(self.w).exec()

    def about(self) -> None:
        import pymupdf
        import PySide6

        QMessageBox.about(
            self.w,
            f"About {APP_NAME}",
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>A lightweight desktop PDF editor.</p>"
            f"<p>PyMuPDF {pymupdf.VersionBind} · PySide6 {PySide6.__version__}</p>",
        )

    def open_log_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(log_file_path())))
