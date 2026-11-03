"""Request/response models of the HTTP API. Frozen by Wave 0; the UI codes against these shapes."""

from __future__ import annotations

from typing import Any

from mcp_browser_core.catalog_models import CatalogEntry
from mcp_browser_core.models import (
    AddResult,
    EntryPatch,
    NewEntry,
    ServerEntry,
    Target,
    Transport,
    WriteReport,
)
from pydantic import BaseModel, Field

__all__ = [
    "AddRequest",
    "AddResult",
    "CallRequest",
    "ConnectRequest",
    "ErrorBody",
    "GetPromptRequest",
    "HealthResponse",
    "ReadResourceRequest",
    "ScanRequest",
    "ServerDetail",
    "ServersResponse",
    "UpdateRequest",
    "WriteReport",
]


class HealthResponse(BaseModel):
    ok: bool = True
    version: str
    pid: int


class ErrorBody(BaseModel):
    error: str
    message: str
    detail: dict[str, Any] = {}


class ServersResponse(BaseModel):
    entries: list[ServerEntry]  # masked
    catalog: list[CatalogEntry]
    warnings: list[str] = []


class ServerDetail(BaseModel):
    entry: ServerEntry  # masked; unmasked on /reveal
    catalog: CatalogEntry | None = None


class AddRequest(BaseModel):
    name: str
    transport: Transport
    extra: dict[str, Any] = {}
    targets: list[Target] = Field(min_length=1)
    allow_comment_loss: bool = False

    def to_new_entry(self) -> NewEntry:
        return NewEntry(name=self.name, transport=self.transport, extra=self.extra)


class UpdateRequest(BaseModel):
    name: str | None = None
    transport: Transport | None = None
    extra: dict[str, Any] | None = None
    allow_comment_loss: bool = False

    def to_patch(self) -> EntryPatch:
        return EntryPatch(name=self.name, transport=self.transport, extra=self.extra)


class Confirmable(BaseModel):
    """Per-request consent for entries that came from a project config file (never stored)."""

    confirm_untrusted: bool = False


class ConnectRequest(Confirmable):
    connect_timeout: float | None = None


class ScanRequest(Confirmable):
    ids: list[str] | None = None


class CallRequest(Confirmable):
    arguments: dict[str, Any] = {}
    call_timeout: float | None = None


class ReadResourceRequest(Confirmable):
    uri: str


class GetPromptRequest(Confirmable):
    arguments: dict[str, str] = {}
