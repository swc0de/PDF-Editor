"""Incremental document search with highlighted results and next/previous."""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QToolButton, QWidget

from ..core.operations import text as text_ops
from .qt_utils import glyph_icon

SLICE_SECONDS = 0.025  # search for at most this long per event-loop tick


class SearchController(QObject):
    """Searches one document page by page without blocking the UI."""

    resultsChanged = Signal()  # hit count / progress changed
    currentChanged = Signal()

    def __init__(self, tab) -> None:
        super().__init__(tab)
        self.tab = tab
        self.needle = ""
        self.match_case = False
        self._hits: dict[int, list[text_ops.TextSelection]] = {}
        self._ordered: list[tuple[int, int]] | None = []
        self._queue: list[int] = []
        self._searched = 0
        self._current: tuple[int, int] | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._step)

    # -- state ----------------------------------------------------------------
    @property
    def active(self) -> bool:
        return bool(self.needle)

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    @property
    def total(self) -> int:
        return sum(len(h) for h in self._hits.values())

    @property
    def progress(self) -> tuple[int, int]:
        return self._searched, self.tab.doc.page_count

    def ordered(self) -> list[tuple[int, int]]:
        if self._ordered is None:
            self._ordered = [(p, i) for p in sorted(self._hits) for i in range(len(self._hits[p]))]
        return self._ordered

    def current_index(self) -> int | None:
        if self._current is None:
            return None
        try:
            return self.ordered().index(self._current)
        except ValueError:
            return None

    # -- control --------------------------------------------------------------
    def start(self, needle: str, match_case: bool = False) -> None:
        """Begin a new search, starting at the current page and wrapping around."""
        self.clear(emit=False)
        self.needle, self.match_case = needle.strip(), match_case
        if not self.needle:
            self.resultsChanged.emit()
            return
        count = self.tab.doc.page_count
        start = self.tab.viewer.current_page
        self._queue = list(range(start, count)) + list(range(0, start))
        self._timer.start()
        self.resultsChanged.emit()

    def clear(self, emit: bool = True) -> None:
        self._timer.stop()
        self.needle = ""
        self._hits, self._ordered, self._queue = {}, [], []
        self._searched = 0
        self._current = None
        self.tab.viewer.clear_search_highlights()
        if emit:
            self.resultsChanged.emit()
            self.currentChanged.emit()

    def restart(self) -> None:
        """Re-run the current search (after the document changed)."""
        if self.needle:
            self.start(self.needle, self.match_case)

    def _step(self) -> None:
        deadline = time.monotonic() + SLICE_SECONDS
        doc = self.tab.doc
        while self._queue and time.monotonic() < deadline:
            pno = self._queue.pop(0)
            if pno >= doc.page_count:
                continue
            hits = text_ops.search_page(doc.raw[pno], self.needle, self.match_case)
            self._searched += 1
            if hits:
                self._hits[pno] = hits
                self._ordered = None
                self.tab.viewer.add_search_highlights(pno, [h.rects for h in hits])
                if self._current is None:
                    self._go((pno, 0))
        if not self._queue:
            self._timer.stop()
        self.resultsChanged.emit()

    def _go(self, target: tuple[int, int]) -> None:
        self._current = target
        pno, idx = target
        self.tab.viewer.set_current_hit(pno, self._hits[pno][idx].rects)
        self.currentChanged.emit()

    def next(self) -> None:
        self._step_by(1)

    def previous(self) -> None:
        self._step_by(-1)

    def _step_by(self, delta: int) -> None:
        ordered = self.ordered()
        if not ordered:
            return
        idx = self.current_index()
        if idx is None:
            page = self.tab.viewer.current_page
            idx = next((i for i, (p, _) in enumerate(ordered) if p >= page), 0) - (1 if delta > 0 else 0)
        self._go(ordered[(idx + delta) % len(ordered)])


class SearchBar(QWidget):
    """Find box with match-case toggle, previous/next buttons and a counter."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller: SearchController | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(2)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("Find in document (Ctrl+F)")
        self.edit.setClearButtonEnabled(True)
        self.edit.setMinimumWidth(180)
        self.edit.returnPressed.connect(self._on_return)
        self.edit.textChanged.connect(self._on_text_changed)
        self.edit.installEventFilter(self)
        self.case = QToolButton(self)
        self.case.setText("Aa")
        self.case.setCheckable(True)
        self.case.setToolTip("Match case")
        self.case.toggled.connect(lambda _c: self._search_now())
        self.prev = QToolButton(self)
        self.prev.setIcon(glyph_icon("▲"))
        self.prev.setToolTip("Previous match (Shift+F3)")
        self.prev.clicked.connect(self.find_previous)
        self.next = QToolButton(self)
        self.next.setIcon(glyph_icon("▼"))
        self.next.setToolTip("Next match (F3)")
        self.next.clicked.connect(self.find_next)
        self.status = QLabel("", self)
        self.status.setMinimumWidth(70)
        for w in (self.edit, self.case, self.prev, self.next, self.status):
            layout.addWidget(w)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._search_now)

    def set_controller(self, controller: SearchController | None) -> None:
        if self.controller is not None:
            for sig in (self.controller.resultsChanged, self.controller.currentChanged):
                try:
                    sig.disconnect(self._update_status)
                except (RuntimeError, TypeError):
                    pass
        self.controller = controller
        if controller is not None:
            controller.resultsChanged.connect(self._update_status)
            controller.currentChanged.connect(self._update_status)
            self.edit.blockSignals(True)
            self.edit.setText(controller.needle)
            self.edit.blockSignals(False)
        self._update_status()

    def focus(self) -> None:
        self.edit.setFocus()
        self.edit.selectAll()

    def _on_text_changed(self, _text: str) -> None:
        self._debounce.start()

    def _search_now(self) -> None:
        self._debounce.stop()
        if self.controller is None:
            return
        text = self.edit.text()
        if text.strip() != self.controller.needle or self.case.isChecked() != self.controller.match_case:
            self.controller.start(text, self.case.isChecked())

    def _on_return(self) -> None:
        if self.controller is None:
            return
        if self._debounce.isActive() or self.edit.text().strip() != self.controller.needle:
            self._search_now()
        else:
            self.find_next()

    def find_next(self) -> None:
        if self.controller is not None:
            self._search_now()
            self.controller.next()

    def find_previous(self) -> None:
        if self.controller is not None:
            self._search_now()
            self.controller.previous()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.edit and isinstance(event, QKeyEvent) and event.type() == QKeyEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.edit.clear()
                if self.controller is not None:
                    self.controller.clear()
                    self.controller.tab.viewer.setFocus()
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.find_previous()
                return True
        return super().eventFilter(obj, event)

    def _update_status(self) -> None:
        c = self.controller
        if c is None or not c.active:
            self.status.setText("")
            return
        total = c.total
        idx = c.current_index()
        done, pages = c.progress
        running = " …" if c.running else ""
        if total == 0:
            self.status.setText("No matches" if not c.running else f"Searching {done}/{pages}")
        else:
            self.status.setText(f"{(idx + 1) if idx is not None else '-'} of {total}{running}")
