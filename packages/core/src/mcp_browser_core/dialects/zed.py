"""Zed `settings.json`: `context_servers`, `source: "custom"` on entries we add."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from ..errors import UnsupportedTransport
from ..models import Scope, ServerEntry, StdioTransport
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

STDIO_KEYS = frozenset({"command", "args", "env", "enabled"})
REMOTE_KEYS = frozenset({"url", "headers", "enabled"})
DROP = {"stdio": frozenset({"url", "headers", "oauth"}), "http": frozenset({"command", "args", "env", "cwd"})}


class Zed:
    def parse(self, name: str, raw: dict[str, Any], spec: ClientSpec) -> ParseResult:
        enabled = raw.get("enabled") is not False
        command = raw.get("command")
        if isinstance(command, str):
            return read_stdio(raw, None), None, enabled, extra_of(raw, STDIO_KEYS)
        if command is not None:
            return None, "legacy nested command form is not supported", enabled, dict(raw)
        if isinstance(raw.get("url"), str):
            return (
                read_remote(raw, "http", raw["url"], oauth_key=None),
                None,
                enabled,
                extra_of(raw, REMOTE_KEYS),
            )
        return None, "entry has neither command nor url", enabled, dict(raw)

    def render(self, entry: ServerEntry, existing: dict[str, Any] | None, spec: ClientSpec) -> dict[str, Any]:
        t = entry.transport
        desired: dict[str, Any] = {}
        if existing is None and "source" not in entry.extra:
            desired["source"] = "custom"
        if isinstance(t, StdioTransport):
            if t.cwd and existing is None:
                raise UnsupportedTransport("Zed has no working-directory (cwd) setting for stdio servers")
            desired.update(stdio_desired(t, None, existing))
            desired.pop("cwd", None)  # an existing raw cwd stays through `extra`
        elif t is not None:
            if t.kind != "http":
                raise UnsupportedTransport("Zed does not support SSE servers")
            desired.update(remote_desired(t, "url", oauth_key=None, existing=existing))
        flag_desired(desired, "enabled", existing, entry.enabled, invert=False)
        old = self.parse(entry.name, existing, spec)[0] if existing else None
        return merge(existing, desired, entry.extra, strip_keys(old, t, STDIO_KEYS | REMOTE_KEYS, DROP))

    def root(
        self, doc: Any, spec: ClientSpec, scope: Scope, project: str | None, create: bool
    ) -> MutableMapping[str, Any] | None:
        return standard_root(doc, spec, scope, project, create)
