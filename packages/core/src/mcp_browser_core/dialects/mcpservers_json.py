"""`mcpServers` JSON: Claude Code and Desktop, Cursor, Antigravity, Windsurf, Cline."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from ..models import Scope, ServerEntry, StdioTransport
from ..specs.base import ClientSpec
from . import ParseResult
from .common import (
    HTTP_TYPES,
    Kind,
    declared_kind,
    extra_of,
    flag_desired,
    merge,
    read_remote,
    read_stdio,
    remote_desired,
    standard_root,
    stdio_desired,
    strip_keys,
)

URLS = ("url", "serverUrl")
STDIO_KEYS = frozenset({"type", "command", "args", "env", "cwd", "envFile", "disabled"})
REMOTE_KEYS = frozenset({"type", "url", "serverUrl", "headers", "oauth", "disabled"})
_COMMAND_ONLY = frozenset({"command", "args", "env", "cwd", "envFile"})
DROP = {
    "stdio": frozenset({"url", "serverUrl", "headers", "oauth", "headersHelper"}),
    "http": _COMMAND_ONLY,
    "sse": _COMMAND_ONLY,
}


def _write_type(kind: Kind, style: str) -> str:
    if kind == "stdio":
        return "stdio"
    if style == "cline":
        return "streamableHttp" if kind == "http" else "sse"
    return kind


class McpServersJson:
    def parse(self, name: str, raw: dict[str, Any], spec: ClientSpec) -> ParseResult:
        enabled = raw.get("disabled") is not True
        declared = raw.get("type")
        if declared in ("ws", "websocket"):
            return None, "websocket transport is not supported", enabled, dict(raw)
        if "command" in raw and declared not in HTTP_TYPES and declared != "sse":
            return read_stdio(raw), None, enabled, extra_of(raw, STDIO_KEYS)
        url = next((raw[k] for k in (spec.url_key, *URLS) if isinstance(raw.get(k), str)), None)
        if url is None:
            return None, "entry has neither command nor url", enabled, dict(raw)
        kind: Kind = "sse" if declared == "sse" else "http"
        return read_remote(raw, kind, url), None, enabled, extra_of(raw, REMOTE_KEYS)

    def render(self, entry: ServerEntry, existing: dict[str, Any] | None, spec: ClientSpec) -> dict[str, Any]:
        t = entry.transport
        desired: dict[str, Any] = {}
        if t is not None:
            kind: Kind = t.kind
            if existing is None:
                wants_type = spec.type_style != "none"
            else:  # an existing entry only gets a type when it has one, or just turned into a url entry
                wants_type = "type" in existing or (kind != "stdio" and "command" in existing)
            if wants_type:
                old = existing.get("type") if existing else None
                keep = declared_kind(old) == kind
                desired["type"] = old if keep else _write_type(kind, spec.type_style)
            if isinstance(t, StdioTransport):
                desired.update(stdio_desired(t, existing=existing))
            else:
                key = next((k for k in URLS if existing and k in existing), spec.url_key)
                desired.update(remote_desired(t, key, existing=existing))
        flag_desired(desired, "disabled", existing, entry.enabled, invert=True)
        old = self.parse(entry.name, existing, spec)[0] if existing else None
        return merge(existing, desired, entry.extra, strip_keys(old, t, STDIO_KEYS | REMOTE_KEYS, DROP))

    def root(
        self, doc: Any, spec: ClientSpec, scope: Scope, project: str | None, create: bool
    ) -> MutableMapping[str, Any] | None:
        return standard_root(doc, spec, scope, project, create)
