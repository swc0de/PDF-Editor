"""Document information dictionary (title, author, subject, keywords...)."""

from __future__ import annotations

import pymupdf

from ..errors import InvalidInput

EDITABLE_FIELDS = ("title", "author", "subject", "keywords", "creator", "producer")


def get_metadata(doc: pymupdf.Document) -> dict[str, str]:
    """Return the editable metadata fields (missing values as empty strings)."""
    meta = doc.metadata or {}
    return {key: (meta.get(key) or "") for key in EDITABLE_FIELDS}


def set_metadata(doc: pymupdf.Document, values: dict[str, str]) -> None:
    """Update metadata fields; keys not in ``values`` are left unchanged."""
    unknown = set(values) - set(EDITABLE_FIELDS)
    if unknown:
        raise InvalidInput(f"Unknown metadata field(s): {', '.join(sorted(unknown))}")
    current = dict(doc.metadata or {})
    for key, value in values.items():
        current[key] = (value or "").strip()
    # PyMuPDF expects only known keys; drop computed ones like 'format'.
    allowed = EDITABLE_FIELDS + ("creationDate", "modDate", "trapped")
    doc.set_metadata({k: v for k, v in current.items() if k in allowed and v is not None})


def document_info(doc: pymupdf.Document) -> dict[str, str]:
    """Read-only facts for a properties dialog."""
    meta = doc.metadata or {}
    return {
        "format": meta.get("format") or "",
        "encryption": meta.get("encryption") or "None",
        "pages": str(doc.page_count),
        "created": meta.get("creationDate") or "",
        "modified": meta.get("modDate") or "",
    }
