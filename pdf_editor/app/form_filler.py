"""Fill form fields directly on the page: click to toggle, type in place, pick options."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGraphicsProxyWidget, QLineEdit, QMenu, QPlainTextEdit

from ..core.operations.forms import FieldInfo
from .errors import guarded


class _Editor(QObject):
    """Commits on Enter / focus loss, cancels on Escape."""

    def __init__(self, filler: "FormFiller", widget, field: FieldInfo) -> None:
        super().__init__(widget)
        self.filler, self.widget, self.field = filler, widget, field
        self.done = False
        widget.installEventFilter(self)

    def text(self) -> str:
        return self.widget.toPlainText() if isinstance(self.widget, QPlainTextEdit) else self.widget.text()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.finish(commit=False)
                return True
            multiline = isinstance(self.widget, QPlainTextEdit)
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
                not multiline or event.modifiers() & Qt.KeyboardModifier.ControlModifier
            ):
                self.finish(commit=True)
                return True
        elif event.type() == QEvent.Type.FocusOut:
            self.finish(commit=True)
        return False

    def finish(self, commit: bool) -> None:
        if self.done:
            return
        self.done = True
        value = self.text()
        self.filler.close_editor()
        if commit and value != (self.field.value or ""):
            self.filler.commit(self.field, value)


class FormFiller:
    """Handles clicks on form widgets for one document tab."""

    def __init__(self, tab) -> None:
        self.tab = tab
        self._proxy: QGraphicsProxyWidget | None = None

    def field_at(self, pno: int, point) -> FieldInfo | None:
        return self.tab.doc.field_at(pno, point)

    def click(self, pno: int, field: FieldInfo, global_pos) -> bool:
        if field.read_only or field.kind in ("button", "signature", "unknown"):
            self.tab.show_message(f"The field '{field.name}' cannot be filled here.")
            return True
        if field.kind == "checkbox":
            self.commit(field, not bool(field.value))
        elif field.kind == "radio":
            if not field.value:
                self.commit(field, True)
        elif field.kind in ("combobox", "listbox"):
            chosen = self.choose_option(field, global_pos)
            if chosen is not None and chosen != field.value:
                self.commit(field, chosen)
        elif field.kind == "text":
            self.open_editor(pno, field)
        return True

    def choose_option(self, field: FieldInfo, global_pos) -> str | None:
        """Pop up the field's choices next to the cursor; returns the chosen text."""
        menu = QMenu(self.tab)
        for option in field.options:
            action = menu.addAction(option)
            action.setCheckable(True)
            action.setChecked(option == field.value)
        chosen = menu.exec(global_pos)
        return chosen.text() if chosen is not None else None

    def open_editor(self, pno: int, field: FieldInfo) -> None:
        self.close_editor()
        viewer = self.tab.viewer
        visual: QRectF = viewer.page_rect_to_visual(pno, field.rect)
        widget = QPlainTextEdit() if field.multiline else QLineEdit()
        (widget.setPlainText if field.multiline else widget.setText)(str(field.value or ""))
        font = QFont()
        font.setPointSizeF(max(6.0, visual.height() * 0.55 if not field.multiline else 10.0))
        widget.setFont(font)
        widget.setStyleSheet("background: #fffbe0; border: 1px solid #2f6fdf;")
        proxy = QGraphicsProxyWidget(viewer.item(pno))
        proxy.setWidget(widget)
        proxy.setGeometry(visual)
        proxy.setZValue(40)
        self._proxy = proxy
        _Editor(self, widget, field)
        widget.setFocus()
        if isinstance(widget, QLineEdit):
            widget.selectAll()

    def close_editor(self) -> None:
        proxy, self._proxy = self._proxy, None
        if proxy is not None and proxy.scene() is not None:
            proxy.scene().removeItem(proxy)
            proxy.deleteLater()
        self.tab.viewer.setFocus()

    def commit(self, field: FieldInfo, value) -> None:
        with guarded(self.tab, "Cannot fill form field"):
            self.tab.doc.set_field_value(field.page, field.xref, value)
