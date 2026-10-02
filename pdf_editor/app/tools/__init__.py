"""Interactive viewer tools and the registry that creates them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import PageEvent, Tool
from .crop_tool import CropTool
from .text_select import HandTool, TextSelectTool

if TYPE_CHECKING:  # pragma: no cover
    from ..document_tab import DocumentTab

TOOL_CLASSES: dict[str, type[Tool]] = {
    "select": TextSelectTool,
    "hand": HandTool,
    "crop": CropTool,
}


def create_tool(name: str, tab: "DocumentTab") -> Tool:
    """Instantiate the tool registered under ``name`` for ``tab``."""
    try:
        return TOOL_CLASSES[name](tab)
    except KeyError:
        raise ValueError(f"Unknown tool '{name}'") from None


__all__ = ["PageEvent", "Tool", "TOOL_CLASSES", "create_tool"]
