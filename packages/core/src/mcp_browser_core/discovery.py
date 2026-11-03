"""Read-only discovery of server entries across all client specs."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from .dialects import get_dialect
from .dialects.readonly import collect
from .formats import has_comments, load, plain
from .models import ClientInfo, ConfigFileInfo, DiscoveryResult, Scope, ServerEntry, make_entry_id
from .paths import Paths
from .specs import REGISTRY
from .specs.base import ClientSpec


def entry_id(client_id: str, scope: Scope, path: str, project: str | None, name: str) -> str:
    """Entry id; local scope mixes the project key in because one file holds many projects."""
    return make_entry_id(
        client_id, scope, f"{path}#{project}" if scope == "local" and project else path, name
    )


def user_files(paths: Paths, spec: ClientSpec) -> list[Path]:
    """Candidate user-scope files for the platform. Globs yield existing matches only."""
    return [p for rule in spec.user_paths for p in paths.candidates(rule)]


def active_user_file(paths: Paths, spec: ClientSpec) -> Path | None:
    """First existing candidate, else the first one (where a new file would be created)."""
    files = user_files(paths, spec)
    return next((p for p in files if p.exists()), files[0] if files else None)


def project_file(spec: ClientSpec, project: Path) -> Path | None:
    """The project config to read or create: first existing, else the first project path."""
    files = [project / rel for rel in spec.project_paths]
    return next((p for p in files if p.exists()), files[0] if files else None)


def _entries_of(
    doc: Any, spec: ClientSpec, scope: Scope, path: Path, project: str | None, warnings: list[str]
) -> list[ServerEntry]:
    dialect = get_dialect(spec.dialect)
    root = dialect.root(doc, spec, scope, project, False)
    out: list[ServerEntry] = []
    for name, raw in (root or {}).items():
        if not isinstance(raw, dict):
            warnings.append(f"{path}: entry {name!r} is not an object")
            continue
        transport, error, enabled, extra = dialect.parse(str(name), cast("dict[str, Any]", plain(raw)), spec)
        out.append(
            ServerEntry(
                id=entry_id(spec.id, scope, str(path), project, str(name)),
                name=str(name),
                client_id=spec.id,
                scope=scope,
                config_path=str(path),
                project=project,
                transport=transport,
                error=error,
                enabled=enabled,
                extra=extra,
                untrusted=scope == "project",
            )
        )
    return out


def _local_projects(doc: Any, spec: ClientSpec) -> list[str]:
    projects: Any = (
        cast("dict[str, Any]", doc).get(spec.local_projects_key or "") if isinstance(doc, dict) else None
    )
    return [str(k) for k in cast("dict[str, Any]", projects)] if isinstance(projects, dict) else []


def _disabled_names(doc: Any, spec: ClientSpec, key: str) -> set[str]:
    """`disabledMcpjsonServers` of one project block in Claude Code's `.claude.json`."""
    block: Any = cast("dict[str, Any]", doc)[spec.local_projects_key or ""].get(key)
    names: Any = (
        cast("dict[str, Any]", block).get("disabledMcpjsonServers") if isinstance(block, dict) else None
    )
    return {str(n) for n in cast("list[Any]", names)} if isinstance(names, list) else set()


def discover(paths: Paths, specs: Mapping[str, ClientSpec] = REGISTRY) -> DiscoveryResult:
    entries: list[ServerEntry] = []
    infos: dict[str, ClientInfo] = {}
    warnings: list[str] = []
    projects: list[str] = []
    seen: set[str] = set()
    disabled: dict[str, set[str]] = {}  # project key -> names Claude Code's approval flow disabled
    overrides = paths.override_paths()

    def read(spec: ClientSpec, path: Path, scope: Scope, project: str | None) -> None:
        """Load one config file (once) and collect its entries; problems become warnings."""
        real = os.path.realpath(path)
        if real in seen or not path.is_file():
            return
        seen.add(real)
        try:
            text = path.read_text(encoding="utf-8")
            doc = load(text, spec.format)
        except (OSError, ValueError) as exc:
            warnings.append(f"{path}: cannot read ({type(exc).__name__}: {exc})")
            return
        comments = has_comments(text, spec.format)
        infos[spec.id].config_paths.append(
            ConfigFileInfo(
                path=str(path),
                exists=True,
                scope=scope,
                format=spec.format,
                project=project,
                has_comments=comments,
            )
        )
        if not spec.editable:
            entries.extend(collect(path, plain(doc), spec, paths))
            return
        entries.extend(_entries_of(doc, spec, scope, path, project, warnings))
        if scope == "user" and spec.local_projects_key:
            for key in _local_projects(doc, spec):
                projects.append(key)
                disabled[key] = _disabled_names(doc, spec, key)
                entries.extend(_entries_of(doc, spec, "local", path, key, warnings))
                # one add target per known project key (local adds may only use existing keys)
                infos[spec.id].config_paths.append(
                    ConfigFileInfo(
                        path=str(path), exists=True, scope="local", format=spec.format, project=key
                    )
                )

    for spec in specs.values():
        infos[spec.id] = ClientInfo(
            id=spec.id,
            display_name=spec.display_name,
            config_paths=[],
            capabilities=spec.capabilities,
            needs_restart=spec.needs_restart,
        )
        files = user_files(paths, spec)
        winner = next((p for p in files if p.exists()), None)
        for rule in spec.user_paths:
            for candidate in paths.candidates(rule):
                exists_before = len(infos[spec.id].config_paths)
                if "*" in rule.template or candidate == winner:
                    read(spec, candidate, rule.scope, None)
                if len(infos[spec.id].config_paths) == exists_before:
                    infos[spec.id].config_paths.append(
                        ConfigFileInfo(
                            path=str(candidate),
                            exists=candidate.exists(),
                            scope=rule.scope,
                            format=spec.format,
                        )
                    )
        for extra_path in overrides.get(spec.id, []):
            read(spec, paths.expand_home(extra_path), "user", None)

    project_keys = list(dict.fromkeys([*projects, str(paths.cwd)]))
    for key in project_keys:
        base = Path(key)
        if not base.is_absolute():
            continue
        for spec in specs.values():
            for rel in spec.project_paths:
                first = len(entries)
                read(spec, base / rel, "project", key)
                if spec.local_projects_key:  # Claude Code: honor its own approval decisions
                    for e in entries[first:]:
                        if e.name in disabled.get(key, ()):
                            e.enabled = False
    return DiscoveryResult(
        entries=entries, clients=list(infos.values()), projects=project_keys, warnings=warnings
    )
