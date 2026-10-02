"""Undoable document-level edits: security, metadata, bookmarks, redaction, OCR.

Mixed into ``PdfDocument``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

import pymupdf

from ..events import Change, ChangeEvent
from ..errors import PermissionDenied
from ..operations import metadata as meta_ops
from ..operations import outline as outline_ops
from ..operations import redact as redact_ops
from ..operations import security as sec_ops

if TYPE_CHECKING:  # pragma: no cover
    from ..document import PdfDocument


class ToolEditsMixin:
    """Security policy, metadata and outline editing."""

    # -- security ---------------------------------------------------------
    def authenticate_owner(self: "PdfDocument", password: str) -> bool:
        """Upgrade to owner rights with ``password``; True on success."""
        level = sec_ops.authentication_level(self.raw, password)
        if level == "owner":
            self._password = password
            self.notify(ChangeEvent(Change.SECURITY))
            return True
        return False

    def set_encryption(self: "PdfDocument", policy: sec_ops.EncryptionPolicy) -> None:
        """Choose how the next save is protected.

        ``EncryptionSettings`` applies AES-256, ``None`` removes any password
        and ``KEEP_ENCRYPTION`` keeps what the file had. Removing or changing
        protection requires owner rights.
        """
        if isinstance(policy, sec_ops.EncryptionSettings):
            policy.validate()
        if self.is_encrypted and not sec_ops.has_full_permissions(self.raw):
            raise PermissionDenied(
                "Changing the security of this document requires its owner (permissions) password."
            )
        old = self._encryption

        def apply(value: sec_ops.EncryptionPolicy) -> None:
            self._encryption = value
            self._needs_full_save = True

        label = "Remove password" if policy is None else "Set password protection"
        self.edit_reversible(
            label, lambda: apply(policy), lambda: apply(old), ChangeEvent(Change.SECURITY), permission=None
        )

    # -- metadata ---------------------------------------------------------
    def metadata(self: "PdfDocument") -> dict[str, str]:
        return meta_ops.get_metadata(self.raw)

    def set_metadata(self: "PdfDocument", values: dict[str, str]) -> None:
        """Update title/author/subject/keywords (undoable)."""
        old = meta_ops.get_metadata(self.raw)
        new = {**old, **values}
        if new == old:
            return
        self.edit_reversible(
            "Edit document properties",
            lambda: meta_ops.set_metadata(self.raw, new),
            lambda: meta_ops.set_metadata(self.raw, old),
            ChangeEvent(Change.METADATA),
        )

    # -- bookmarks --------------------------------------------------------
    def bookmarks(self: "PdfDocument") -> list[outline_ops.Bookmark]:
        return outline_ops.get_bookmarks(self.raw)

    def set_bookmarks(self: "PdfDocument", tree: Sequence[outline_ops.Bookmark], label: str = "Edit bookmarks") -> None:
        """Replace the outline (undoable: the previous outline is restored)."""
        old = outline_ops.get_bookmarks(self.raw)
        new = outline_ops.clone_tree(tree)
        self.edit_reversible(
            label,
            lambda: outline_ops.set_bookmarks(self.raw, new),
            lambda: outline_ops.set_bookmarks(self.raw, old),
            ChangeEvent(Change.OUTLINE),
            permission=pymupdf.PDF_PERM_MODIFY,
        )

    # -- redaction ----------------------------------------------------------
    def mark_redaction(self: "PdfDocument", pno: int, rect, label: str = "") -> int:
        """Mark an area for redaction (nothing is removed until applied)."""
        return self.edit_pages("Mark for redaction", [pno], lambda: redact_ops.mark_area(self.raw[pno], rect, label=label),
                               kind=Change.ANNOTATIONS)

    def mark_redaction_text(self: "PdfDocument", needle: str, match_case: bool = False) -> int:
        """Mark every occurrence of ``needle``; returns the number of marks."""
        pages = list(redact_ops.find_text_marks(self.raw, needle, match_case))
        if not pages:
            return 0
        return self.edit_pages(
            f"Mark '{needle}' for redaction", pages,
            lambda: len(redact_ops.mark_text(self.raw, needle, match_case, pages)), kind=Change.ANNOTATIONS,
        )

    def redaction_marks(self: "PdfDocument"):
        return redact_ops.list_marks(self.raw)

    def apply_redactions(self: "PdfDocument", scrub: bool = False) -> int:
        """Permanently remove marked content (and optionally hidden data).

        The next save is forced to be a full rewrite so the removed content
        cannot survive in an earlier revision of the file.
        """

        def apply() -> int:
            changed = redact_ops.apply_redactions(self.raw)
            if scrub:
                redact_ops.scrub_hidden_data(self.raw)
            return changed

        result = self.edit_snapshot("Apply redactions", apply)
        self.require_full_save()
        return result
