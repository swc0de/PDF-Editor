"""One open document: model, undo stack, renderer, viewer, search and tools."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget

from ..core.document import PdfDocument
from ..core.events import Change, ChangeEvent
from ..settings import Settings
from .errors import guarded, show_error, show_warning
from .form_filler import FormFiller
from .render_cache import RenderScheduler
from .search import SearchController
from .tools import create_tool
from .tools.base import PageEvent, Tool
from .tools.text_select import TextSelector
from .undo import QtHistory
from .viewer import PdfViewer

MB = 1024 * 1024


class DocumentTab(QWidget):
    """The widget shown in one tab of the main window."""

    modifiedChanged = Signal(bool)
    documentChanged = Signal(object)  # ChangeEvent
    currentPageChanged = Signal(int)
    zoomChanged = Signal(float)
    toolChanged = Signal(str)
    selectionChanged = Signal()
    annotationSelected = Signal(object, object)  # page, xref (None, None = cleared)

    def __init__(self, doc: PdfDocument, settings: Settings, tool_options, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.settings = settings
        self.tool_options = tool_options
        self.history = QtHistory(settings.undo_memory_mb * MB, parent=self)
        doc.set_history(self.history)
        self.scheduler = RenderScheduler(doc, parent=self)
        self.viewer = PdfViewer(doc, self.scheduler, self)
        self.text_selector = TextSelector(self)
        self.search = SearchController(self)
        self.form_filler = FormFiller(self)
        self._tools: dict[str, Tool] = {}
        self.tool_name = ""

        self.banner = QLabel(self)
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        self.banner.setStyleSheet("QLabel { background: #fff3cd; color: #5c4400; padding: 6px 10px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.banner)
        layout.addWidget(self.viewer, 1)

        doc.add_listener(self._on_document_event)
        self.history.changed.connect(lambda: self.modifiedChanged.emit(self.doc.is_modified))
        self.history.failed.connect(lambda exc: show_error(exc, self))
        self.viewer.currentPageChanged.connect(self.currentPageChanged)
        self.viewer.zoomChanged.connect(self.zoomChanged)

        self.viewer.set_continuous(settings.continuous_scroll)
        self.viewer.set_invert(settings.invert_pages)
        self._apply_default_zoom()
        self.set_tool("select")
        self._update_banner()

    # -- presentation -----------------------------------------------------------
    @property
    def title(self) -> str:
        return self.doc.display_name + (" *" if self.doc.is_modified else "")

    def _apply_default_zoom(self) -> None:
        mode = self.settings.default_zoom
        if mode == "fit-width":
            self.viewer.fit_width()
        elif mode == "fit-page":
            self.viewer.fit_page()
        elif mode == "actual":
            self.viewer.set_zoom(1.0)
        else:
            self.viewer.set_zoom(int(mode) / 100.0)

    def _update_banner(self) -> None:
        import pymupdf

        if not self.doc.has_permission(pymupdf.PDF_PERM_MODIFY):
            self.banner.setText(
                "This document is protected: editing is restricted. "
                "Use Tools ▸ Security ▸ Enter Owner Password to unlock all features."
            )
            self.banner.setVisible(True)
        else:
            self.banner.setVisible(False)

    def show_message(self, text: str) -> None:
        """Show a transient message in the main window's status bar."""
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(text, 5000)

    # -- tools ------------------------------------------------------------------
    def tool(self, name: str) -> Tool:
        if name not in self._tools:
            self._tools[name] = create_tool(name, self)
        return self._tools[name]

    @property
    def active_tool(self) -> Tool | None:
        return self.viewer.tool

    def set_tool(self, name: str) -> None:
        if name == self.tool_name:
            return
        tool = self.tool(name)
        self.viewer.set_tool(tool)
        self.tool_name = name
        self.toolChanged.emit(name)
        self.viewer.setFocus()

    # -- selection ----------------------------------------------------------------
    def selection_changed(self) -> None:
        self.selectionChanged.emit()

    def show_selection_menu(self, event: PageEvent) -> bool:
        """Context menu for selected text (copy and markup actions)."""
        selector = self.text_selector
        if not selector.has_selection or selector.page != event.pno:
            return False
        menu = QMenu(self)
        copy = QAction("Copy", menu)
        copy.triggered.connect(selector.copy)
        menu.addAction(copy)
        window = self.window()
        extra = getattr(window, "selection_menu_actions", None)
        if callable(extra):
            menu.addSeparator()
            for action in extra():
                menu.addAction(action)
        menu.exec(event.global_pos)
        return True

    # -- annotations and form widgets ------------------------------------------------
    def annotation_selected(self, pno: int | None, xref: int | None) -> None:
        self.annotationSelected.emit(pno, xref)

    def select_annotation(self, pno: int, xref: int) -> None:
        """Switch to the Select tool and select (and reveal) an annotation."""
        self.set_tool("select")
        self.tool("select").select_annotation(pno, xref, scroll=True)

    def edit_annotation(self, pno: int, xref: int, properties: bool = False) -> None:
        """Open the properties dialog (focused on the text for notes/text boxes)."""
        from .dialogs.annotation_props import AnnotationPropertiesDialog

        info = self.doc.annotation_info(pno, xref)
        if info is None:
            return
        dialog = AnnotationPropertiesDialog(info, self, focus_text=not properties)
        if dialog.exec():
            style, text = dialog.changes()
            with guarded(self, "Cannot change annotation"):
                self.doc.update_annotation(pno, xref, text, **style)

    def widget_at(self, event: PageEvent):
        """The form field under the cursor, if any."""
        return self.form_filler.field_at(event.pno, event.point)

    def handle_widget_click(self, event: PageEvent) -> bool:
        """Toggle/edit a form field under the cursor; True if one was hit."""
        field = self.form_filler.field_at(event.pno, event.point)
        if field is None:
            return False
        return self.form_filler.click(event.pno, field, event.global_pos)

    # -- document events ------------------------------------------------------------
    def _on_document_event(self, event: ChangeEvent) -> None:
        kind = event.kind
        if kind == Change.RELOAD:
            self.viewer.rebuild()
        elif kind == Change.STRUCTURE:
            if event.pages is None or self.viewer.page_count != self.doc.page_count:
                self.viewer.rebuild()
            else:
                self.viewer.update_page_sizes()
                self.viewer.refresh_pages(list(event.pages))
        elif kind in (Change.CONTENT, Change.ANNOTATIONS, Change.FORMS):
            self.viewer.refresh_pages(list(event.pages) if event.pages else None)
        elif kind == Change.SECURITY:
            self._update_banner()
        elif kind == Change.HISTORY_TRUNCATED:
            show_warning(
                self,
                "Change cannot be undone",
                "This change was too large to keep in the undo history (see Settings ▸ Undo memory).",
            )
        if kind in (Change.RELOAD, Change.STRUCTURE, Change.CONTENT):
            self.text_selector.invalidate()
            if self.search.active:
                self.search.restart()
        for tool in self._tools.values():
            tool.document_changed()
        self.documentChanged.emit(event)
        self.modifiedChanged.emit(self.doc.is_modified)

    def close_document(self) -> None:
        """Release resources; the tab is about to be deleted."""
        self.search.clear(emit=False)
        self.viewer.set_tool(None)
        self.viewer.shutdown()
        self.scheduler.forget_document()
        self.doc.remove_listener(self._on_document_event)
        self.doc.close()
