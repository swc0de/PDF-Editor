"""QUndoStack adapter implementing the core ``HistoryBackend`` protocol.

Each core :class:`~pdf_editor.core.history.Command` is wrapped in a
``QUndoCommand``. Commands are already performed when pushed, so the first
``redo()`` call that ``QUndoStack.push`` makes is skipped. A parallel list
of core commands lets us enforce the memory budget: expired commands stay
on the stack (Qt cannot drop the bottom of a stack) but undo stops there.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from ..core.history import DEFAULT_MAX_STEPS, Command, expire_for_budget

log = logging.getLogger(__name__)


class _QtCommand(QUndoCommand):
    def __init__(self, command: Command, on_error) -> None:
        super().__init__(command.label)
        self.command = command
        self._on_error = on_error
        self._skip_first_redo = True

    # Exceptions raised in these overrides would be swallowed by PySide
    # (they are called from C++), so they are caught and reported here.
    def redo(self) -> None:
        if self._skip_first_redo:
            self._skip_first_redo = False
            return
        try:
            self.command.redo()
        except Exception as exc:
            self._on_error(exc)

    def undo(self) -> None:
        try:
            self.command.undo()
        except Exception as exc:
            self._on_error(exc)


class QtHistory(QObject):
    """Undo history for one document, backed by a ``QUndoStack``."""

    changed = Signal()
    failed = Signal(object)  # exception raised while undoing/redoing

    def __init__(self, memory_limit: int, max_steps: int = DEFAULT_MAX_STEPS, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.memory_limit = memory_limit
        self.max_steps = max_steps
        self.stack = QUndoStack(self)
        self._commands: list[Command] = []
        self.stack.indexChanged.connect(lambda _i: self.changed.emit())
        self.stack.cleanChanged.connect(lambda _c: self.changed.emit())

    # -- HistoryBackend ---------------------------------------------------
    def push(self, command: Command) -> list[Command]:
        index = self.stack.index()
        for dropped in self._commands[index:]:
            dropped.release()
        del self._commands[index:]
        self._commands.append(command)
        self.stack.push(_QtCommand(command, self._report))
        expired = expire_for_budget(self._commands, self.stack.index(), self.memory_limit, self.max_steps)
        self.changed.emit()
        return expired

    def clear(self) -> None:
        for cmd in self._commands:
            cmd.release()
        self._commands.clear()
        self.stack.clear()
        self.changed.emit()

    def mark_clean(self) -> None:
        self.stack.setClean()

    def is_clean(self) -> bool:
        return self.stack.isClean()

    # -- navigation -------------------------------------------------------
    @property
    def can_undo(self) -> bool:
        i = self.stack.index()
        return i > 0 and i <= len(self._commands) and not self._commands[i - 1].expired

    @property
    def can_redo(self) -> bool:
        i = self.stack.index()
        return i < len(self._commands) and not self._commands[i].expired

    @property
    def undo_label(self) -> str:
        return self.stack.undoText() if self.can_undo else ""

    @property
    def redo_label(self) -> str:
        return self.stack.redoText() if self.can_redo else ""

    def undo(self) -> None:
        if self.can_undo:
            self.stack.undo()

    def redo(self) -> None:
        if self.can_redo:
            self.stack.redo()

    def _report(self, exc: Exception) -> None:
        log.exception("Undo/redo failed", exc_info=exc)
        self.failed.emit(exc)

    def memory_bytes(self) -> int:
        return sum(c.memory_bytes() for c in self._commands if not c.expired)
