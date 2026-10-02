"""The document model: wraps ``pymupdf.Document``; every edit goes through here.

``PdfDocument`` owns the underlying PyMuPDF document, records every change
as an undoable :class:`~pdf_editor.core.history.Command`, and notifies
listeners (the GUI) about what changed. The high-level edit methods live in
mixins under :mod:`pdf_editor.core.edits` to keep files small; they all use
the primitives defined here:

* :meth:`edit_pages` / :meth:`edit_annotation` - object-level undo state;
* :meth:`edit_snapshot` - whole-document snapshot for hard-to-invert edits;
* :meth:`edit_reversible` - an explicit inverse function.

Invariant: xref numbers of existing objects never change while a document
is open (snapshots use ``garbage=0`` and saving works on a copy), so every
recorded command stays valid across undo/redo and saves.
"""

from __future__ import annotations

import itertools
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Callable, Iterable

import pymupdf

from . import objstate
from .edits.annotations import AnnotationEditsMixin
from .edits.content import ContentEditsMixin
from .edits.pages import PageEditsMixin
from .edits.tools import ToolEditsMixin
from .events import Change, ChangeEvent
from .errors import PasswordRequired, PdfEditorError, PermissionDenied, WrongPassword
from .history import CallbackCommand, Command, HistoryBackend, StateCommand, UndoHistory
from .operations.security import KEEP_ENCRYPTION, EncryptionPolicy, encryption_save_kwargs

_untitled_counter = itertools.count(1)


@dataclass(frozen=True)
class SaveResult:
    """Outcome of :meth:`PdfDocument.save`."""

    path: str
    incremental: bool
    size: int


