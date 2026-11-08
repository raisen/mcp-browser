"""Data models and Textual messages for the MCP Browser TUI."""

from __future__ import annotations

from typing import Any, Literal

from mcp_browser_core.catalog_models import CatalogEntry, ToolInfo
from mcp_browser_core.models import ServerEntry
from textual.message import Message

ServerBadge = Literal["connected", "idle", "untrusted", "error", "connecting"]

BADGE_SYMBOLS: dict[ServerBadge, str] = {
    "connected": "●",
    "idle": "○",
    "untrusted": "▲",
    "error": "✖",
    "connecting": "◌",
}

BADGE_STYLES: dict[ServerBadge, str] = {
    "connected": "green",
    "idle": "dim",
    "untrusted": "yellow",
    "error": "red",
    "connecting": "cyan",
}


def entry_status(entry: ServerEntry, catalog: CatalogEntry | None) -> ServerBadge:
    """Compute the visual status badge for a server entry."""
    if entry.untrusted and (catalog is None or catalog.status != "ok"):
        return "untrusted"
    if entry.error is not None:
        return "error"
    if catalog is not None:
        if catalog.status == "ok":
            return "connected"
        if catalog.status == "error":
            return "error"
        if catalog.status == "needs_auth":
            return "untrusted"
    return "idle"


class ServerSelected(Message):
    """User selected a server in the sidebar tree or list."""

    def __init__(self, entry: ServerEntry) -> None:
        super().__init__()
        self.entry = entry


class ToolSelected(Message):
    """User selected a tool in the tools list."""

    def __init__(self, tool: ToolInfo) -> None:
        super().__init__()
        self.tool = tool


class ConnectRequested(Message):
    """User requested to connect/scan the currently selected server."""

    def __init__(self, entry: ServerEntry) -> None:
        super().__init__()
        self.entry = entry


class RunToolRequested(Message):
    """User triggered execution of a tool."""

    def __init__(self, tool_name: str, args: dict[str, Any]) -> None:
        super().__init__()
        self.tool_name = tool_name
        self.args = args


class ReadResourceRequested(Message):
    """User requested to read a resource URI."""

    def __init__(self, uri: str) -> None:
        super().__init__()
        self.uri = uri


class GetPromptRequested(Message):
    """User requested to get a prompt with arguments."""

    def __init__(self, prompt_name: str, args: dict[str, str]) -> None:
        super().__init__()
        self.prompt_name = prompt_name
        self.args = args
