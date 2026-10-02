"""Form fields (AcroForm widgets): list, fill and flatten."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import pymupdf

from ..errors import InvalidInput, UnsupportedOperation

KIND_NAMES = {
    pymupdf.PDF_WIDGET_TYPE_TEXT: "text",
    pymupdf.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
    pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON: "radio",
    pymupdf.PDF_WIDGET_TYPE_COMBOBOX: "combobox",
    pymupdf.PDF_WIDGET_TYPE_LISTBOX: "listbox",
    pymupdf.PDF_WIDGET_TYPE_BUTTON: "button",
    pymupdf.PDF_WIDGET_TYPE_SIGNATURE: "signature",
}
READ_ONLY_FLAG = pymupdf.PDF_FIELD_IS_READ_ONLY


@dataclass
class FieldInfo:
    """A summary of one form widget."""

    page: int
    xref: int
    name: str
    kind: str
    value: str | bool
    rect: pymupdf.Rect
    options: list[str] = field(default_factory=list)
    on_state: str | None = None
    read_only: bool = False
    multiline: bool = False


def _info(page: pymupdf.Page, widget: pymupdf.Widget) -> FieldInfo:
    kind = KIND_NAMES.get(widget.field_type, "unknown")
    value: str | bool = widget.field_value
    on_state = None
    if kind in ("checkbox", "radio"):
        on_state = widget.on_state()
        value = value not in (None, "", "Off", False)
    options = []
    for choice in widget.choice_values or []:
        options.append(choice[0] if isinstance(choice, (list, tuple)) else str(choice))
    return FieldInfo(
        page.number, widget.xref, widget.field_name or "", kind, value if value is not None else "",
        pymupdf.Rect(widget.rect), options, on_state, bool(widget.field_flags & READ_ONLY_FLAG),
        bool(widget.field_flags & pymupdf.PDF_TX_FIELD_IS_MULTILINE) if kind == "text" else False,
    )


def list_fields(doc: pymupdf.Document, pages: Sequence[int] | None = None) -> list[FieldInfo]:
    """All form widgets, in page order."""
    result = []
    for pno in range(doc.page_count) if pages is None else pages:
        page = doc[pno]
        for widget in page.widgets():
            result.append(_info(page, widget))
    return result


def field_at(page: pymupdf.Page, point: Sequence[float]) -> FieldInfo | None:
    """The form widget under ``point``."""
    p = pymupdf.Point(point)
    for widget in page.widgets():
        if widget.rect.contains(p):
            return _info(page, widget)
    return None


def _widget(page: pymupdf.Page, xref: int) -> pymupdf.Widget:
    for widget in page.widgets():
        if widget.xref == xref:
            return widget
    raise InvalidInput("That form field no longer exists.")


def set_field_value(doc: pymupdf.Document, pno: int, xref: int, value: str | bool) -> None:
    """Fill a field. Checkboxes/radios take a bool; choice fields an option text."""
    page = doc[pno]
    widget = _widget(page, xref)
    kind = KIND_NAMES.get(widget.field_type, "unknown")
    if widget.field_flags & READ_ONLY_FLAG:
        raise InvalidInput(f"The field '{widget.field_name}' is read-only.")
    if kind in ("button", "signature", "unknown"):
        raise UnsupportedOperation(f"{kind.capitalize()} fields cannot be filled here.")
    if kind in ("checkbox", "radio"):
        on = bool(value)
        widget.field_value = widget.on_state() if on else "Off"
        widget.update()
        _fix_button_value(doc, xref, widget.on_state() if on else "Off")
        return
    if kind in ("combobox", "listbox"):
        options = [c[0] if isinstance(c, (list, tuple)) else str(c) for c in widget.choice_values or []]
        editable = kind == "combobox" and widget.field_flags & pymupdf.PDF_CH_FIELD_IS_EDIT
        if str(value) not in options and not editable:
            raise InvalidInput(f"'{value}' is not one of the choices for '{widget.field_name}'.")
    if str(value) == "":
        # PyMuPDF ignores empty strings, so clear /V directly and let update()
        # regenerate the (now empty) appearance.
        doc.xref_set_key(_value_holder(doc, xref), "V", "()")
        widget = _widget(doc[pno], xref)
        widget.update()
        return
    widget.field_value = str(value)
    widget.update()


def _value_holder(doc: pymupdf.Document, xref: int) -> int:
    """The object holding the field's /V: the widget itself or its parent field."""
    kind, value = doc.xref_get_key(xref, "Parent")
    has_name = doc.xref_get_key(xref, "T")[0] != "null"
    return int(value.split()[0]) if kind == "xref" and not has_name else xref


def _fix_button_value(doc: pymupdf.Document, xref: int, state: str) -> None:
    """Store /V as a PDF name (some viewers ignore string values on buttons)."""
    doc.xref_set_key(_value_holder(doc, xref), "V", f"/{state}")


def reset_field(doc: pymupdf.Document, pno: int, xref: int) -> None:
    """Clear a field: empty text, unchecked buttons, default (or first) choice."""
    page = doc[pno]
    widget = _widget(page, xref)
    kind = KIND_NAMES.get(widget.field_type, "unknown")
    if kind in ("checkbox", "radio"):
        set_field_value(doc, pno, xref, False)
    elif kind in ("combobox", "listbox"):
        options = [c[0] if isinstance(c, (list, tuple)) else str(c) for c in widget.choice_values or []]
        dv_kind, default = doc.xref_get_key(xref, "DV")
        value = default if dv_kind == "string" and default in options else (options[0] if options else "")
        set_field_value(doc, pno, xref, value)
    elif kind == "text":
        set_field_value(doc, pno, xref, "")


def flatten_forms(doc: pymupdf.Document) -> int:
    """Turn all form fields into static page content; returns how many were flattened."""
    count = sum(1 for pno in range(doc.page_count) for _ in doc[pno].widgets())
    if count:
        doc.bake(annots=False, widgets=True)
    return count
