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
