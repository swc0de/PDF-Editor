"""Menu bar and toolbar layout (built from the action table)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QMenu, QSizePolicy, QToolBar, QWidget

if TYPE_CHECKING:  # pragma: no cover
    from .main_window import MainWindow

# "-" is a separator, "@name" a dynamic submenu filled by the window.
MENUS: list[tuple[str, list[str]]] = [
    ("&File", [
        "file.new", "file.open", "@recent", "-", "file.save", "file.save_as", "-",
        "@export", "-", "file.print", "file.properties", "-", "file.close", "file.close_all", "-", "file.quit",
    ]),
    ("&Edit", [
        "edit.undo", "edit.redo", "-", "edit.copy", "edit.select_all", "-",
        "edit.find", "edit.find_next", "edit.find_previous", "-", "edit.settings",
    ]),
    ("&View", [
        "view.zoom_in", "view.zoom_out", "view.actual_size", "view.fit_width", "view.fit_page", "-",
        "view.continuous", "view.invert", "-", "@theme", "-",
        "view.panel_thumbnails", "view.panel_outline", "view.panel_annotations",
    ]),
    ("&Go", [
        "view.first_page", "view.prev_page", "view.next_page", "view.last_page", "view.goto_page", "-",
        "view.prev_tab", "view.next_tab",
    ]),
    ("&Pages", ["@pages"]),
    ("&Comment", ["@annotate"]),
    ("E&dit Content", ["@content"]),
    ("&Tools", ["@tools"]),
    ("&Help", ["help.shortcuts", "help.log", "-", "help.about"]),
]

SUBMENUS: dict[str, tuple[str, list[str]]] = {
    "theme": ("&Theme", ["view.theme_light", "view.theme_dark", "view.theme_system"]),
}

# Optional menu sections contributed by feature controllers (key -> action keys).
SECTIONS: dict[str, list[str]] = {
    "pages": [
        "pages.rotate_left", "pages.rotate_right", "pages.rotate_180", "-",
        "pages.insert_blank", "pages.insert_file", "pages.duplicate", "pages.delete", "-",
        "pages.extract", "pages.split", "pages.merge", "-", "pages.crop", "tool.crop",
    ],
}

SECTIONS["annotate"] = [
    "tool.highlight", "tool.underline", "tool.strikeout", "-",
    "annot.highlight_selection", "annot.underline_selection", "annot.strikeout_selection", "-",
    "tool.pen", "tool.rectangle", "tool.ellipse", "tool.line", "tool.arrow", "-",
    "tool.note", "tool.textbox", "tool.stamp", "-", "annot.properties", "annot.delete",
]

SECTIONS["content"] = [
    "tool.text_add", "tool.text_edit", "tool.image", "-", "tool.signature", "content.new_signature", "-",
    "content.watermark", "content.header_footer", "content.page_numbers", "-", "content.flatten",
]

# Context menu of the thumbnail strip.
THUMBNAIL_MENU = [
    "pages.rotate_left", "pages.rotate_right", "-", "pages.insert_blank", "pages.insert_file",
    "pages.duplicate", "pages.delete", "-", "pages.extract", "pages.crop",
]

MAIN_TOOLBAR = ["file.open", "file.save", "file.print", "-", "edit.undo", "edit.redo", "-",
                "view.zoom_out", "@zoom", "view.zoom_in", "view.fit_width", "view.fit_page", "-",
                "view.prev_page", "@page", "view.next_page"]
TOOLS_TOOLBAR = [
    "tool.select", "tool.hand", "-", "tool.highlight", "tool.underline", "tool.strikeout", "-",
    "tool.pen", "tool.rectangle", "tool.ellipse", "tool.line", "tool.arrow", "-",
    "tool.note", "tool.textbox", "tool.stamp", "-", "tool.text_add", "tool.text_edit", "tool.image",
    "tool.signature", "-", "pages.rotate_left", "pages.rotate_right", "tool.crop",
]


def _fill(window: "MainWindow", menu: QMenu, keys: list[str]) -> None:
    for key in keys:
        if key == "-":
            menu.addSeparator()
        elif key == "@recent":
            window.recent_menu = menu.addMenu("Open &Recent")
        elif key.startswith("@"):
            name = key[1:]
            if name in SUBMENUS:
                title, items = SUBMENUS[name]
                _fill(window, menu.addMenu(title), items)
            elif name in SECTIONS:
                _fill(window, menu, SECTIONS[name])
        elif key in window.actions:
            menu.addAction(window.actions[key])


def build_context_menu(window: "MainWindow", keys: list[str]) -> QMenu:
    menu = QMenu(window)
    _fill(window, menu, keys)
    return menu


def build_menus(window: "MainWindow") -> None:
    bar = window.menuBar()
    for title, keys in MENUS:
        menu = bar.addMenu(title)
        _fill(window, menu, keys)
        if menu.isEmpty():
            menu.menuAction().setVisible(False)


def _toolbar(window: "MainWindow", name: str, title: str, keys: list[str]) -> QToolBar:
    bar = QToolBar(title, window)
    bar.setObjectName(name)
    bar.setIconSize(QSize(20, 20))
    bar.setMovable(True)
    for key in keys:
        if key == "-":
            bar.addSeparator()
        elif key == "@zoom":
            bar.addWidget(window.zoom_box)
        elif key == "@page":
            bar.addWidget(window.page_box)
        elif key == "@search":
            bar.addWidget(window.search_bar)
        elif key in window.actions:
            bar.addAction(window.actions[key])
    return bar


def build_toolbars(window: "MainWindow") -> None:
    main = _toolbar(window, "mainToolbar", "Main", MAIN_TOOLBAR)
    spacer = QWidget(main)
    spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    main.addWidget(spacer)
    main.addWidget(window.search_bar)
    window.addToolBar(Qt.ToolBarArea.TopToolBarArea, main)
    window.addToolBarBreak()
    tools = _toolbar(window, "toolsToolbar", "Tools", TOOLS_TOOLBAR)
    tools.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    window.addToolBar(Qt.ToolBarArea.TopToolBarArea, tools)
    window.tools_toolbar = tools
    window.addToolBar(Qt.ToolBarArea.TopToolBarArea, window.options_bar)
