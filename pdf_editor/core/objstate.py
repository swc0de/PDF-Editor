"""Capture and restore individual PDF objects - the "minimal state" for undo.

Most edits only touch a handful of objects: a page dictionary, its content
streams, its ``/Annots`` array, or one annotation and its appearance
streams. Recording just those objects (by xref) is far cheaper than a whole
document snapshot, and restoring them is exact: raw (still encoded) stream
bytes are written back together with the original dictionary.

Objects created by an edit are simply left unreferenced after an undo; they
are dropped when the file is saved with garbage collection.
"""

from __future__ import annotations

import re
from typing import Iterable

import pymupdf

# xref -> (object source, raw stream bytes or None)
ObjectState = dict[int, tuple[str, bytes | None]]

_REF = re.compile(r"(\d+)\s+0\s+R")


def _refs(value: str) -> list[int]:
    return [int(m) for m in _REF.findall(value)]


def _key_refs(doc: pymupdf.Document, xref: int, key: str) -> list[int]:
    """Indirect objects referenced by ``key`` of object ``xref``."""
    kind, value = doc.xref_get_key(xref, key)
    if kind in ("xref", "array", "dict"):
        return _refs(value)
    return []


def capture_objects(doc: pymupdf.Document, xrefs: Iterable[int]) -> ObjectState:
    """Record the current source (and raw stream) of each object."""
    state: ObjectState = {}
    length = doc.xref_length()
    for xref in xrefs:
        if xref in state or not 0 < xref < length:
            continue
        source = doc.xref_object(xref, compressed=False)
        raw = doc.xref_stream_raw(xref) if doc.xref_is_stream(xref) else None
        state[xref] = (source, raw)
    return state


def restore_objects(doc: pymupdf.Document, state: ObjectState) -> None:
    """Write recorded objects back exactly as they were."""
    for xref, (source, raw) in state.items():
        if raw is not None:
            # Writing raw bytes drops /Filter, so the dictionary goes last.
            doc.update_stream(xref, raw, compress=0)
        doc.update_object(xref, source)


def state_size(state: ObjectState) -> int:
    """Approximate memory held by a captured state."""
    return sum(len(src) + (len(raw) if raw else 0) for src, raw in state.values()) + 64 * len(state)


def page_object_xrefs(doc: pymupdf.Document, pno: int) -> list[int]:
    """Objects that page-content and annotation edits on page ``pno`` modify.

    Covers the page dictionary, its content streams (and an indirect
    ``/Contents`` array), an indirect ``/Annots`` array, and an indirect
    ``/Resources`` dictionary with its indirect sub-dictionaries.
    """
    page_xref = doc.page_xref(pno)
    xrefs = [page_xref]
    xrefs += _key_refs(doc, page_xref, "Contents")
    kind, _ = doc.xref_get_key(page_xref, "Contents")
    if kind == "xref":  # indirect array of streams
        for ref in _key_refs(doc, page_xref, "Contents"):
            if not doc.xref_is_stream(ref):
                xrefs += _refs(doc.xref_object(ref, compressed=False))
    kind, _ = doc.xref_get_key(page_xref, "Annots")
    if kind == "xref":
        xrefs += _key_refs(doc, page_xref, "Annots")
    kind, value = doc.xref_get_key(page_xref, "Resources")
    if kind == "xref":
        res = _refs(value)[0]
        xrefs.append(res)
        for sub in ("Font", "XObject", "ExtGState", "Properties"):
            sub_kind, sub_value = doc.xref_get_key(res, sub)
            if sub_kind == "xref":
                xrefs += _refs(sub_value)
    elif kind == "dict":
        for sub in ("Font", "XObject", "ExtGState", "Properties"):
            sub_kind, sub_value = doc.xref_get_key(page_xref, f"Resources/{sub}")
            if sub_kind == "xref":
                xrefs += _refs(sub_value)
    return list(dict.fromkeys(xrefs))


def annot_object_xrefs(doc: pymupdf.Document, annot_xref: int) -> list[int]:
    """Objects that change when one annotation (or form widget) is modified.

    Includes the annotation dictionary, its appearance streams, its popup
    and - for form widgets - the parent field and its sibling widgets, since
    toggling a radio button changes the whole group.
    """
    xrefs = [annot_xref]
    xrefs += _appearance_xrefs(doc, annot_xref)
    xrefs += _key_refs(doc, annot_xref, "Popup")
    parents = _key_refs(doc, annot_xref, "Parent")
    for parent in parents:
        xrefs.append(parent)
        for kid in _key_refs(doc, parent, "Kids"):
            xrefs.append(kid)
            xrefs += _appearance_xrefs(doc, kid)
    return list(dict.fromkeys(xrefs))


def _appearance_xrefs(doc: pymupdf.Document, xref: int) -> list[int]:
    result: list[int] = []
    kind, value = doc.xref_get_key(xref, "AP")
    if kind == "xref":
        ap = _refs(value)[0]
        result.append(ap)
        result += _refs(doc.xref_object(ap, compressed=False))
    elif kind == "dict":
        result += _refs(value)
    # Appearance sub-dictionaries (e.g. /N << /On 12 0 R /Off 13 0 R >>) may
    # themselves be indirect.
    nested: list[int] = []
    for ref in result:
        if not doc.xref_is_stream(ref):
            nested += _refs(doc.xref_object(ref, compressed=False))
    return result + nested
