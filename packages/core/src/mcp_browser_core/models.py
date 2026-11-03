"""Core pydantic models shared by every package. Frozen by Wave 0."""

from __future__ import annotations

import hashlib
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

Scope = Literal["user", "local", "project", "plugin", "extension"]
Format = Literal["json", "jsonc", "toml"]
Platform = Literal["darwin", "win32", "linux"]


class StdioTransport(BaseModel):
    kind: Literal["stdio"] = "stdio"
    command: str
    args: list[str] = []
    env: dict[str, str] = {}
    cwd: str | None = None
    env_file: str | None = None  # Cursor / VS Code envFile


class HttpTransport(BaseModel):
    kind: Literal["http"] = "http"  # streamable HTTP
    url: str
    headers: dict[str, str] = {}
    oauth: dict[str, Any] | None = None


class SseTransport(BaseModel):
    kind: Literal["sse"] = "sse"
    url: str
    headers: dict[str, str] = {}
    oauth: dict[str, Any] | None = None


Transport = Annotated[StdioTransport | HttpTransport | SseTransport, Field(discriminator="kind")]


def make_entry_id(client_id: str, scope: str, config_path: str, name: str) -> str:
    """Stable id of a server entry: blake2b over client, scope, file and name."""
    return hashlib.blake2b(f"{client_id}|{scope}|{config_path}|{name}".encode(), digest_size=8).hexdigest()


def fingerprint(transport: StdioTransport | HttpTransport | SseTransport | None) -> str:
    """Cache key of a transport; changes whenever anything that affects connecting changes."""
    data = transport.model_dump_json().encode() if transport else b""
    return hashlib.blake2b(data, digest_size=8).hexdigest()


class Capabilities(BaseModel):
    stdio: bool = True
    http: bool = True
    sse: bool = True
    project_scope: bool
    editable: bool = True


class ConfigFileInfo(BaseModel):
    path: str
    exists: bool
    scope: Scope
    format: Format
    project: str | None = None
    has_comments: bool = False


class ClientInfo(BaseModel):
    id: str
    display_name: str
    config_paths: list[ConfigFileInfo]
    capabilities: Capabilities
    needs_restart: bool = False


class ServerEntry(BaseModel):
    id: str
    name: str
    client_id: str
    scope: Scope
    config_path: str  # absolute path of the file it came from
    project: str | None = None  # project dir (verbatim key) for project/local scope
    transport: Transport | None = None  # None when unparseable (e.g. type:"ws")
    error: str | None = None  # why transport is None
    enabled: bool = True  # mirrors disabled/enabled fields, read-only in UI
    extra: dict[str, Any] = {}  # every native field not mapped above, kept verbatim
    read_only: bool = False
    read_only_reason: str | None = None
    untrusted: bool = False  # project scope: repo-provided config, needs per-request confirmation


class DiscoveryResult(BaseModel):
    entries: list[ServerEntry]
    clients: list[ClientInfo]
    projects: list[str]
    warnings: list[str]


class Target(BaseModel):
    """Where an add writes: one client, scope and (for project/local scope) project key."""

    client_id: str
    scope: Scope
    project: str | None = None


class NewEntry(BaseModel):
    name: str
    transport: Transport
    extra: dict[str, Any] = {}


class EntryPatch(BaseModel):
    """Partial update; omitted fields are left alone."""

    name: str | None = None
    transport: Transport | None = None
    extra: dict[str, Any] | None = None


class WriteReport(BaseModel):
    path: str
    backup_path: str | None  # None when the file did not exist before
    created_file: bool
    entry: ServerEntry


class AddResult(BaseModel):
    target: Target
    report: WriteReport | None = None
    error: str | None = None
