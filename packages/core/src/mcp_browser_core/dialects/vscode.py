"""VS Code `mcp.json`: root key `servers`, explicit `type`; sibling `inputs` is never touched."""

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
    merge,
    read_remote,
    read_stdio,
    remote_desired,
    standard_root,
    stdio_desired,
    strip_keys,
)

STDIO_KEYS = frozenset({"type", "command", "args", "cwd", "env", "envFile"})
REMOTE_KEYS = frozenset({"type", "url", "headers", "oauth"})
DROP = {
    "stdio": frozenset({"url", "headers", "oauth"}),
    "http": frozenset({"command", "args", "cwd", "env", "envFile"}),
    "sse": frozenset({"command", "args", "cwd", "env", "envFile"}),
}


class VsCode:
    def parse(self, name: str, raw: dict[str, Any], spec: ClientSpec) -> ParseResult:
        declared = raw.get("type")
        if declared in ("ws", "websocket"):
            return None, "websocket transport is not supported", True, dict(raw)
        if "command" in raw and declared not in (*HTTP_TYPES, "sse"):
            return read_stdio(raw), None, True, extra_of(raw, STDIO_KEYS)
        if isinstance(raw.get("url"), str):
            kind: Kind = "sse" if declared == "sse" else "http"
            return read_remote(raw, kind, raw["url"]), None, True, extra_of(raw, REMOTE_KEYS)
        return None, "entry has neither command nor url", True, dict(raw)

    def render(self, entry: ServerEntry, existing: dict[str, Any] | None, spec: ClientSpec) -> dict[str, Any]:
        t = entry.transport
        desired: dict[str, Any] = {}
        if t is not None:
            old = existing.get("type") if existing else None
            desired["type"] = old if declared_kind(old) == t.kind else t.kind
            if isinstance(t, StdioTransport):
                desired.update(stdio_desired(t, existing=existing))
            else:
                desired.update(remote_desired(t, "url", existing=existing))
        old = self.parse(entry.name, existing, spec)[0] if existing else None
        return merge(existing, desired, entry.extra, strip_keys(old, t, STDIO_KEYS | REMOTE_KEYS, DROP))

    def root(
        self, doc: Any, spec: ClientSpec, scope: Scope, project: str | None, create: bool
    ) -> MutableMapping[str, Any] | None:
        return standard_root(doc, spec, scope, project, create)
