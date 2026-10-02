"""Keyboard shortcut reference (Ctrl+/), generated from the action table."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ..actions import ACTIONS, shortcut_text

EXTRA_SHORTCUTS = [
    ("Viewer", "Zoom with the mouse wheel", "Ctrl + Wheel"),
    ("Viewer", "Previous / next page (single-page mode)", "Page Up / Page Down"),
    ("Viewer", "Cancel the current operation or deselect", "Esc"),
    ("Viewer", "Delete the selected annotation", "Delete"),
    ("Viewer", "Nudge the selected annotation", "Arrow keys (Shift = 10 pt)"),
    ("Search", "Next / previous match in the search box", "Enter / Shift+Enter"),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.resize(560, 620)
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText("Filter…")
        self.filter.textChanged.connect(self._apply_filter)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Command", "Shortcut"])
        self.tree.setRootIsDecorated(True)
        groups: dict[str, QTreeWidgetItem] = {}

        def group(name: str) -> QTreeWidgetItem:
            if name not in groups:
                groups[name] = QTreeWidgetItem([name])
                self.tree.addTopLevelItem(groups[name])
            return groups[name]

        for spec in ACTIONS:
            keys = shortcut_text(spec)
            if keys:
                group(spec.category).addChild(QTreeWidgetItem([spec.text.replace("&", "").rstrip("…"), keys]))
        for category, text, keys in EXTRA_SHORTCUTS:
            group(category).addChild(QTreeWidgetItem([text, keys]))
        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.filter)
        layout.addWidget(self.tree)
        layout.addWidget(buttons)

    def _apply_filter(self, text: str) -> None:
        needle = text.lower().strip()
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            visible = 0
            for j in range(group.childCount()):
                child = group.child(j)
                match = not needle or needle in child.text(0).lower() or needle in child.text(1).lower()
                child.setHidden(not match)
                visible += match
            group.setHidden(visible == 0)
