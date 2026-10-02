"""Tests for the GUI-free undo/redo machinery."""

from __future__ import annotations

import pytest

from pdf_editor.core.history import CallbackCommand, StateCommand, UndoHistory, expire_for_budget


class Box:
    """A tiny mutable 'document' for exercising commands."""

    def __init__(self) -> None:
        self.value = 0


def state_cmd(box: Box, new_value: int, size: int = 10) -> StateCommand:
    def action():
        box.value = new_value
        return new_value

    return StateCommand(
        f"set {new_value}",
        action,
        capture=lambda: box.value,
        restore=lambda v: setattr(box, "value", v),
        size_of=lambda _v: size,
    )


def test_state_command_undo_redo_roundtrip():
    box, history = Box(), UndoHistory()
    for v in (1, 2, 3):
        cmd = state_cmd(box, v)
        assert cmd.perform() == v
        history.push(cmd)
    assert box.value == 3
    assert history.undo() and box.value == 2
    assert history.undo() and box.value == 1
    assert history.redo() and box.value == 2
    assert history.undo_label == "set 2"


def test_state_command_rolls_back_on_failure():
    box = Box()
    box.value = 5

    def broken():
        box.value = 99
        raise RuntimeError("boom")

    cmd = StateCommand("broken", broken, lambda: box.value, lambda v: setattr(box, "value", v), lambda _v: 1)
    with pytest.raises(RuntimeError):
        cmd.perform()
    assert box.value == 5


def test_callback_command_runs_inverse():
    box = Box()
    cmd = CallbackCommand("inc", lambda: setattr(box, "value", box.value + 1), lambda: setattr(box, "value", box.value - 1))
    cmd.perform()
    cmd.undo()
    assert box.value == 0
    cmd.redo()
    assert box.value == 1


def test_push_after_undo_discards_redo_branch():
    box, history = Box(), UndoHistory()
    for v in (1, 2):
        c = state_cmd(box, v)
        c.perform()
        history.push(c)
    history.undo()
    c = state_cmd(box, 7)
    c.perform()
    history.push(c)
    assert not history.can_redo
    assert len(history) == 2


def test_clean_state_tracking():
    box, history = Box(), UndoHistory()
    assert history.is_clean()
    c = state_cmd(box, 1)
    c.perform()
    history.push(c)
    assert not history.is_clean()
    history.mark_clean()
    assert history.is_clean()
    history.undo()
    assert not history.is_clean()
    history.redo()
    assert history.is_clean()


def test_memory_budget_expires_oldest_prefix():
    box, history = Box(), UndoHistory(memory_limit=25)
    for v in (1, 2, 3):
        c = state_cmd(box, v, size=10)
        c.perform()
        history.push(c)
    # 30 bytes > 25: the oldest command must be gone, the newer two remain
    assert history.memory_bytes() <= 25
    assert history.undo() and history.undo()
    assert not history.can_undo
    assert box.value == 1


def test_command_larger_than_budget_is_not_undoable():
    box, history = Box(), UndoHistory(memory_limit=5)
    c = state_cmd(box, 1, size=50)
    c.perform()
    expired = history.push(c)
    assert c in expired
    assert not history.can_undo


def test_max_steps_limit():
    box, history = Box(), UndoHistory(max_steps=2)
    for v in range(5):
        c = state_cmd(box, v + 1, size=0)
        c.perform()
        history.push(c)
    steps = 0
    while history.undo():
        steps += 1
    assert steps == 2


def test_expire_for_budget_noop_when_within_limits():
    box = Box()
    cmds = [state_cmd(box, 1, size=1)]
    cmds[0].perform()
    assert expire_for_budget(cmds, 1, memory_limit=100, max_steps=10) == []


def test_undo_on_empty_history_returns_false():
    history = UndoHistory()
    assert history.undo() is False
    assert history.redo() is False
