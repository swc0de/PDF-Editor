"""Saving: incremental when possible, otherwise a full rewrite from a copy (mixin).

Kept separate from :mod:`pdf_editor.core.document` for size; see the
invariant described there: the live document's object numbers never change.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pymupdf

from .errors import PdfEditorError
from .events import Change, ChangeEvent
from .operations.security import KEEP_ENCRYPTION, encryption_save_kwargs

if TYPE_CHECKING:  # pragma: no cover
    from .document import PdfDocument


@dataclass(frozen=True)
class SaveResult:
    """Outcome of :meth:`SaveMixin.save`."""

    path: str
    incremental: bool
    size: int


class SaveMixin:
    """Mixed into ``PdfDocument``."""

    def save(self: "PdfDocument", path: str | None = None, *, garbage: int = 3) -> SaveResult:
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

    def _full_save(self: "PdfDocument", target: str, garbage: int, detach: bool) -> None:
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

    def mark_modified(self) -> None:
        """Treat the document as unsaved (e.g. restored from a recovery copy)."""
        self._force_modified = True

    def require_full_save(self) -> None:
        """Force the next save to rewrite the file (e.g. after redaction)."""
        self._needs_full_save = True


def _same_path(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
