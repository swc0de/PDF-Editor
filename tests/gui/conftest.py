"""Fixtures for GUI tests (run with the offscreen Qt platform)."""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    from pdf_editor.settings import Settings

    return Settings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))


@pytest.fixture
def window(qtbot, settings, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from pdf_editor.app.main_window import MainWindow

    # never block on modal message boxes during tests
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Ok)
    win = MainWindow(settings)
    win.resize(1200, 800)
    qtbot.addWidget(win)
    win.show()
    yield win
    for tab in win.tabs_list():
        tab.doc._history.clear()  # discard changes so closing does not prompt
        tab.doc._force_modified = False
    win.close()


def pump(qtbot, seconds: float = 0.3) -> None:
    """Let timers (lazy rendering, incremental search) run for a while."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qtbot.wait(10)
