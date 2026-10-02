"""Undo/redo commands and a memory-capped history.

This module is GUI-free. The desktop app wraps :class:`Command` objects in
``QUndoCommand`` adapters (see ``app/undo.py``) so they live on a
``QUndoStack``; :class:`UndoHistory` is a pure-Python stack with identical
semantics used for headless use and tests.

Commands follow a *perform once, then undo/redo* protocol:

* :meth:`Command.perform` runs the edit for the first time. If it raises,
  the command restores the previous state and is never pushed.
* :meth:`Command.undo` / :meth:`Command.redo` swap between the recorded
  before/after states.

:class:`StateCommand` implements this generically on top of a pair of
``capture()``/``restore()`` callables. The document layer supplies two kinds:
object-level captures (only the PDF objects an edit touches - the "minimal
state") and whole-document snapshots for edits that are hard to invert.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Generic, Protocol, Sequence, TypeVar

State = TypeVar("State")

DEFAULT_MEMORY_LIMIT = 256 * 1024 * 1024
DEFAULT_MAX_STEPS = 200


class Command(ABC):
    """A reversible document edit."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.expired = False

    @abstractmethod
    def perform(self) -> Any:
        """Execute the edit for the first time and return its result."""

    @abstractmethod
    def undo(self) -> None:
        """Revert the edit."""

    @abstractmethod
    def redo(self) -> None:
        """Re-apply the edit after an undo."""

    def memory_bytes(self) -> int:
        """Approximate number of bytes held to make this command reversible."""
        return 0

    def release(self) -> None:
        """Drop held state; the command can no longer be undone or redone."""
        self.expired = True


class CallbackCommand(Command):
    """A command whose inverse is an explicit function (e.g. rotate back)."""

    def __init__(
        self,
        label: str,
        do: Callable[[], Any],
        undo: Callable[[], None],
        *,
        after: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(label)
        self._do = do
        self._undo = undo
        self._after = after or (lambda: None)

    def perform(self) -> Any:
        result = self._do()
        self._after()
        return result

    def undo(self) -> None:
        if not self.expired:
            self._undo()
            self._after()

    def redo(self) -> None:
        if not self.expired:
            self._do()
            self._after()


class StateCommand(Command, Generic[State]):
    """A command that records state before/after an action and swaps it.

    Exactly one state is held at any time: the "before" state while the
    command is applied, and the "after" state while it is undone.
    """

    def __init__(
        self,
        label: str,
        action: Callable[[], Any],
        capture: Callable[[], State],
        restore: Callable[[State], None],
        size_of: Callable[[State], int],
        *,
        after: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(label)
        self._action = action
        self._capture = capture
        self._restore = restore
        self._size_of = size_of
        self._after = after or (lambda: None)
        self._state: State | None = None

    def perform(self) -> Any:
        before = self._capture()
        try:
            result = self._action()
        except BaseException:
            self._restore(before)
            self._after()
            raise
        self._state = before
        self._action = _performed  # never run twice; drop references held by the closure
        self._after()
        return result

    def _swap(self) -> None:
        if self.expired or self._state is None:
            return
        current = self._capture()
        self._restore(self._state)
        self._state = current
        self._after()

    def undo(self) -> None:
        self._swap()

    def redo(self) -> None:
        self._swap()

    def memory_bytes(self) -> int:
        return 0 if self._state is None else self._size_of(self._state)

    def release(self) -> None:
        super().release()
        self._state = None


def _performed() -> None:  # pragma: no cover - placeholder, never called
    raise RuntimeError("command already performed")


class HistoryBackend(Protocol):
    """What :class:`~pdf_editor.core.document.PdfDocument` needs from a history."""

    def push(self, command: Command) -> list[Command]:
        """Record an already-performed command; return commands that expired."""

    def clear(self) -> None:
        """Forget all commands."""

    def mark_clean(self) -> None:
        """Remember the current position as the saved state."""

    def is_clean(self) -> bool:
        """True if the document is at the saved state."""


def expire_for_budget(
    commands: Sequence[Command],
    index: int,
    memory_limit: int = DEFAULT_MEMORY_LIMIT,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> list[Command]:
    """Expire the oldest undoable commands until the history fits its budget.

    ``commands[:index]`` are undoable, ``commands[index:]`` are redoable.
    Expiry always removes a *prefix* of the undoable commands so the history
    stays consistent: you can never undo past an expired command.
    Returns the commands newly expired, oldest first.
    """
    live = [c for c in commands[:index] if not c.expired]
    total = sum(c.memory_bytes() for c in commands if not c.expired)
    expired: list[Command] = []
    while live and (total > memory_limit or len(live) > max_steps):
        oldest = live.pop(0)
        total -= oldest.memory_bytes()
        oldest.release()
        expired.append(oldest)
    if expired:
        # Everything older than the newest expired command is unreachable too.
        cutoff = commands.index(expired[-1])
        for cmd in commands[:cutoff]:
            if not cmd.expired:
                cmd.release()
                expired.append(cmd)
    return expired


class UndoHistory:
    """A linear undo/redo stack with a memory cap (GUI-free reference version)."""

    def __init__(self, memory_limit: int = DEFAULT_MEMORY_LIMIT, max_steps: int = DEFAULT_MAX_STEPS) -> None:
        self.memory_limit = memory_limit
        self.max_steps = max_steps
        self._commands: list[Command] = []
        self._index = 0
        self._clean_index: int | None = 0

    # -- HistoryBackend -------------------------------------------------
    def push(self, command: Command) -> list[Command]:
        for dropped in self._commands[self._index :]:
            dropped.release()
        if self._clean_index is not None and self._clean_index > self._index:
            self._clean_index = None  # the saved state can no longer be reached
        del self._commands[self._index :]
        self._commands.append(command)
        self._index += 1
        return expire_for_budget(self._commands, self._index, self.memory_limit, self.max_steps)

    def clear(self) -> None:
        for cmd in self._commands:
            cmd.release()
        self._commands.clear()
        self._index = 0
        self._clean_index = 0

    def mark_clean(self) -> None:
        self._clean_index = self._index

    def is_clean(self) -> bool:
        return self._clean_index == self._index

    # -- navigation -----------------------------------------------------
    @property
    def can_undo(self) -> bool:
        return self._index > 0 and not self._commands[self._index - 1].expired

    @property
    def can_redo(self) -> bool:
        return self._index < len(self._commands) and not self._commands[self._index].expired

    @property
    def undo_label(self) -> str | None:
        return self._commands[self._index - 1].label if self.can_undo else None

    @property
    def redo_label(self) -> str | None:
        return self._commands[self._index].label if self.can_redo else None

    def undo(self) -> bool:
        """Undo one step; returns False if nothing could be undone."""
        if not self.can_undo:
            return False
        self._index -= 1
        self._commands[self._index].undo()
        return True

    def redo(self) -> bool:
        """Redo one step; returns False if nothing could be redone."""
        if not self.can_redo:
            return False
        self._commands[self._index].redo()
        self._index += 1
        return True

    def memory_bytes(self) -> int:
        """Total bytes held by live commands."""
        return sum(c.memory_bytes() for c in self._commands if not c.expired)

    def __len__(self) -> int:
        return len(self._commands)
