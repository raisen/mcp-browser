"""mcp-browser core: discovery, safe config rewriting and the MCP client layer."""

from __future__ import annotations

from .catalog_models import CallResult, CatalogEntry, PromptInfo, ResourceInfo, ToolInfo
from .models import (
    AddResult,
    Capabilities,
    ClientInfo,
    ConfigFileInfo,
    DiscoveryResult,
    EntryPatch,
    Format,
    HttpTransport,
    NewEntry,
    Platform,
    Scope,
    ServerEntry,
    SseTransport,
    StdioTransport,
    Target,
    Transport,
    WriteReport,
    fingerprint,
    make_entry_id,
)

__version__ = "0.1.0"

__all__ = [
    "AddResult",
    "CallResult",
    "Capabilities",
    "CatalogEntry",
    "ClientInfo",
    "ConfigFileInfo",
    "DiscoveryResult",
    "EntryPatch",
    "Format",
    "HttpTransport",
    "NewEntry",
    "Platform",
    "PromptInfo",
    "ResourceInfo",
    "Scope",
    "ServerEntry",
    "SseTransport",
    "StdioTransport",
    "Target",
    "ToolInfo",
    "Transport",
    "WriteReport",
    "__version__",
    "fingerprint",
    "make_entry_id",
]
