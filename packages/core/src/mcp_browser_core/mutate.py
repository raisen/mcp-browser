"""add / update / delete / rename on top of dialects and the writer."""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from pathlib import Path
from typing import Any, cast

from .catalog import Catalog
from .dialects import get_dialect
from .discovery import discover
from .entry_store import Root, report, store, write
from .errors import (
    Conflict,
    InvalidArguments,
    McpBrowserError,
    NotFound,
    ReadOnly,
)
from .formats import plain
from .models import (
    AddResult,
    EntryPatch,
    NewEntry,
    ServerEntry,
    Target,
    WriteReport,
)
from .paths import Paths
from .secrets import contains_mask
from .specs import REGISTRY
from .specs.base import ClientSpec
from .targets import check_name, check_transport, preflight, spec_for, target_file


def add(
    new: NewEntry,
    targets: list[Target],
    *,
    paths: Paths,
    specs: Mapping[str, ClientSpec] = REGISTRY,
    allow_comment_loss: bool = False,
) -> list[AddResult]:
    """Preflight ALL targets (capability, duplicate name, comment rule); on failure write nothing.
    Then write each target; an I/O failure on one target does not abort the others."""
    check_name(new.name)
    if contains_mask(new):
        raise InvalidArguments("a masked value cannot be saved; enter the real value")
    plan: list[tuple[Target, ClientSpec, Path]] = []
    for target in targets:
        spec = spec_for(specs, target.client_id)
        check_transport(spec, new.transport)
        file = target_file(paths, spec, target)
        preflight(new, target, file, spec, allow_comment_loss)
        plan.append((target, spec, file))
    return [_add_one(new, target, spec, file, paths, allow_comment_loss) for target, spec, file in plan]


def _add_one(
    new: NewEntry, target: Target, spec: ClientSpec, file: Path, paths: Paths, allow: bool
) -> AddResult:
    dialect = get_dialect(spec.dialect)
    existed = file.exists()
    box: list[Any] = []

    def edit(doc: Any) -> None:
        root = dialect.root(doc, spec, target.scope, target.project, True)
        if root is None:
            raise InvalidArguments(f"{file.name} has an unexpected layout")
        if new.name in root:
            raise Conflict(f"{spec.display_name} already has a server named {new.name!r}")
        stub = ServerEntry(
            id="", name=new.name, client_id=spec.id, scope=target.scope, config_path=str(file),
            project=target.project, transport=new.transport, extra=new.extra,
        )  # fmt: skip
        root[new.name] = dialect.render(stub, None, spec)
        box.append(plain(root[new.name]))

    try:
        backup = write(file, spec, paths, edit, allow)
    except (OSError, McpBrowserError) as exc:
        return AddResult(target=target, error=getattr(exc, "message", None) or str(exc))
    entry = report(spec, file, target.scope, target.project, new.name, box[-1])
    return AddResult(
        target=target,
        report=WriteReport(path=str(file), backup_path=backup, created_file=not existed, entry=entry),
    )


def _locate(eid: str, paths: Paths, specs: Mapping[str, ClientSpec]) -> tuple[ServerEntry, ClientSpec]:
    entry = next((e for e in discover(paths, specs).entries if e.id == eid), None)
    if entry is None:
        raise NotFound(f"no server entry with id {eid!r}")
    if entry.read_only:
        raise ReadOnly(entry.read_only_reason or "this entry is read-only")
    return entry, spec_for(specs, entry.client_id)


def _edit_entry(
    entry: ServerEntry, spec: ClientSpec, paths: Paths, allow: bool, apply: Callable[[Root], Any]
) -> tuple[str | None, Any]:
    box: list[Any] = []

    def edit(doc: Any) -> None:
        root = get_dialect(spec.dialect).root(doc, spec, entry.scope, entry.project, False)
        if root is None or entry.name not in root:
            raise NotFound(f"{entry.name!r} is no longer in {Path(entry.config_path).name}")
        box.append(apply(root))

    return write(Path(entry.config_path), spec, paths, edit, allow), (box[-1] if box else None)


def update(
    entry_id: str,
    patch: EntryPatch,
    *,
    paths: Paths,
    specs: Mapping[str, ClientSpec] = REGISTRY,
    allow_comment_loss: bool = False,
    catalog: Catalog | None = None,
) -> WriteReport:
    if contains_mask(patch):
        raise InvalidArguments("a masked value cannot be saved; enter the real value")
    entry, spec = _locate(entry_id, paths, specs)
    name = entry.name if patch.name is None else patch.name
    check_name(name)
    if patch.transport is not None:
        check_transport(spec, patch.transport, entry.transport)
    keep_extra = entry.extra if entry.transport is not None or patch.transport is None else {}
    updated = entry.model_copy(
        update={
            "name": name,
            "transport": patch.transport or entry.transport,
            "extra": keep_extra if patch.extra is None else patch.extra,
            "error": entry.error if patch.transport is None else None,
        }
    )

    def apply(root: Root) -> Any:
        if name != entry.name and name in root:
            raise Conflict(f"{spec.display_name} already has a server named {name!r}")
        existing: Any = root[entry.name]
        rendered = get_dialect(spec.dialect).render(
            updated, cast("dict[str, Any]", existing) if isinstance(existing, MutableMapping) else None, spec
        )
        store(root, entry.name, name, rendered)
        return plain(root[name])

    backup, raw = _edit_entry(entry, spec, paths, allow_comment_loss, apply)
    if catalog is not None:
        catalog.drop(entry.id)
    fresh = report(spec, Path(entry.config_path), entry.scope, entry.project, name, raw)
    return WriteReport(path=entry.config_path, backup_path=backup, created_file=False, entry=fresh)


def delete(
    entry_id: str,
    *,
    paths: Paths,
    specs: Mapping[str, ClientSpec] = REGISTRY,
    allow_comment_loss: bool = False,
    catalog: Catalog | None = None,
) -> WriteReport:
    entry, spec = _locate(entry_id, paths, specs)
    backup, _ = _edit_entry(entry, spec, paths, allow_comment_loss, lambda root: root.pop(entry.name))
    if catalog is not None:
        catalog.drop(entry.id)
    return WriteReport(path=entry.config_path, backup_path=backup, created_file=False, entry=entry)


def rename(
    entry_id: str,
    new_name: str,
    *,
    paths: Paths,
    specs: Mapping[str, ClientSpec] = REGISTRY,
    allow_comment_loss: bool = False,
    catalog: Catalog | None = None,
) -> WriteReport:
    return update(
        entry_id,
        EntryPatch(name=new_name),
        paths=paths,
        specs=specs,
        allow_comment_loss=allow_comment_loss,
        catalog=catalog,
    )
