"""Redact tool: draw areas to mark them for redaction."""

from __future__ import annotations

import pymupdf
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

from ..errors import guarded
from .base import PageEvent
from .rect_tool import RectDrawTool


class RedactTool(RectDrawTool):
    """Marks are only applied from Tools ▸ Redact ▸ Review & Apply."""

    name, label = "redact", "Redact"
    tooltip = "Draw areas to mark them for redaction"
    hint = "Drag over content to mark it. Nothing is removed until you choose Tools ▸ Review & Apply Redactions."
    outline = QColor(200, 0, 0)
    fill = QColor(0, 0, 0, 90)
    dashed = False
    options_used: set[str] = set()

    def finish(self, pno: int, visual: QRectF, rect: pymupdf.Rect) -> None:
        with guarded(self.tab, "Cannot mark area"):
            self.doc.mark_redaction(pno, rect)
            count = len(self.doc.redaction_marks())
            self.tab.show_message(f"{count} area(s) marked for redaction. Apply them from the Tools menu.")

    def click(self, pno: int, event: PageEvent) -> None:
        """A click marks the text line under the cursor."""
        span = self.doc.text_span_at(pno, event.point)
        if span is not None:
            self.finish(pno, QRectF(), span.bbox)
