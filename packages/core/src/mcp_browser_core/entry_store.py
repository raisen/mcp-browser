"""Helpers `mutate` builds on: guarded file writes, entry reports and in-place entry replacement."""

from __future__ import annotations

from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Any, cast

from .dialects import get_dialect
from .discovery import entry_id as make_id
from .errors import InvalidArguments, McpBrowserError
from .formats import plain
from .models import ServerEntry
from .paths import Paths
from .specs.base import ClientSpec
from .writer import write_entry

Root = MutableMapping[str, Any]


def write(file: Path, spec: ClientSpec, paths: Paths, edit: Callable[[Any], None], allow: bool) -> str | None:
    """`write_entry` with every failure surfaced as an `McpBrowserError` (never a raw OSError)."""
    try:
        return write_entry(
            str(file),
            spec.format,
            edit,
            paths=paths,
            allow_comment_loss=allow,
            create=True,
            dedicated_file=spec.dedicated_file,
        )
    except ValueError as exc:
        raise InvalidArguments(f"{file.name} is not valid {spec.format}: {exc}") from exc
    except OSError as exc:
        raise McpBrowserError(f"could not write {file.name}: {exc.strerror or exc}", path=str(file)) from exc


def report(spec: ClientSpec, file: Path, scope: Any, project: str | None, name: str, raw: Any) -> ServerEntry:
    transport, error, enabled, extra = get_dialect(spec.dialect).parse(
        name, cast("dict[str, Any]", raw), spec
    )
    return ServerEntry(
        id=make_id(spec.id, scope, str(file), project, name),
        name=name,
        client_id=spec.id,
        scope=scope,
        config_path=str(file),
        project=project,
        transport=transport,
        error=error,
        enabled=enabled,
        extra=extra,
    )


def _rename_toml(root: Root, old: str, new: str) -> bool:
    """Re-key a tomlkit table where it stands, so its position, header comments and interior
    comments stay. False when `root` is not a plain tomlkit table (caller falls back)."""
    container: Any = getattr(root, "value", None)
    body: Any = getattr(container, "body", None)
    if not isinstance(body, list) or not hasattr(container, "_insert_at") or not hasattr(container, "remove"):
        return False
    pairs = cast("list[tuple[Any, Any]]", body)
    index = next((i for i, (k, _) in enumerate(pairs) if k is not None and k.key == old), None)
    if index is None:
        return False
    item: Any = pairs[index][1]
    container.remove(old)
    container._insert_at(index, new, item)  # pyright: ignore[reportUnknownMemberType]
    _clear_display_names(item)
    return True


def _clear_display_names(item: Any) -> None:
    """tomlkit prints a parsed table's header from `display_name`; None makes it follow the key."""
    if hasattr(item, "display_name"):
        item.display_name = None
    children: Any = getattr(getattr(item, "value", None), "body", None)
    if isinstance(children, list):
        for _, child in cast("list[tuple[Any, Any]]", children):
            if hasattr(child, "display_name"):
                _clear_display_names(child)


def store(root: Root, old: str, new: str, rendered: Any) -> None:
    if old == new:
        if root[old] is not rendered:
            root[old] = rendered
    elif type(root) is dict:  # plain JSON object: rebuild so the entry keeps its position
        obj = cast("dict[str, Any]", root)
        items = list(obj.items())
        obj.clear()
        for key, value in items:
            obj[new if key == old else key] = rendered if key == old else value
    elif root[old] is rendered and _rename_toml(root, old, new):
        return
    else:
        del root[old]
        root[new] = plain(rendered)
