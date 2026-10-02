"""Tools menu: document properties, security, compression, OCR, export."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject

from ..errors import guarded

if TYPE_CHECKING:  # pragma: no cover
    from ..main_window import MainWindow


class ToolsController(QObject):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.w = window

    def edit_metadata(self) -> None:
        tab = self.w.current_tab()
        if tab is None:
            return
        from ..dialogs.metadata import MetadataDialog

        dialog = MetadataDialog(tab, self.w)
        if dialog.exec():
            with guarded(self.w):
                tab.doc.set_metadata(dialog.values())
