"""Dialects translate between a client's native entry shape and the normalized models."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, Protocol

from ..models import Scope, ServerEntry, Transport
from ..specs.base import ClientSpec

ParseResult = tuple[Transport | None, str | None, bool, dict[str, Any]]
"""(transport, error, enabled, extra)"""


class Dialect(Protocol):
    def parse(self, name: str, raw: dict[str, Any], spec: ClientSpec) -> ParseResult: ...

    def render(self, entry: ServerEntry, existing: dict[str, Any] | None, spec: ClientSpec) -> dict[str, Any]:
        """Merge onto existing (or {}): drop other transport kinds' keys, set mapped keys, keep extra."""
        ...

    def root(
        self, doc: Any, spec: ClientSpec, scope: Scope, project: str | None, create: bool
    ) -> MutableMapping[str, Any] | None:
        """The mapping holding server entries; creates the key chain only when create=True."""
        ...


def get_dialect(name: str) -> Dialect:
    """Dialect instance by name (modules are imported lazily; they import this package)."""
    from .codex import Codex
    from .gemini import Gemini
    from .mcpservers_json import McpServersJson
    from .readonly import ReadOnlyDialect
    from .vscode import VsCode
    from .zed import Zed

    table: dict[str, Dialect] = {
        "mcpservers_json": McpServersJson(),
        "codex": Codex(),
        "gemini": Gemini(),
        "vscode": VsCode(),
        "zed": Zed(),
        "readonly": ReadOnlyDialect(),
    }
    if name not in table:
        raise KeyError(f"unknown dialect: {name}")
    return table[name]
