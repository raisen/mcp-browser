"""Codex TOML: `[mcp_servers.<name>]` tables."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from ..errors import UnsupportedTransport
from ..models import HttpTransport, Scope, ServerEntry, StdioTransport
from ..specs.base import ClientSpec
from . import ParseResult
from .common import (
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

STDIO_KEYS = frozenset({"command", "args", "env", "cwd", "enabled"})
HTTP_KEYS = frozenset({"url", "http_headers", "enabled"})
STDIO_ONLY = frozenset({"command", "args", "env", "cwd", "env_vars"})
HTTP_ONLY = frozenset(
    {
        "url",
        "http_headers",
        "bearer_token_env_var",
        "env_http_headers",
        "oauth",
        "oauth_resource",
        "scopes",
        "auth",
    }
)
DROP = {"stdio": HTTP_ONLY, "http": STDIO_ONLY}


class Codex:
    def parse(self, name: str, raw: dict[str, Any], spec: ClientSpec) -> ParseResult:
        enabled = raw.get("enabled") is not False
        if "command" in raw:
            return read_stdio(raw, None), None, enabled, extra_of(raw, STDIO_KEYS)
        if isinstance(raw.get("url"), str):
            transport = read_remote(raw, "http", raw["url"], "http_headers", None)
            return transport, None, enabled, extra_of(raw, HTTP_KEYS)
        return None, "entry has neither command nor url", enabled, dict(raw)

    def render(self, entry: ServerEntry, existing: dict[str, Any] | None, spec: ClientSpec) -> dict[str, Any]:
        t = entry.transport
        desired: dict[str, Any] = {}
        if isinstance(t, StdioTransport):
            desired.update(stdio_desired(t, None, existing))
        elif isinstance(t, HttpTransport):
            desired.update(remote_desired(t, "url", "http_headers", None, existing))
        elif t is not None:
            raise UnsupportedTransport("Codex does not support SSE servers")
        flag_desired(desired, "enabled", existing, entry.enabled, invert=False)
        old = self.parse(entry.name, existing, spec)[0] if existing else None
        return merge(existing, desired, entry.extra, strip_keys(old, t, STDIO_KEYS | HTTP_KEYS, DROP))

    def root(
        self, doc: Any, spec: ClientSpec, scope: Scope, project: str | None, create: bool
    ) -> MutableMapping[str, Any] | None:
        return standard_root(doc, spec, scope, project, create)
