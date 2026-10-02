"""View menu: zoom, page navigation, display modes, themes and panels."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from ..theme import apply_theme

if TYPE_CHECKING:  # pragma: no cover
    from ..main_window import MainWindow


class ViewController(QObject):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.w = window

    def _viewer(self):
        tab = self.w.current_tab()
        return tab.viewer if tab is not None else None

    # -- zoom -----------------------------------------------------------------
    def zoom_in(self) -> None:
        if (v := self._viewer()) is not None:
            v.zoom_in()

    def zoom_out(self) -> None:
        if (v := self._viewer()) is not None:
            v.zoom_out()

    def actual_size(self) -> None:
        if (v := self._viewer()) is not None:
            v.set_zoom(1.0)

    def fit_width(self) -> None:
        if (v := self._viewer()) is not None:
            v.fit_width()

    def fit_page(self) -> None:
        if (v := self._viewer()) is not None:
            v.fit_page()

    def apply_zoom_request(self, value) -> None:
        """Handle a choice from the zoom combo box."""
        v = self._viewer()
        if v is None:
            return
        if value == "fit-width":
            v.fit_width()
        elif value == "fit-page":
            v.fit_page()
        else:
            v.set_zoom(float(value))

    # -- modes ----------------------------------------------------------------
    def set_continuous(self, checked: bool) -> None:
        self.w.settings.continuous_scroll = checked
        for tab in self.w.tabs_list():
            tab.viewer.set_continuous(checked)

    def toggle_invert(self, checked: bool) -> None:
        self.w.settings.invert_pages = checked
        for tab in self.w.tabs_list():
            tab.viewer.set_invert(checked)

    def _theme(self, name: str) -> None:
        self.w.settings.theme = name
        self.w.effective_theme = apply_theme(QApplication.instance(), name)
        self.w.on_theme_changed()

    def theme_light(self) -> None:
        self._theme("light")

    def theme_dark(self) -> None:
        self._theme("dark")

    def theme_system(self) -> None:
        self._theme("system")

    # -- navigation -------------------------------------------------------------
    def next_page(self) -> None:
        if (v := self._viewer()) is not None:
            v.next_page()

    def prev_page(self) -> None:
        if (v := self._viewer()) is not None:
            v.previous_page()

    def first_page(self) -> None:
        if (v := self._viewer()) is not None:
            v.go_to_page(0)

    def last_page(self) -> None:
        if (v := self._viewer()) is not None:
            v.go_to_page(v.page_count - 1)

    def goto_page(self) -> None:
        self.w.page_box.focus()

    def next_tab(self) -> None:
        count = self.w.tabs.count()
        if count:
            self.w.tabs.setCurrentIndex((self.w.tabs.currentIndex() + 1) % count)

    def prev_tab(self) -> None:
        count = self.w.tabs.count()
        if count:
            self.w.tabs.setCurrentIndex((self.w.tabs.currentIndex() - 1) % count)

    # -- panels -----------------------------------------------------------------
    def toggle_thumbnails(self) -> None:
        self.w.toggle_dock("thumbnails")

    def toggle_outline(self) -> None:
        self.w.toggle_dock("outline")

    def toggle_annotations(self) -> None:
        self.w.toggle_dock("annotations")