class PdfDocument(PageEditsMixin, AnnotationEditsMixin, ContentEditsMixin, ToolEditsMixin):
    """An open PDF with undo/redo history and change notifications."""

    def __init__(
        self,
        raw: pymupdf.Document,
        *,
        path: str | None = None,
        password: str | None = None,
        backing_path: str | None = None,
        history: HistoryBackend | None = None,
        name: str | None = None,
    ) -> None:
        self._raw = raw
        self.path = os.path.abspath(path) if path else None
        self._password = password
        self._backing_path = backing_path
        self._history: HistoryBackend = history or UndoHistory()
        self._listeners: list[Callable[[ChangeEvent], None]] = []
        self._revisions: dict[int, int] = {}
        self.generation = 0
        self._needs_full_save = False
        self._force_modified = False
        self._encryption: EncryptionPolicy = KEEP_ENCRYPTION
        self._name = name or (os.path.basename(path) if path else f"Untitled-{next(_untitled_counter)}.pdf")

    # ------------------------------------------------------------------
    # construction
    @classmethod
    def open(cls, path: str, password: str | None = None) -> "PdfDocument":
        """Open a PDF (or any format MuPDF converts to PDF, such as images)."""
        path = os.path.abspath(path)
        try:
            raw = pymupdf.open(path)
        except (pymupdf.FileNotFoundError, FileNotFoundError) as exc:
            raise PdfEditorError(f"The file '{path}' was not found.") from exc
        except Exception as exc:  # pymupdf.FileDataError and friends
            raise PdfEditorError(
                f"'{os.path.basename(path)}' could not be opened. It may be damaged or not a PDF.",
                details=str(exc),
            ) from exc
        if not raw.is_pdf:
            converted = pymupdf.open("pdf", raw.convert_to_pdf())
            raw.close()
            stem = os.path.splitext(os.path.basename(path))[0]
            return cls(converted, name=f"{stem}.pdf")
        cls._unlock(raw, password, path)
        return cls(raw, path=path, password=password, backing_path=raw.name)

    @classmethod
    def from_bytes(
        cls, data: bytes, *, path: str | None = None, password: str | None = None, name: str | None = None
    ) -> "PdfDocument":
        """Open a PDF held in memory (e.g. a recovery file)."""
        try:
            raw = pymupdf.open("pdf", data)
        except Exception as exc:
            raise PdfEditorError("The data is not a valid PDF.", details=str(exc)) from exc
        cls._unlock(raw, password, path or name or "document")
        return cls(raw, path=path, password=password, name=name)

    @classmethod
    def new(cls, width: float = 595, height: float = 842) -> "PdfDocument":
        """Create an empty document with one blank page (A4 by default)."""
        raw = pymupdf.open()
        raw.new_page(width=width, height=height)
        doc = cls(raw)
        doc._force_modified = True
        return doc

    @staticmethod
    def _unlock(raw: pymupdf.Document, password: str | None, label: str) -> None:
        if not raw.needs_pass:
            return
        name = os.path.basename(label)
        if password is None:
            raw.close()
            raise PasswordRequired(f"'{name}' is protected. Please enter its password.")
        if not raw.authenticate(password):
            raw.close()
            raise WrongPassword(f"The password for '{name}' is not correct.")

    # ------------------------------------------------------------------
    # basic properties
    @property
    def raw(self) -> pymupdf.Document:
        """The underlying PyMuPDF document (read access for rendering/extraction)."""
        return self._raw

    @property
    def page_count(self) -> int:
        return self._raw.page_count

    @property
    def display_name(self) -> str:
        return os.path.basename(self.path) if self.path else self._name

    @property
    def is_modified(self) -> bool:
        return self._force_modified or not self._history.is_clean()

    @property
    def needs_full_save(self) -> bool:
        return self._needs_full_save

    @property
    def is_encrypted(self) -> bool:
        """True if the file on disk was encrypted when opened."""
        return bool(self._password) or bool(self._raw.metadata and self._raw.metadata.get("encryption"))

    @property
    def password(self) -> str | None:
        """The password used to unlock the file (needed to hand it to background jobs)."""
        return self._password

    @property
    def encryption_policy(self) -> EncryptionPolicy:
        return self._encryption

    @property
    def history(self) -> HistoryBackend:
        return self._history

    def set_history(self, history: HistoryBackend) -> None:
        """Replace the history backend (the GUI installs a QUndoStack adapter)."""
        self._history.clear()
        self._history = history

    def has_permission(self, flag: int) -> bool:
        """Check a ``pymupdf.PDF_PERM_*`` flag for the opened document."""
        return bool(self._raw.permissions & flag)

    def page_key(self, pno: int) -> tuple[int, int, int]:
        """A cache key that changes whenever page ``pno`` looks different."""
        xref = self._raw.page_xref(pno)
        return (self.generation, xref, self._revisions.get(xref, 0))

    def page_rect(self, pno: int) -> pymupdf.Rect:
        """Visible (rotated, cropped) page rectangle in points."""
        return self._raw[pno].rect

    def close(self) -> None:
        self._history.clear()
        self._listeners.clear()
        if not self._raw.is_closed:
            self._raw.close()

    # ------------------------------------------------------------------
    # notifications
    def add_listener(self, callback: Callable[[ChangeEvent], None]) -> None:
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[ChangeEvent], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def notify(self, event: ChangeEvent) -> None:
        """Bump page revisions and inform listeners about ``event``."""
        if event.kind == Change.RELOAD:
            self.generation += 1
        if event.pages and event.kind in (Change.CONTENT, Change.ANNOTATIONS, Change.STRUCTURE, Change.FORMS):
            for pno in event.pages:
                if 0 <= pno < self._raw.page_count:
                    xref = self._raw.page_xref(pno)
                    self._revisions[xref] = self._revisions.get(xref, 0) + 1
        for listener in list(self._listeners):
            listener(event)

    # ------------------------------------------------------------------
    # edit primitives
    def _check_permission(self, flag: int | None) -> None:
        if flag is not None and not self.has_permission(flag):
            raise PermissionDenied(
                "This document's security settings do not allow this change. "
                "Re-open it with the owner password to edit it."
            )

    def execute(self, command: Command, permission: int | None = pymupdf.PDF_PERM_MODIFY) -> Any:
        """Perform ``command`` and record it in the history."""
        self._check_permission(permission)
        result = command.perform()
        expired = self._history.push(command)
        if command in expired:
            self.notify(ChangeEvent(Change.HISTORY_TRUNCATED))
        return result

    def edit_objects(
        self,
        label: str,
        xrefs: Callable[[], Iterable[int]],
        action: Callable[[], Any],
        event: ChangeEvent,
        permission: int | None = pymupdf.PDF_PERM_MODIFY,
    ) -> Any:
        """Run ``action`` recording only the objects returned by ``xrefs()``."""
        command = StateCommand(
            label,
            action,
            capture=lambda: objstate.capture_objects(self._raw, list(xrefs())),
            restore=lambda state: objstate.restore_objects(self._raw, state),
            size_of=objstate.state_size,
            after=lambda: self.notify(event),
        )
        return self.execute(command, permission)

    def edit_pages(
        self,
        label: str,
        pages: Iterable[int],
        action: Callable[[], Any],
        kind: str = Change.CONTENT,
        permission: int | None = pymupdf.PDF_PERM_MODIFY,
        deep: bool = False,
    ) -> Any:
        """Edit content or annotations of ``pages`` with page-level undo state.

        ``deep`` also records the pages' Form XObjects (needed for redaction).
        """
        pages = tuple(sorted(set(pages)))

        def xrefs() -> list[int]:
            return [x for p in pages for x in objstate.page_object_xrefs(self._raw, p, deep)]

        return self.edit_objects(label, xrefs, action, ChangeEvent(kind, pages), permission)

    def edit_annotation(
        self,
        label: str,
        pno: int,
        annot_xref: int,
        action: Callable[[], Any],
        kind: str = Change.ANNOTATIONS,
        permission: int | None = pymupdf.PDF_PERM_ANNOTATE,
    ) -> Any:
        """Modify one annotation/widget, recording only its own objects."""

        def xrefs() -> list[int]:
            return objstate.annot_object_xrefs(self._raw, annot_xref)

        return self.edit_objects(label, xrefs, action, ChangeEvent(kind, (pno,)), permission)

    def edit_snapshot(
        self,
        label: str,
        action: Callable[[], Any],
        permission: int | None = pymupdf.PDF_PERM_MODIFY,
    ) -> Any:
        """Run ``action`` with a whole-document snapshot as undo state."""
        command = StateCommand(
            label,
            action,
            capture=self.snapshot,
            restore=self.restore_snapshot,
            size_of=len,
            after=lambda: self.notify(ChangeEvent(Change.RELOAD)),
        )
        return self.execute(command, permission)

    def edit_reversible(
        self,
        label: str,
        do: Callable[[], Any],
        undo: Callable[[], None],
        event: ChangeEvent,
        permission: int | None = pymupdf.PDF_PERM_MODIFY,
    ) -> Any:
        """Run ``do`` with ``undo`` as its explicit inverse."""
        command = CallbackCommand(label, do, undo, after=lambda: self.notify(event))
        return self.execute(command, permission)

    # ------------------------------------------------------------------
    # snapshots
    def snapshot(self) -> bytes:
        """Serialize the document without renumbering objects."""
        return self._raw.tobytes(garbage=0, encryption=pymupdf.PDF_ENCRYPT_KEEP)

    def restore_snapshot(self, data: bytes) -> None:
        """Replace the in-memory document with a snapshot."""
        raw = pymupdf.open("pdf", data)
        if raw.needs_pass and self._password:
            raw.authenticate(self._password)
        old, self._raw = self._raw, raw
        self._backing_path = None
        old.close()

    def replace_content(self, label: str, data: bytes) -> None:
        """Replace the document with ``data`` (e.g. the result of an OCR job)."""
        self.edit_snapshot(label, lambda: self.restore_snapshot(data))

    # ------------------------------------------------------------------
    # saving
    def save(self, path: str | None = None, *, garbage: int = 3) -> SaveResult:
        """Save to ``path`` (default: the current file).

        Writes incrementally when saving back to the file the document was
        opened from and nothing requires a rewrite; otherwise writes a full,
        garbage-collected copy to a temporary file and moves it into place.
        """
        target = os.path.abspath(path or self.path or "")
        if not path and not self.path:
            raise PdfEditorError("Please choose where to save the document.")
        same_as_backing = self._backing_path is not None and _same_path(target, self._backing_path)
        incremental = (
            same_as_backing
            and not self._needs_full_save
            and self._encryption is KEEP_ENCRYPTION
            and self._raw.can_save_incrementally()
        )
        try:
            if incremental:
                self._raw.save(self._backing_path, incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
            else:
                self._full_save(target, garbage, detach=same_as_backing)
        except PermissionError as exc:
            raise PdfEditorError(f"Cannot write to '{target}'. Check that it is not open elsewhere.") from exc
        except OSError as exc:
            raise PdfEditorError(f"Saving to '{target}' failed: {exc.strerror or exc}") from exc
        self.path = target
        self._needs_full_save = False
        self._force_modified = False
        self._history.mark_clean()
        self.notify(ChangeEvent(Change.SAVED))
        return SaveResult(target, incremental, os.path.getsize(target))

    def _full_save(self, target: str, garbage: int, detach: bool) -> None:
        data = self.snapshot()
        copy = pymupdf.open("pdf", data)
        if copy.needs_pass and self._password:
            copy.authenticate(self._password)
        folder = os.path.dirname(target) or "."
        fd, tmp = tempfile.mkstemp(prefix=".pdfedit-", suffix=".pdf", dir=folder)
        os.close(fd)
        try:
            copy.save(tmp, garbage=garbage, deflate=True, **encryption_save_kwargs(self._encryption))
            copy.close()
            if detach:
                # The live document reads lazily from the file we are about to
                # replace; switch it to an in-memory copy with identical xrefs.
                self.restore_snapshot(data)
            os.replace(tmp, target)
        finally:
            if not copy.is_closed:
                copy.close()
            if os.path.exists(tmp):
                os.remove(tmp)

    def require_full_save(self) -> None:
        """Force the next save to rewrite the file (e.g. after redaction)."""
        self._needs_full_save = True


def _same_path(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
