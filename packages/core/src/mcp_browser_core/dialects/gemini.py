"""Gemini CLI `settings.json`: `httpUrl` is streamable HTTP, `url` is SSE; no `type` field."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from ..models import Scope, ServerEntry, StdioTransport
from ..specs.base import ClientSpec
from . import ParseResult
from .common import (
    extra_of,
    merge,
    read_remote,
    read_stdio,
    remote_desired,
    standard_root,
    stdio_desired,
    strip_keys,
)

STDIO_KEYS = frozenset({"command", "args", "env", "cwd"})
HTTP_KEYS = frozenset({"httpUrl", "headers", "oauth"})
SSE_KEYS = frozenset({"url", "headers", "oauth"})
REMOTE_ONLY = frozenset(
    {
        "httpUrl",
        "url",
        "headers",
        "oauth",
        "tcp",
        "authProviderType",
        "targetAudience",
        "targetServiceAccount",
    }
)
DROP = {
    "stdio": REMOTE_ONLY,
    "http": frozenset({"command", "args", "env", "cwd", "url", "tcp"}),
    "sse": frozenset({"command", "args", "env", "cwd", "httpUrl", "tcp"}),
}


class Gemini:
    def parse(self, name: str, raw: dict[str, Any], spec: ClientSpec) -> ParseResult:
        if "command" in raw:
            return read_stdio(raw, None), None, True, extra_of(raw, STDIO_KEYS)
        if isinstance(raw.get("httpUrl"), str):
            return read_remote(raw, "http", raw["httpUrl"]), None, True, extra_of(raw, HTTP_KEYS)
        if isinstance(raw.get("url"), str):
            return read_remote(raw, "sse", raw["url"]), None, True, extra_of(raw, SSE_KEYS)
        return None, "entry has neither command nor url", True, dict(raw)

    def render(self, entry: ServerEntry, existing: dict[str, Any] | None, spec: ClientSpec) -> dict[str, Any]:
        t = entry.transport
        desired: dict[str, Any] = {}
        if isinstance(t, StdioTransport):
            desired.update(stdio_desired(t, None, existing))
        elif t is not None:
            desired.update(remote_desired(t, "httpUrl" if t.kind == "http" else "url", existing=existing))
        old = self.parse(entry.name, existing, spec)[0] if existing else None
        mapped = STDIO_KEYS | HTTP_KEYS | SSE_KEYS
        return merge(existing, desired, entry.extra, strip_keys(old, t, mapped, DROP))

    def root(
        self, doc: Any, spec: ClientSpec, scope: Scope, project: str | None, create: bool
    ) -> MutableMapping[str, Any] | None:
        return standard_root(doc, spec, scope, project, create)
