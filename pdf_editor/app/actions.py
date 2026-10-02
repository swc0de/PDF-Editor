"""Declarative table of all menu/toolbar actions and their shortcuts.

Menus, toolbars and the keyboard-shortcut help dialog are all generated
from :data:`ACTIONS`, so a shortcut is defined in exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QAction, QActionGroup, QKeySequence

SK = QKeySequence.StandardKey


@dataclass(frozen=True)
class ActionSpec:
    key: str
    text: str
    handler: str  # "controller.method"
    shortcut: str | QKeySequence.StandardKey | tuple = ""
    glyph: str = ""
    tip: str = ""
    checkable: bool = False
    group: str = ""  # exclusive action group name
    category: str = "General"


ACTIONS: list[ActionSpec] = [
    # -- File
    ActionSpec("file.new", "&New Blank Document", "file.new_document", SK.New, "🗋", category="File"),
    ActionSpec("file.open", "&Open…", "file.open_dialog", SK.Open, "📂", "Open a PDF", category="File"),
    ActionSpec("file.save", "&Save", "file.save", SK.Save, "💾", "Save the document", category="File"),
    ActionSpec("file.save_as", "Save &As…", "file.save_as", SK.SaveAs, category="File"),
    ActionSpec("file.close", "&Close", "file.close_current", SK.Close, category="File"),
    ActionSpec("file.close_all", "Close A&ll", "file.close_all", "Ctrl+Shift+W", category="File"),
    ActionSpec("file.print", "&Print…", "file.print_document", SK.Print, "🖶", category="File"),
    ActionSpec("file.properties", "Document P&roperties…", "tools.edit_metadata", "Ctrl+D", category="File"),
    ActionSpec("file.quit", "E&xit", "file.quit", SK.Quit, category="File"),
    # -- Edit
    ActionSpec("edit.undo", "&Undo", "edit.undo", SK.Undo, "↶", category="Edit"),
    ActionSpec("edit.redo", "&Redo", "edit.redo", ("Ctrl+Y", "Ctrl+Shift+Z"), "↷", category="Edit"),
    ActionSpec("edit.copy", "&Copy", "edit.copy", SK.Copy, category="Edit"),
    ActionSpec("edit.select_all", "Select &All Text on Page", "edit.select_all", SK.SelectAll, category="Edit"),
    ActionSpec("edit.find", "&Find…", "edit.find", SK.Find, "🔍", category="Edit"),
    ActionSpec("edit.find_next", "Find &Next", "edit.find_next", ("F3",), category="Edit"),
    ActionSpec("edit.find_previous", "Find Pre&vious", "edit.find_previous", ("Shift+F3",), category="Edit"),
    ActionSpec("edit.settings", "Se&ttings…", "edit.settings", "Ctrl+,", "⚙", category="Edit"),
    # -- View
    ActionSpec("view.zoom_in", "Zoom &In", "view.zoom_in", ("Ctrl++", "Ctrl+="), "＋", category="View"),
    ActionSpec("view.zoom_out", "Zoom &Out", "view.zoom_out", "Ctrl+-", "－", category="View"),
    ActionSpec("view.actual_size", "&Actual Size", "view.actual_size", "Ctrl+0", category="View"),
    ActionSpec("view.fit_width", "Fit &Width", "view.fit_width", "Ctrl+2", "↔", category="View"),
    ActionSpec("view.fit_page", "Fit &Page", "view.fit_page", "Ctrl+1", "⤢", category="View"),
    ActionSpec("view.continuous", "&Continuous Scroll", "view.set_continuous", "Ctrl+Shift+C", checkable=True, category="View"),
    ActionSpec("view.invert", "&Invert Page Colors (Night Reading)", "view.toggle_invert", "Ctrl+I", checkable=True, category="View"),
    ActionSpec("view.theme_light", "&Light Theme", "view.theme_light", checkable=True, group="theme", category="View"),
    ActionSpec("view.theme_dark", "&Dark Theme", "view.theme_dark", checkable=True, group="theme", category="View"),
    ActionSpec("view.theme_system", "&System Theme", "view.theme_system", checkable=True, group="theme", category="View"),
    ActionSpec("view.next_page", "&Next Page", "view.next_page", ("Ctrl+PgDown",), "›", category="Navigation"),
    ActionSpec("view.prev_page", "&Previous Page", "view.prev_page", ("Ctrl+PgUp",), "‹", category="Navigation"),
    ActionSpec("view.first_page", "&First Page", "view.first_page", ("Ctrl+Home",), category="Navigation"),
    ActionSpec("view.last_page", "&Last Page", "view.last_page", ("Ctrl+End",), category="Navigation"),
    ActionSpec("view.goto_page", "&Go to Page…", "view.goto_page", "Ctrl+G", category="Navigation"),
    ActionSpec("view.panel_thumbnails", "&Thumbnails", "view.toggle_thumbnails", "F4", checkable=True, category="View"),
    ActionSpec("view.panel_outline", "&Bookmarks", "view.toggle_outline", "F5", checkable=True, category="View"),
    ActionSpec("view.panel_annotations", "&Annotations", "view.toggle_annotations", "F6", checkable=True, category="View"),
    ActionSpec("view.next_tab", "Next &Tab", "view.next_tab", ("Ctrl+Tab",), category="Navigation"),
    ActionSpec("view.prev_tab", "Previous Ta&b", "view.prev_tab", ("Ctrl+Shift+Tab",), category="Navigation"),
    # -- Pages
    ActionSpec("pages.rotate_left", "Rotate &Left", "pages.rotate_left", "Ctrl+Shift+L", "⟲", "Rotate selected pages counter-clockwise", category="Pages"),
    ActionSpec("pages.rotate_right", "Rotate &Right", "pages.rotate_right", "Ctrl+Shift+R", "⟳", "Rotate selected pages clockwise", category="Pages"),
    ActionSpec("pages.rotate_180", "Rotate 18&0°", "pages.rotate_180", category="Pages"),
    ActionSpec("pages.delete", "&Delete Pages", "pages.delete_pages", "Shift+Del", "🗑", "Delete selected pages", category="Pages"),
    ActionSpec("pages.duplicate", "D&uplicate Pages", "pages.duplicate_pages", "Ctrl+Shift+D", category="Pages"),
    ActionSpec("pages.insert_blank", "Insert &Blank Page", "pages.insert_blank", "Ctrl+Shift+B", category="Pages"),
    ActionSpec("pages.insert_file", "&Insert Pages from File…", "pages.insert_from_file", "Ctrl+Shift+I", category="Pages"),
    ActionSpec("pages.extract", "&Extract Pages…", "pages.extract_pages", "Ctrl+Shift+E", category="Pages"),
    ActionSpec("pages.split", "&Split Document…", "pages.split", category="Pages"),
    ActionSpec("pages.merge", "&Merge PDFs…", "pages.merge", "Ctrl+Shift+M", "⊕", category="Pages"),
    ActionSpec("pages.crop", "Cro&p Pages…", "pages.crop", "Ctrl+Shift+K", category="Pages"),
    # -- Tools (interactive)
    ActionSpec("tool.select", "&Select", "tool.select", "V", "⌶", "Select text, annotations and form fields", True, "tool", "Tools"),
    ActionSpec("tool.hand", "&Hand", "tool.hand", "H", "✋", "Scroll by dragging", True, "tool", "Tools"),
    ActionSpec("tool.crop", "&Crop Tool", "tool.crop", "C", "⛶", "Draw the area of the page to keep", True, "tool", "Tools"),
    # -- Help
    ActionSpec("help.shortcuts", "&Keyboard Shortcuts", "help.shortcuts", "Ctrl+/", category="Help"),
    ActionSpec("help.about", "&About PDF Editor", "help.about", category="Help"),
    ActionSpec("help.log", "Open &Log Folder", "help.open_log_folder", category="Help"),
]

SPECS: dict[str, ActionSpec] = {spec.key: spec for spec in ACTIONS}


def _sequences(shortcut) -> list[QKeySequence]:
    if not shortcut:
        return []
    if isinstance(shortcut, tuple):
        return [QKeySequence(s) for s in shortcut]
    if isinstance(shortcut, QKeySequence.StandardKey):
        return QKeySequence.keyBindings(shortcut)
    return [QKeySequence(shortcut)]


def shortcut_text(spec: ActionSpec) -> str:
    """Human-readable shortcut(s) for the help dialog."""
    return ", ".join(s.toString(QKeySequence.SequenceFormat.NativeText) for s in _sequences(spec.shortcut))


def create_actions(parent, resolve) -> dict[str, QAction]:
    """Create a QAction per spec; ``resolve("controller.method")`` returns the slot."""
    from .qt_utils import glyph_icon

    actions: dict[str, QAction] = {}
    groups: dict[str, QActionGroup] = {}
    for spec in ACTIONS:
        action = QAction(spec.text, parent)
        sequences = _sequences(spec.shortcut)
        if sequences:
            action.setShortcuts(sequences)
        if spec.glyph:
            action.setIcon(glyph_icon(spec.glyph))
        tip = spec.tip or spec.text.replace("&", "").rstrip("…")
        if sequences:
            tip += f" ({sequences[0].toString(QKeySequence.SequenceFormat.NativeText)})"
        action.setToolTip(tip)
        action.setStatusTip(spec.tip or tip)
        action.setCheckable(spec.checkable)
        if spec.group:
            groups.setdefault(spec.group, QActionGroup(parent)).addAction(action)
        slot = resolve(spec.handler)
        if spec.checkable and not spec.group:
            action.toggled.connect(slot)
        else:
            action.triggered.connect(lambda _checked=False, s=slot: s())
        parent.addAction(action)  # shortcuts work even when menus are hidden
        actions[spec.key] = action
    return actions
