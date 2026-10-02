"""Comment menu: properties/delete of the selected annotation, markup of selected text."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject

from ..errors import guarded

if TYPE_CHECKING:  # pragma: no cover
    from ..main_window import MainWindow


class AnnotController(QObject):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.w = window

    def _selected(self):
        tab = self.w.current_tab()
        if tab is None:
            return None, None
        tool = tab.tool("select")
        return tab, tool.selected

    def properties(self) -> None:
        tab, selected = self._selected()
        if tab is not None and selected is not None:
            tab.edit_annotation(*selected, properties=True)
        elif tab is not None:
            self.w.statusBar().showMessage("Select an annotation first (Select tool, click it).", 4000)

    def delete(self) -> None:
        tab, selected = self._selected()
        if tab is not None and selected is not None:
            tab.tool("select").delete_selected()

    def _markup_selection(self, kind: str) -> None:
        tab = self.w.current_tab()
        if tab is None:
            return
        selector = tab.text_selector
        if not selector.has_selection or selector.page is None:
            self.w.statusBar().showMessage("Select some text first.", 4000)
            return
        options = self.w.tool_options
        color = options.highlight_rgb() if kind == "highlight" else options.stroke_rgb()
        with guarded(self.w, "Cannot add markup"):
            tab.doc.add_text_markup(selector.page, kind, selector.selection.quads, color, options.opacity,
                                    options.author or None, selector.selection.text)
            selector.clear()

    def highlight_selection(self) -> None:
        self._markup_selection("highlight")

    def underline_selection(self) -> None:
        self._markup_selection("underline")

    def strikeout_selection(self) -> None:
        self._markup_selection("strikeout")
