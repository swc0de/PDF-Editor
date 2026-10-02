"""Interactive viewer tools and the registry that creates them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .annotate_tools import (
    ArrowTool,
    EllipseTool,
    HighlightTool,
    LineTool,
    NoteTool,
    PenTool,
    RectangleTool,
    StampTool,
    StrikeoutTool,
    TextBoxTool,
    UnderlineTool,
)
from .base import PageEvent, Tool
from .content_tools import AddTextTool, EditTextTool, ImageTool, SignatureTool
from .crop_tool import CropTool
from .redact_tool import RedactTool
from .select_tool import SelectTool
from .text_select import HandTool

if TYPE_CHECKING:  # pragma: no cover
    from ..document_tab import DocumentTab

TOOL_CLASSES: dict[str, type[Tool]] = {
    cls.name: cls
    for cls in (
        SelectTool, HandTool, CropTool, HighlightTool, UnderlineTool, StrikeoutTool, PenTool,
        RectangleTool, EllipseTool, LineTool, ArrowTool, NoteTool, TextBoxTool, StampTool,
        AddTextTool, EditTextTool, ImageTool, SignatureTool, RedactTool,
    )
}


def create_tool(name: str, tab: "DocumentTab") -> Tool:
    """Instantiate the tool registered under ``name`` for ``tab``."""
    try:
        return TOOL_CLASSES[name](tab)
    except KeyError:
        raise ValueError(f"Unknown tool '{name}'") from None


__all__ = ["PageEvent", "Tool", "TOOL_CLASSES", "create_tool"]
