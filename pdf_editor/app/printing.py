"""Printing through QPrinter: each page is rendered at printer resolution."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog, QPrinter
from PySide6.QtWidgets import QApplication, QProgressDialog, QWidget

from ..core.render import render_page
from .qt_utils import qimage_from_render

MAX_PRINT_DPI = 300


def page_range(printer: QPrinter, page_count: int, current: int) -> list[int]:
    """0-based pages selected in the print dialog."""
    mode = printer.printRange()
    if mode == QPrinter.PrintRange.PageRange:
        first, last = max(1, printer.fromPage()), min(page_count, printer.toPage() or page_count)
        return list(range(first - 1, last))
    if mode == QPrinter.PrintRange.CurrentPage:
        return [current]
    return list(range(page_count))


def print_document(parent: QWidget, tab) -> bool:
    """Show the print dialog and print; returns True if something was printed."""
    doc = tab.doc
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setDocName(doc.display_name)
    printer.setFromTo(1, doc.page_count)
    dialog = QPrintDialog(printer, parent)
    dialog.setOption(QAbstractPrintDialog.PrintDialogOption.PrintPageRange, True)
    dialog.setOption(QAbstractPrintDialog.PrintDialogOption.PrintCurrentPage, True)
    dialog.setMinMax(1, doc.page_count)
    if dialog.exec() != QPrintDialog.DialogCode.Accepted:
        return False
    pages = page_range(printer, doc.page_count, tab.viewer.current_page)
    if not pages:
        return False
    dpi = min(MAX_PRINT_DPI, printer.resolution())
    progress = QProgressDialog("Printing…", "Cancel", 0, len(pages), parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("The printer could not be started.")
    try:
        for i, pno in enumerate(pages):
            if progress.wasCanceled():
                printer.abort()
                return False
            progress.setValue(i)
            QApplication.processEvents()
            if i > 0:
                printer.newPage()
            image = qimage_from_render(render_page(doc.raw, pno, dpi / 72.0))
            target = QRectF(painter.viewport())
            # fit the page into the printable area, keeping its aspect ratio
            scale = min(target.width() / image.width(), target.height() / image.height())
            w, h = image.width() * scale, image.height() * scale
            painter.drawImage(QRectF(target.x() + (target.width() - w) / 2, target.y() + (target.height() - h) / 2, w, h), image)
        progress.setValue(len(pages))
    finally:
        painter.end()
    return True
