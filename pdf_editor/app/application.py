"""Application bootstrap: QApplication, logging, theme, main window, CLI files."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .. import APP_NAME, ORG_NAME, __version__
from ..settings import Settings
from .errors import install_excepthook, setup_logging
from .theme import apply_theme

log = logging.getLogger("pdf_editor")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pdf-editor", description=f"{APP_NAME} {__version__}")
    parser.add_argument("files", nargs="*", help="PDF files to open")
    parser.add_argument("--no-recovery", action="store_true", help="do not offer to restore autosaved files")
    known, _unknown = parser.parse_known_args(argv[1:])  # Qt may add its own options
    return known


def create_app(argv: list[str]) -> QApplication:
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(__version__)
    return app  # type: ignore[return-value]


def run(argv: list[str] | None = None) -> int:
    """Start the GUI; returns the process exit code."""
    argv = list(sys.argv if argv is None else argv)
    args = parse_args(argv)
    app = create_app(argv)
    log_path = setup_logging()
    install_excepthook()
    log.info("Starting %s %s (log: %s)", APP_NAME, __version__, log_path)

    from .main_window import MainWindow

    settings = Settings()
    effective = apply_theme(app, settings.theme)
    window = MainWindow(settings, effective)
    window.show()
    files = [os.path.abspath(f) for f in args.files]

    def startup() -> None:
        if not args.no_recovery and hasattr(window, "offer_recovery"):
            window.offer_recovery()
        window.file.open_paths(files)

    QTimer.singleShot(0, startup)
    return app.exec()
