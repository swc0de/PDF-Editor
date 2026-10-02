"""Crop tool: draw the area to keep, then choose which pages to crop."""

from __future__ import annotations

import pymupdf
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

from ..dialogs.crop import CropDialog
from ..errors import guarded
from .rect_tool import RectDrawTool


class CropTool(RectDrawTool):
    name = "crop"
    label = "Crop"
    tooltip = "Draw the area of the page to keep"
    outline = QColor(0, 150, 80)
    fill = QColor(0, 150, 80, 35)

    def finish(self, pno: int, visual: QRectF, rect: pymupdf.Rect) -> None:
        window = self.tab.window()
        selected = window.selected_pages() if hasattr(window, "selected_pages") else [pno]
        dialog = CropDialog(len(selected), self.tab, rect_mode=True)
        if not dialog.exec():
            return
        scope = dialog.scope_name()
        pages = {"current": [pno], "selected": selected, "all": list(range(self.doc.page_count))}[scope]
        with guarded(self.tab, "Crop failed"):
            self.doc.crop_pages(pages, rect)
            self.tab.set_tool("select")
