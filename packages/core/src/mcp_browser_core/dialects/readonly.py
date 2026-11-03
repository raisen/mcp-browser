"""Read-only sources: Claude Code plugins and Claude Desktop extensions."""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, cast

from ..errors import ReadOnly
from ..models import Scope, ServerEntry, make_entry_id
from ..paths import Paths
from ..specs.base import ClientSpec
from ..specs.claude import CLAUDE_CODE
from . import ParseResult
from .common import as_dict
from .mcpservers_json import McpServersJson

_JSON = McpServersJson()


def _substitute(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, str):
        for key, replacement in mapping.items():
            value = value.replace(key, replacement)
        return value
    if isinstance(value, list):
        return [_substitute(v, mapping) for v in cast("list[Any]", value)]
    if isinstance(value, dict):
        return {k: _substitute(v, mapping) for k, v in as_dict(value).items()}
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return as_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def _entry(name: str, raw: Any, path: Path, spec: ClientSpec, mapping: dict[str, str]) -> ServerEntry:
    transport, error, enabled, extra = _JSON.parse(name, _substitute(as_dict(raw), mapping), CLAUDE_CODE)
    if error is None and "${user_config." in (transport.model_dump_json() if transport else ""):
        error = "needs user configuration values that are not resolved here (${user_config.*})"
    return ServerEntry(
        id=make_entry_id(spec.id, spec.user_paths[0].scope, str(path), name),
        name=name,
        client_id=spec.id,
        scope=spec.user_paths[0].scope,
        config_path=str(path),
        transport=transport,
        error=error,
        enabled=enabled,
        extra=extra,
        read_only=True,
        read_only_reason=spec.read_only_reason,
    )


def _plugin_servers(install: Path) -> list[tuple[Path, dict[str, Any]]]:
    found: list[tuple[Path, dict[str, Any]]] = []
    mcp = install / ".mcp.json"
    data = _read_json(mcp)
    if data:
        servers = as_dict(data.get("mcpServers")) or {k: v for k, v in data.items() if isinstance(v, dict)}
        found.append((mcp, servers))
    for manifest in (install / ".claude-plugin" / "plugin.json", install / "plugin.json"):
        inline = as_dict(_read_json(manifest).get("mcpServers"))
        if inline:
            found.append((manifest, inline))
    return found


def _plugins(path: Path, doc: dict[str, Any], spec: ClientSpec) -> list[ServerEntry]:
    out: list[ServerEntry] = []
    for installs in as_dict(doc.get("plugins")).values():
        records = cast("list[Any]", installs) if isinstance(installs, list) else [installs]
        for record in records:
            root = as_dict(record).get("installPath")
            if not isinstance(root, str):
                continue
            mapping = {"${CLAUDE_PLUGIN_ROOT}": root, "${__dirname}": root}
            for source, servers in _plugin_servers(Path(root)):
                out.extend(_entry(n, raw, source, spec, mapping) for n, raw in servers.items())
    return out


def _extension(path: Path, doc: dict[str, Any], spec: ClientSpec, paths: Paths) -> list[ServerEntry]:
    config = as_dict(as_dict(doc.get("server")).get("mcp_config"))
    override = as_dict(as_dict(config.get("platforms")).get(paths.platform))
    merged = {k: v for k, v in config.items() if k != "platforms"} | override
    if not merged:
        return []
    name = str(doc.get("name") or path.parent.name)
    return [_entry(name, merged, path, spec, {"${__dirname}": str(path.parent)})]


def collect(path: Path, doc: Any, spec: ClientSpec, paths: Paths) -> list[ServerEntry]:
    """Entries found through one plugin registry or extension manifest (`doc` is plain JSON)."""
    data = as_dict(doc)
    if spec.id == "claude-code-plugins":
        return _plugins(path, data, spec)
    return _extension(path, data, spec, paths)


class ReadOnlyDialect:
    def parse(self, name: str, raw: dict[str, Any], spec: ClientSpec) -> ParseResult:
        return _JSON.parse(name, raw, CLAUDE_CODE)

    def render(self, entry: ServerEntry, existing: dict[str, Any] | None, spec: ClientSpec) -> dict[str, Any]:
        raise ReadOnly(spec.read_only_reason or "this source is read-only")

    def root(
        self, doc: Any, spec: ClientSpec, scope: Scope, project: str | None, create: bool
    ) -> MutableMapping[str, Any] | None:
        return None
