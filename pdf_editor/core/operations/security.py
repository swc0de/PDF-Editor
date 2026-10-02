"""Password protection (AES-256), permissions and password removal."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Union

import pymupdf

from ..errors import InvalidInput

PERMISSION_FLAGS: dict[str, int] = {
    "print": pymupdf.PDF_PERM_PRINT,
    "print_high_quality": pymupdf.PDF_PERM_PRINT_HQ,
    "copy": pymupdf.PDF_PERM_COPY,
    "modify": pymupdf.PDF_PERM_MODIFY,
    "annotate": pymupdf.PDF_PERM_ANNOTATE,
    "fill_forms": pymupdf.PDF_PERM_FORM,
    "assemble": pymupdf.PDF_PERM_ASSEMBLE,
    "accessibility": pymupdf.PDF_PERM_ACCESSIBILITY,
}

PERMISSION_LABELS: dict[str, str] = {
    "print": "Print",
    "print_high_quality": "Print in high quality",
    "copy": "Copy text and images",
    "modify": "Change the document",
    "annotate": "Add comments and annotations",
    "fill_forms": "Fill in form fields",
    "assemble": "Insert, rotate and delete pages",
    "accessibility": "Extract content for accessibility",
}


class _KeepEncryption:
    """Sentinel: save with whatever encryption the opened file had."""

    _instance: "_KeepEncryption | None" = None

    def __new__(cls) -> "_KeepEncryption":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "KEEP_ENCRYPTION"


KEEP_ENCRYPTION = _KeepEncryption()


@dataclass(frozen=True)
class EncryptionSettings:
    """AES-256 password protection to apply when saving."""

    owner_password: str
    user_password: str = ""
    allowed: frozenset[str] = field(default_factory=lambda: frozenset(PERMISSION_FLAGS))

    def validate(self) -> None:
        """Raise :class:`InvalidInput` if the settings cannot be used."""
        if not self.owner_password:
            raise InvalidInput("An owner (permissions) password is required.")
        unknown = set(self.allowed) - set(PERMISSION_FLAGS)
        if unknown:
            raise InvalidInput(f"Unknown permission(s): {', '.join(sorted(unknown))}")
        if self.user_password and self.user_password == self.owner_password and self.allowed != frozenset(
            PERMISSION_FLAGS
        ):
            raise InvalidInput(
                "The open password and the permissions password must differ, "
                "otherwise anyone who can open the file has full rights."
            )


# KEEP_ENCRYPTION, None (= remove encryption) or new settings.
EncryptionPolicy = Union[_KeepEncryption, None, EncryptionSettings]


def permissions_value(allowed: Iterable[str]) -> int:
    """Combine permission names into a PDF permission integer."""
    value = 0
    for name in allowed:
        if name not in PERMISSION_FLAGS:
            raise InvalidInput(f"Unknown permission '{name}'.")
        value |= PERMISSION_FLAGS[name]
    return value


def describe_permissions(value: int) -> dict[str, bool]:
    """Expand a PDF permission integer into ``{name: allowed}``."""
    return {name: bool(value & flag) for name, flag in PERMISSION_FLAGS.items()}


def encryption_save_kwargs(policy: EncryptionPolicy) -> dict:
    """Keyword arguments for ``pymupdf.Document.save`` implementing ``policy``."""
    if policy is KEEP_ENCRYPTION:
        return {"encryption": pymupdf.PDF_ENCRYPT_KEEP}
    if policy is None:
        return {"encryption": pymupdf.PDF_ENCRYPT_NONE}
    assert isinstance(policy, EncryptionSettings)
    policy.validate()
    return {
        "encryption": pymupdf.PDF_ENCRYPT_AES_256,
        "owner_pw": policy.owner_password,
        "user_pw": policy.user_password,
        "permissions": permissions_value(policy.allowed),
    }


def save_encrypted(doc: pymupdf.Document, path: str, settings: EncryptionSettings) -> None:
    """Write ``doc`` to ``path`` protected with AES-256."""
    doc.save(path, garbage=3, deflate=True, **encryption_save_kwargs(settings))


def save_decrypted(doc: pymupdf.Document, path: str) -> None:
    """Write ``doc`` to ``path`` without any password protection."""
    if doc.is_encrypted:  # still locked (needs_pass stays true after unlocking)
        raise InvalidInput("The document must be unlocked before its password can be removed.")
    doc.save(path, garbage=3, deflate=True, encryption=pymupdf.PDF_ENCRYPT_NONE)


def authentication_level(doc: pymupdf.Document, password: str) -> str:
    """Classify ``password`` for an encrypted document.

    Returns ``"owner"``, ``"user"`` or ``"none"`` (wrong password). For an
    unencrypted document every password grants ``"owner"`` rights.
    """
    if not doc.is_encrypted and not doc.needs_pass:
        return "owner"
    result = doc.authenticate(password)
    if result & 4:
        return "owner"
    if result & 2 or result == 1:
        return "user"
    return "none"


def has_full_permissions(doc: pymupdf.Document) -> bool:
    """True if every permission bit is granted for the opened document."""
    wanted = permissions_value(PERMISSION_FLAGS)
    return (doc.permissions & wanted) == wanted
