"""Autosave recovery copies and crash recovery.

Every running app session holds a lock file in the recovery folder. Modified
documents are written there periodically (``<session>-<tab>.pdf`` plus a
JSON sidecar). Saving or closing a document deletes its copy, so leftovers
only exist after a crash. At startup, copies whose session lock is no longer
held (the process died) are offered for restoring.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from dataclasses import dataclass

import pymupdf
from PySide6.QtCore import QLockFile, QObject, QTimer

log = logging.getLogger(__name__)


def recovery_dir() -> str:
    folder = os.path.join(tempfile.gettempdir(), "pdf_editor_recovery")
    os.makedirs(folder, exist_ok=True)
    return folder


@dataclass(frozen=True)
class RecoveryEntry:
    pdf_path: str
    meta_path: str
    original_path: str | None
    display_name: str
    saved_at: float
    encrypted: bool

    @property
    def label(self) -> str:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.saved_at))
        return f"{self.display_name}  (autosaved {when})"

    def discard(self) -> None:
        for path in (self.pdf_path, self.meta_path):
            try:
                os.remove(path)
            except OSError:
                pass


class AutosaveManager(QObject):
    """Writes recovery copies for one app session."""

    def __init__(self, interval_minutes: int, folder: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.folder = folder or recovery_dir()
        self.session = uuid.uuid4().hex[:12]
        self._lock = QLockFile(os.path.join(self.folder, f"session-{self.session}.lock"))
        self._lock.setStaleLockTime(0)  # only consider a lock stale when its process is gone
        self._lock.tryLock(0)
        self._tabs: dict[int, object] = {}
        self._dirty: set[int] = set()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.autosave_all)
        self.set_interval(interval_minutes)

    def set_interval(self, minutes: int) -> None:
        self.timer.stop()
        if minutes > 0:
            self.timer.start(minutes * 60_000)

    # -- tracking ---------------------------------------------------------------
    def _paths(self, tab) -> tuple[str, str]:
        base = os.path.join(self.folder, f"{self.session}-{id(tab):x}")
        return base + ".pdf", base + ".json"

    def watch(self, tab) -> None:
        self._tabs[id(tab)] = tab
        tab.documentChanged.connect(lambda _e, t=tab: self._dirty.add(id(t)))

    def forget(self, tab) -> None:
        """The document was saved: its recovery copy is no longer needed."""
        self._dirty.discard(id(tab))
        self._remove_files(tab)

    def unwatch(self, tab) -> None:
        """The tab is closing: stop tracking it and remove its copy."""
        self._tabs.pop(id(tab), None)
        self.forget(tab)

    def _remove_files(self, tab) -> None:
        for path in self._paths(tab):
            try:
                os.remove(path)
            except OSError:
                pass

    # -- writing ------------------------------------------------------------------
    def autosave_all(self) -> int:
        """Write copies of modified documents changed since the last autosave."""
        written = 0
        for key in list(self._dirty):
            tab = self._tabs.get(key)
            self._dirty.discard(key)
            if tab is None or tab.doc.raw.is_closed:
                continue
            if not tab.doc.is_modified:  # e.g. undone back to the saved state
                self._remove_files(tab)
                continue
            try:
                self.write(tab)
                written += 1
            except Exception:
                self._dirty.add(key)  # retry next time
                log.exception("Autosave of %s failed", tab.doc.display_name)
        return written

    def write(self, tab) -> None:
        pdf_path, meta_path = self._paths(tab)
        # Garbage-collected copy: content removed by redaction must not linger on disk.
        data = tab.doc.raw.tobytes(garbage=3, deflate=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
        tmp = pdf_path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, pdf_path)
        meta = {"original_path": tab.doc.path, "display_name": tab.doc.display_name, "saved_at": time.time(),
                "session": self.session, "encrypted": bool(tab.doc.password)}
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh)

    def shutdown(self) -> None:
        """Normal exit: remove everything this session wrote and release the lock."""
        self.timer.stop()
        for tab in list(self._tabs.values()):
            self._remove_files(tab)
        self._lock.unlock()


def find_orphans(folder: str | None = None, current_session: str | None = None) -> list[RecoveryEntry]:
    """Recovery copies left behind by sessions that are no longer running."""
    folder = folder or recovery_dir()
    entries: list[RecoveryEntry] = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        meta_path = os.path.join(folder, name)
        pdf_path = meta_path[:-5] + ".pdf"
        try:
            with open(meta_path, encoding="utf-8") as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            continue
        session = meta.get("session", "")
        if session == current_session or not os.path.exists(pdf_path):
            continue
        lock = QLockFile(os.path.join(folder, f"session-{session}.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):  # still held by a running instance
            continue
        lock.unlock()
        entries.append(RecoveryEntry(pdf_path, meta_path, meta.get("original_path"),
                                     meta.get("display_name", "document.pdf"), float(meta.get("saved_at", 0)),
                                     bool(meta.get("encrypted"))))
    return entries
