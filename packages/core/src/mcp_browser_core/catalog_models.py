"""Models for what a connected MCP server exposes. Frozen by Wave 0."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ToolInfo(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any] = {}


class ResourceInfo(BaseModel):
    uri: str
    name: str | None = None
    mime_type: str | None = None
    description: str | None = None


class PromptInfo(BaseModel):
    name: str
    description: str | None = None
    arguments: list[dict[str, Any]] = []


class CatalogEntry(BaseModel):
    entry_id: str
    fingerprint: str  # models.fingerprint(entry.transport)
    scanned_at: datetime
    tools: list[ToolInfo] = []
    resources: list[ResourceInfo] = []
    prompts: list[PromptInfo] = []
    status: Literal["ok", "error", "needs_auth"]
    error: str | None = None
    stderr_tail: str | None = None


class CallResult(BaseModel):
    content: list[dict[str, Any]]
    structured: dict[str, Any] | None = None
    is_error: bool = False
    duration_ms: int = 0
    stderr_tail: str | None = None
    truncated: bool = False  # result was cut at the 10 MB cap
