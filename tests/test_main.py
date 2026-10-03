"""Tests for the entry point's start-up checks."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from pdf_editor import main as entry


def test_python_version_problem_accepts_supported_versions():
    assert entry.python_version_problem((3, 11, 0)) is None
    assert entry.python_version_problem((3, 13, 2)) is None
    assert entry.python_version_problem() is None  # the interpreter running the tests


def test_python_version_problem_explains_old_versions():
    message = entry.python_version_problem((3, 9, 13))
    assert message is not None
    assert "3.9.13" in message and "3.11 or newer" in message and "py -3.11 -m venv .venv" in message


def test_main_stops_before_loading_the_app_on_old_python(monkeypatch):
    reported = []
    monkeypatch.setattr(entry, "python_version_problem", lambda: "too old")
    monkeypatch.setattr(entry, "report_startup_problem", reported.append)
    assert entry.main([]) == 1 and reported == ["too old"]


@pytest.mark.gui
def test_report_startup_problem_prints_and_shows_dialog(qapp, monkeypatch, capsys):
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda parent, title, text: shown.append(text))
    entry.report_startup_problem("Python too old")
    assert shown == ["Python too old"] and "Python too old" in capsys.readouterr().err


def test_entry_module_imports_cleanly_without_the_app():
    """The version check only works if importing the entry point loads nothing else."""
    code = (
        "import sys, pdf_editor.main\n"
        "print(any(m.startswith('pdf_editor.') and m != 'pdf_editor.main' for m in sys.modules))\n"
    )
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=root, check=True)
    assert out.stdout.strip() == "False"
