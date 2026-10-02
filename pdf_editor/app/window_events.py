"""Main-window reactions to document-tab events (mixed into ``MainWindow``)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtGui import QAction

from ..core.events import Change
from . import menus
from .tools import TOOL_CLASSES

if TYPE_CHECKING:  # pragma: no cover
    from .document_tab import DocumentTab


class WindowEventsMixin:
    """Keeps panels, thumbnails and actions in sync with the current tab."""

    def _on_document_changed(self, tab: DocumentTab, event) -> None:
        if tab is not self.current_tab():
            return
        if event.kind in (Change.STRUCTURE, Change.RELOAD):
            tab.thumb_model.refresh(None)
            self.thumbnails.sync_current(tab.viewer.current_page)
        elif event.kind in (Change.CONTENT, Change.ANNOTATIONS, Change.FORMS):
            tab.thumb_model.refresh(list(event.pages) if event.pages else None)
        if event.kind in (Change.OUTLINE, Change.RELOAD, Change.STRUCTURE):
            self.outline.reload()
        self.annotations_panel.on_document_event(event)
        self.update_ui()

    def _on_page_changed(self, tab: DocumentTab) -> None:
        if tab is self.current_tab():
            self.thumbnails.sync_current(tab.viewer.current_page)
            self.update_ui()

    def _on_zoom_changed(self, tab: DocumentTab) -> None:
        if tab is self.current_tab():
            self.update_ui()

    def _on_tool_changed(self, tab: DocumentTab, name: str) -> None:
        if tab is self.current_tab():
            action = self.actions.get(f"tool.{name}")
            if action is not None:
                action.setChecked(True)
            cls = TOOL_CLASSES.get(name)
            self.options_bar.show_for(set(getattr(cls, "options_used", set())), getattr(cls, "hint", "") or
                                      getattr(cls, "tooltip", ""))

    def _on_history_changed(self, tab: DocumentTab) -> None:
        if tab is self.current_tab():
            self.update_ui()

    def on_document_saved(self, tab: DocumentTab) -> None:
        self._update_tab_title(tab)
        self.update_ui()

    def on_pages_dropped(self, tab: DocumentTab, pages: list[int], target: int) -> None:
        """Thumbnails were dragged to a new position."""
        self.pages_ctl.move_pages(tab, pages, target)

    def on_files_dropped(self, tab: DocumentTab, paths: list[str], target: int) -> None:
        """Files dropped onto the thumbnail strip are inserted at that position."""
        self.pages_ctl.insert_files(tab, [p for p in paths if os.path.isfile(p)], target)

    def selected_pages(self) -> list[int]:
        """Pages selected in the thumbnail strip, or the current page."""
        tab = self.current_tab()
        if tab is None:
            return []
        pages = [p for p in self.thumbnails.selected_pages() if p < tab.doc.page_count]
        return pages or [tab.viewer.current_page]

    def _thumbnail_menu(self, pos) -> None:
        if self.current_tab() is None:
            return
        index = self.thumbnails.indexAt(pos)
        if index.isValid() and index.row() not in self.thumbnails.selected_pages():
            self.thumbnails.setCurrentIndex(index)
        menus.build_context_menu(self, menus.THUMBNAIL_MENU).exec(self.thumbnails.viewport().mapToGlobal(pos))

    def create_signature(self) -> bool:
        """Open the signature creator; True if a signature is now available."""
        return self.content_ctl.new_signature()

    def selection_menu_actions(self) -> list[QAction]:
        """Extra actions for the selected-text context menu."""
        keys = ["annot.highlight_selection", "annot.underline_selection", "annot.strikeout_selection"]
        return [self.actions[k] for k in keys if k in self.actions]
