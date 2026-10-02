"""The Select tool: select/move/resize/delete annotations, otherwise select text."""

from __future__ import annotations

import pymupdf
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QCursor, QKeyEvent, QKeySequence
from PySide6.QtWidgets import QMenu

from ...core.operations import annotate as annot_ops
from ..annotation_overlay import CURSORS, AnnotationSelectionItem, resized
from ..errors import guarded
from .base import PageEvent
from .text_select import TextSelectTool

FIXED_SIZE_KINDS = {"Text", "FileAttachment", "Sound"}  # icons: move only
TEXT_KINDS = {"Text", "FreeText"}


class SelectTool(TextSelectTool):
    """Click an annotation to select it; drag to move, drag handles to resize."""

    name = "select"
    label = "Select"
    tooltip = "Select text and annotations; move, resize and delete annotations"
    cursor = Qt.CursorShape.ArrowCursor

    def __init__(self, tab) -> None:
        super().__init__(tab)
        self.selected: tuple[int, int] | None = None  # (page, xref)
        self.selected_kind = ""
        self._overlay: AnnotationSelectionItem | None = None
        self._drag: tuple[str, QPointF, QRectF] | None = None  # handle, start point, start rect
        self._text_drag = False

    # -- selection management ------------------------------------------------------
    def select_annotation(self, pno: int, xref: int, scroll: bool = False) -> None:
        self.clear_annotation()
        info = self.doc.annotation_info(pno, xref)
        if info is None:
            return
        self.selected, self.selected_kind = (pno, xref), info.kind
        visual = self.viewer.page_rect_to_visual(pno, info.rect)
        self._overlay = AnnotationSelectionItem(visual, info.kind not in FIXED_SIZE_KINDS, self.viewer.item(pno))
        self._overlay.scale_hint = self.viewer.transform().m11()
        if scroll:
            self.viewer.scroll_to_page_rect(pno, info.rect)
        self.tab.annotation_selected(pno, xref)

    def clear_annotation(self) -> None:
        if self._overlay is not None and self._overlay.scene() is not None:
            self._overlay.scene().removeItem(self._overlay)
        had = self.selected is not None
        self._overlay, self.selected, self._drag = None, None, None
        if had:
            self.tab.annotation_selected(None, None)

    def document_changed(self) -> None:
        super().document_changed()
        if self.selected is None:
            return
        pno, xref = self.selected
        if pno < self.doc.page_count and self.doc.annotation_info(pno, xref) is not None:
            self.select_annotation(pno, xref)  # refresh the outline after undo/redo
        else:
            self.clear_annotation()

    # -- mouse -------------------------------------------------------------------------
    def press(self, event: PageEvent) -> bool:
        if self._overlay is not None and self.selected and self.selected[0] == event.pno:
            self._overlay.scale_hint = self.viewer.transform().m11()
            handle = self._overlay.hit_test(event.visual)
            if handle is not None:
                self._drag = (handle, QPointF(event.visual), self._overlay.rect)
                return True
        if self.tab.handle_widget_click(event):
            self.clear_annotation()
            return True
        xref = annot_ops.annot_at(self.doc.raw[event.pno], event.point)
        if xref is not None:
            self.selector.clear()
            self.select_annotation(event.pno, xref)
            assert self._overlay is not None
            self._drag = ("move", QPointF(event.visual), self._overlay.rect)
            return True
        self.clear_annotation()
        self._text_drag = True
        return super().press(event)

    def move(self, event: PageEvent) -> bool:
        if self._drag is not None and self._overlay is not None:
            handle, start, rect = self._drag
            if handle != "move" and self.selected_kind in FIXED_SIZE_KINDS:
                handle = "move"
            keep = event.shift or self.selected_kind == "Stamp"
            self._overlay.set_rect(resized(rect, handle, event.visual - start, keep_aspect=keep))
            return True
        return super().move(event) if self._text_drag else False

    def release(self, event: PageEvent) -> bool:
        if self._drag is not None and self._overlay is not None and self.selected is not None:
            _, _, start_rect = self._drag
            self._drag = None
            new = self._overlay.rect
            if (abs(new.left() - start_rect.left()) + abs(new.top() - start_rect.top())
                    + abs(new.width() - start_rect.width()) + abs(new.height() - start_rect.height())) > 0.5:
                pno, xref = self.selected
                label = "Move annotation" if new.size() == start_rect.size() else "Resize annotation"
                with guarded(self.tab, "Cannot move annotation"):
                    self.doc.set_annotation_rect(pno, xref, self.viewer.visual_rect_to_page(pno, new), label)
            return True
        if self._text_drag:
            self._text_drag = False
            return super().release(event)
        return False

    def double_click(self, event: PageEvent) -> bool:
        xref = annot_ops.annot_at(self.doc.raw[event.pno], event.point)
        if xref is not None:
            self.select_annotation(event.pno, xref)
            self.tab.edit_annotation(event.pno, xref)
            return True
        return super().double_click(event)

    def hover(self, event: PageEvent) -> None:
        if self._overlay is not None and self.selected and self.selected[0] == event.pno:
            handle = self._overlay.hit_test(event.visual)
            if handle is not None:
                if handle != "move" and self.selected_kind in FIXED_SIZE_KINDS:
                    handle = "move"
                self.viewer.viewport().setCursor(QCursor(CURSORS[handle]))
                return
        if self.tab.widget_at(event) is not None:
            self.viewer.viewport().setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            return
        if annot_ops.annot_at(self.doc.raw[event.pno], event.point) is not None:
            self.viewer.viewport().setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            return
        super().hover(event)

    # -- keyboard & menus ----------------------------------------------------------------
    def key_press(self, event: QKeyEvent) -> bool:
        if self.selected is not None:
            pno, xref = self.selected
            key = event.key()
            if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.delete_selected()
                return True
            if key == Qt.Key.Key_Escape:
                self.clear_annotation()
                return True
            steps = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
            if key in steps:
                step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
                visual = self._overlay.rect.translated(steps[key][0] * step, steps[key][1] * step)
                with guarded(self.tab):
                    self.doc.set_annotation_rect(pno, xref, self.viewer.visual_rect_to_page(pno, visual))
                return True
            if event.matches(QKeySequence.StandardKey.Copy):
                return False
        return super().key_press(event)

    def delete_selected(self) -> None:
        if self.selected is None:
            return
        pno, xref = self.selected
        self.clear_annotation()
        with guarded(self.tab, "Cannot delete annotation"):
            self.doc.delete_annotation(pno, xref)

    def context_menu(self, event: PageEvent) -> bool:
        xref = annot_ops.annot_at(self.doc.raw[event.pno], event.point)
        if xref is None:
            return super().context_menu(event)
        self.select_annotation(event.pno, xref)
        menu = QMenu(self.tab)
        menu.addAction("Properties…", lambda: self.tab.edit_annotation(event.pno, xref, properties=True))
        if self.selected_kind in TEXT_KINDS:
            menu.addAction("Edit Text…", lambda: self.tab.edit_annotation(event.pno, xref))
        menu.addSeparator()
        menu.addAction("Delete", self.delete_selected)
        menu.exec(event.global_pos)
        return True

    def deactivate(self) -> None:
        self.clear_annotation()
        super().deactivate()

    def copy(self) -> bool:
        return self.selector.copy()
