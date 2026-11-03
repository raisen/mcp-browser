"""Target resolution and preflight checks shared by `mutate.add`."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from .dialects import get_dialect
from .discovery import active_user_file, project_file
from .errors import CommentsWouldBeLost, Conflict, InvalidArguments, NotFound, ReadOnly, UnsupportedTransport
from .formats import has_comments, load
from .models import NewEntry, StdioTransport, Target, Transport
from .paths import Paths
from .specs.base import ClientSpec


def spec_for(specs: Mapping[str, ClientSpec], client_id: str) -> ClientSpec:
    if client_id not in specs:
        raise NotFound(f"unknown client {client_id!r}")
    spec = specs[client_id]
    if not spec.editable:
        raise ReadOnly(spec.read_only_reason or f"{spec.display_name} is read-only")
    return spec


def check_transport(spec: ClientSpec, transport: Transport, current: Transport | None = None) -> None:
    """Capability check. A working directory the client cannot store is refused, unless the entry
    already carries that same value (an edit that does not touch it)."""
    if not getattr(spec.capabilities, transport.kind):
        raise UnsupportedTransport(f"{spec.display_name} does not support {transport.kind} servers")
    if isinstance(transport, StdioTransport) and transport.cwd and not spec.stdio_cwd:
        same = isinstance(current, StdioTransport) and current.cwd == transport.cwd
        if not same:
            raise UnsupportedTransport(
                f"{spec.display_name} has no working-directory (cwd) setting for stdio servers"
            )


def check_name(name: str) -> None:
    if not name.strip():
        raise InvalidArguments("server name must not be empty")


def target_file(paths: Paths, spec: ClientSpec, target: Target) -> Path:
    if target.scope == "user":
        found = active_user_file(paths, spec)
    elif target.scope == "local":
        if not spec.local_projects_key or not target.project:
            raise InvalidArguments(f"{spec.display_name} has no local scope")
        found = active_user_file(paths, spec)
    elif target.scope == "project":
        if not spec.capabilities.project_scope or not target.project:
            raise InvalidArguments(f"{spec.display_name} has no project scope, or no project was given")
        base = Path(target.project)
        if not base.is_absolute() or not base.is_dir():
            raise InvalidArguments(f"project directory does not exist: {target.project}")
        found = project_file(spec, base)
    else:
        raise InvalidArguments(f"cannot add to scope {target.scope!r}")
    if found is None:
        raise InvalidArguments(f"no config location known for {spec.display_name} on this platform")
    return found


def _local_exists(doc: Any, spec: ClientSpec, project: str | None) -> bool:
    if not isinstance(doc, dict) or not spec.local_projects_key:
        return False
    projects: Any = cast("dict[str, Any]", doc).get(spec.local_projects_key)
    return isinstance(projects, dict) and project in cast("dict[str, Any]", projects)


def preflight(new: NewEntry, target: Target, file: Path, spec: ClientSpec, allow: bool) -> None:
    exists = file.is_file()
    if target.scope == "local" and not exists:
        raise InvalidArguments(f"{file} does not exist, so it has no project {target.project!r}")
    if not exists:
        return
    try:
        text = file.read_text(encoding="utf-8")
        doc = load(text, spec.format)
    except (OSError, ValueError) as exc:
        raise InvalidArguments(f"cannot read {file}: {exc}") from exc
    if has_comments(text, spec.format) and not (spec.dedicated_file and allow):
        raise CommentsWouldBeLost(
            f"{file.name} contains comments that rewriting would remove", can_override=spec.dedicated_file
        )
    if target.scope == "local" and not _local_exists(doc, spec, target.project):
        raise InvalidArguments(
            f"{file} has no project {target.project!r}; local entries can only be added to existing projects"
        )
    root = get_dialect(spec.dialect).root(doc, spec, target.scope, target.project, False)
    if root is not None and new.name in root:
        raise Conflict(f"{spec.display_name} already has a server named {new.name!r}", path=str(file))
