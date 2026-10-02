"""Change notifications sent by ``PdfDocument`` to its listeners."""

from __future__ import annotations

from dataclasses import dataclass


class Change:
    """Kinds of :class:`ChangeEvent`."""

    CONTENT = "content"  # page content changed -> re-render ``pages``
    ANNOTATIONS = "annotations"  # annotations changed on ``pages``
    STRUCTURE = "structure"  # pages added/removed/reordered/rotated/resized
    RELOAD = "reload"  # whole document replaced (snapshot restore)
    OUTLINE = "outline"
    METADATA = "metadata"
    FORMS = "forms"
    SECURITY = "security"
    SAVED = "saved"
    HISTORY_TRUNCATED = "history_truncated"  # an edit was too large to keep undoable


@dataclass(frozen=True)
class ChangeEvent:
    """Notification sent to listeners after the document changed."""

    kind: str
    pages: tuple[int, ...] | None = None
