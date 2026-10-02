"""QSettings-backed preferences, recent files, window state and saved signatures.

This lives outside ``core`` because it depends on Qt (``QSettings``).
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QByteArray, QSettings

from . import APP_NAME, ORG_NAME

MAX_RECENT_FILES = 12
THEMES = ("system", "light", "dark")
ZOOM_MODES = ("fit-width", "fit-page", "actual")


@dataclass(frozen=True)
class SavedSignature:
    """A reusable signature image (PNG with transparency)."""

    name: str
    png: bytes


class Settings:
    """Typed access to persistent application settings."""

    def __init__(self, qsettings: QSettings | None = None) -> None:
        self._s = qsettings or QSettings(ORG_NAME, APP_NAME)

    # -- generic helpers ------------------------------------------------
    def _get(self, key: str, default: Any, kind: type) -> Any:
        value = self._s.value(key, default)
        if value is None:
            return default
        try:
            if kind is bool:
                return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes")
            return kind(value)
        except (TypeError, ValueError):
            return default

    def _list(self, key: str) -> list[str]:
        value = self._s.value(key, [])
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [value]
        return [str(v) for v in value]

    def sync(self) -> None:
        self._s.sync()

    # -- appearance -------------------------------------------------------
    @property
    def theme(self) -> str:
        value = self._get("appearance/theme", "system", str)
        return value if value in THEMES else "system"

    @theme.setter
    def theme(self, value: str) -> None:
        self._s.setValue("appearance/theme", value if value in THEMES else "system")

    @property
    def invert_pages(self) -> bool:
        return self._get("appearance/invert_pages", False, bool)

    @invert_pages.setter
    def invert_pages(self, value: bool) -> None:
        self._s.setValue("appearance/invert_pages", bool(value))

    # -- viewing ----------------------------------------------------------
    @property
    def default_zoom(self) -> str:
        """``fit-width``, ``fit-page``, ``actual`` or a percentage such as ``"125"``."""
        value = self._get("view/default_zoom", "fit-width", str)
        if value in ZOOM_MODES:
            return value
        try:
            return str(max(10, min(800, int(float(value)))))
        except ValueError:
            return "fit-width"

    @default_zoom.setter
    def default_zoom(self, value: str) -> None:
        self._s.setValue("view/default_zoom", str(value))

    @property
    def continuous_scroll(self) -> bool:
        return self._get("view/continuous", True, bool)

    @continuous_scroll.setter
    def continuous_scroll(self, value: bool) -> None:
        self._s.setValue("view/continuous", bool(value))

    # -- editing ----------------------------------------------------------
    @property
    def annotation_color(self) -> str:
        return self._get("editing/annotation_color", "#e53935", str)

    @annotation_color.setter
    def annotation_color(self, value: str) -> None:
        self._s.setValue("editing/annotation_color", value)

    @property
    def highlight_color(self) -> str:
        return self._get("editing/highlight_color", "#ffeb3b", str)

    @highlight_color.setter
    def highlight_color(self, value: str) -> None:
        self._s.setValue("editing/highlight_color", value)

    @property
    def author(self) -> str:
        return self._get("editing/author", os.environ.get("USERNAME") or os.environ.get("USER") or "", str)

    @author.setter
    def author(self, value: str) -> None:
        self._s.setValue("editing/author", value)

    @property
    def autosave_minutes(self) -> int:
        """Minutes between recovery autosaves; 0 disables autosave."""
        return max(0, min(120, self._get("editing/autosave_minutes", 2, int)))

    @autosave_minutes.setter
    def autosave_minutes(self, value: int) -> None:
        self._s.setValue("editing/autosave_minutes", int(value))

    @property
    def undo_memory_mb(self) -> int:
        return max(16, min(4096, self._get("editing/undo_memory_mb", 256, int)))

    @undo_memory_mb.setter
    def undo_memory_mb(self, value: int) -> None:
        self._s.setValue("editing/undo_memory_mb", int(value))

    # -- recent files -------------------------------------------------------
    def recent_files(self) -> list[str]:
        return self._list("files/recent")

    def add_recent_file(self, path: str) -> None:
        path = os.path.abspath(path)
        files = [p for p in self.recent_files() if os.path.normcase(p) != os.path.normcase(path)]
        files.insert(0, path)
        self._s.setValue("files/recent", files[:MAX_RECENT_FILES])

    def remove_recent_file(self, path: str) -> None:
        files = [p for p in self.recent_files() if os.path.normcase(p) != os.path.normcase(os.path.abspath(path))]
        self._s.setValue("files/recent", files)

    def clear_recent_files(self) -> None:
        self._s.setValue("files/recent", [])

    @property
    def last_directory(self) -> str:
        value = self._get("files/last_directory", "", str)
        return value if value and os.path.isdir(value) else os.path.expanduser("~")

    @last_directory.setter
    def last_directory(self, value: str) -> None:
        self._s.setValue("files/last_directory", value)

    # -- signatures ---------------------------------------------------------
    def signatures(self) -> list[SavedSignature]:
        result = []
        size = self._s.beginReadArray("signatures")
        for i in range(size):
            self._s.setArrayIndex(i)
            name = str(self._s.value("name", f"Signature {i + 1}"))
            try:
                png = base64.b64decode(str(self._s.value("png", "")))
            except (ValueError, TypeError):
                continue
            if png:
                result.append(SavedSignature(name, png))
        self._s.endArray()
        return result

    def _write_signatures(self, signatures: list[SavedSignature]) -> None:
        self._s.remove("signatures")
        self._s.beginWriteArray("signatures", len(signatures))
        for i, sig in enumerate(signatures):
            self._s.setArrayIndex(i)
            self._s.setValue("name", sig.name)
            self._s.setValue("png", base64.b64encode(sig.png).decode("ascii"))
        self._s.endArray()

    def add_signature(self, signature: SavedSignature) -> None:
        self._write_signatures(self.signatures() + [signature])

    def remove_signature(self, index: int) -> None:
        sigs = self.signatures()
        if 0 <= index < len(sigs):
            del sigs[index]
            self._write_signatures(sigs)

    # -- window state ---------------------------------------------------------
    def window_geometry(self) -> QByteArray | None:
        value = self._s.value("window/geometry")
        return value if isinstance(value, QByteArray) else None

    def set_window_geometry(self, value: QByteArray) -> None:
        self._s.setValue("window/geometry", value)

    def window_state(self) -> QByteArray | None:
        value = self._s.value("window/state")
        return value if isinstance(value, QByteArray) else None

    def set_window_state(self, value: QByteArray) -> None:
        self._s.setValue("window/state", value)

    def panel_visible(self, name: str, default: bool = True) -> bool:
        return self._get(f"window/panel_{name}", default, bool)

    def set_panel_visible(self, name: str, visible: bool) -> None:
        self._s.setValue(f"window/panel_{name}", bool(visible))
