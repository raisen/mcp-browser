"""Helpers shared by dialects: typed field readers, key-preserving merge, root lookup."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any, Literal, cast

from ..models import HttpTransport, Scope, SseTransport, StdioTransport, Transport
from ..specs.base import ClientSpec

Kind = Literal["stdio", "http", "sse"]
HTTP_TYPES = ("http", "streamableHttp", "streamable-http")


def declared_kind(value: Any) -> Kind | None:
    """Transport kind a `type` value stands for (any other string means a command-based server)."""
    if value in HTTP_TYPES:
        return "http"
    if value == "sse":
        return "sse"
    return "stdio" if isinstance(value, str) else None


def as_dict(value: Any) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def str_dict(value: Any) -> dict[str, str]:
    return {str(k): str(v) for k, v in as_dict(value).items()}


def str_list(value: Any) -> list[str]:
    return [str(v) for v in cast("list[Any]", value)] if isinstance(value, list) else []


def opt_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def opt_dict(value: Any) -> dict[str, Any] | None:
    return as_dict(value) if isinstance(value, dict) and value else None


def extra_of(raw: dict[str, Any], mapped: set[str] | frozenset[str]) -> dict[str, Any]:
    return {k: v for k, v in raw.items() if k not in mapped}


def read_stdio(raw: dict[str, Any], env_file_key: str | None = "envFile") -> StdioTransport:
    env_file = opt_str(raw.get(env_file_key)) if env_file_key else None
    return StdioTransport(
        command=str(raw["command"]),
        args=str_list(raw.get("args")),
        env=str_dict(raw.get("env")),
        cwd=opt_str(raw.get("cwd")),
        env_file=env_file,
    )


_ABSENT: Any = object()


def _keep_list(raw: list[Any], new: list[str]) -> list[Any]:
    used: set[int] = set()
    out: list[Any] = []
    for i, v in enumerate(new):
        order = ([i] if i < len(raw) else []) + list(range(len(raw)))
        hit = next((j for j in order if j not in used and str(raw[j]) == v), None)
        if hit is not None:
            used.add(hit)
        out.append(v if hit is None else raw[hit])
    return out


def keep_raw(raw: Any, new: Any) -> Any:
    """`new` (a normalized value) unless `raw` (the file's value) already reads as `new`; then `raw`
    itself, so non-string originals (8080, true, null) survive an edit that did not touch them.
    Dicts and lists are matched entry by entry."""
    if isinstance(new, dict) and isinstance(raw, dict):
        old = cast("dict[str, Any]", raw)
        merged: dict[str, Any] = {}
        for k, v in cast("dict[str, Any]", new).items():
            merged[k] = old[k] if k in old and str(old[k]) == v else v
        return merged
    if isinstance(new, list) and isinstance(raw, list):
        kept: list[Any] = _keep_list(cast("list[Any]", raw), cast("list[str]", new))
        return kept
    return cast("Any", new)


def pick(existing: dict[str, Any] | None, key: str, new: Any, parse: Any = None) -> Any:
    """Value to write for `key`: the file's raw value when it already parses to `new`, else `new`."""
    raw = existing.get(key, _ABSENT) if existing is not None else _ABSENT
    if raw is _ABSENT:
        return new
    if parse is not None and parse(raw) == new:
        return raw
    return keep_raw(raw, new)


def stdio_desired(
    t: StdioTransport, env_file_key: str | None = "envFile", existing: dict[str, Any] | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "command": pick(existing, "command", t.command, str),
        "args": pick(existing, "args", t.args, str_list),
        "env": pick(existing, "env", t.env, str_dict),
        "cwd": pick(existing, "cwd", t.cwd, opt_str),
    }
    if env_file_key:
        out[env_file_key] = pick(existing, env_file_key, t.env_file, opt_str)
    return out


def read_remote(
    raw: dict[str, Any], kind: Kind, url: str, headers_key: str = "headers", oauth_key: str | None = "oauth"
) -> HttpTransport | SseTransport:
    headers = str_dict(raw.get(headers_key))
    oauth = opt_dict(raw.get(oauth_key)) if oauth_key else None
    if kind == "sse":
        return SseTransport(url=url, headers=headers, oauth=oauth)
    return HttpTransport(url=url, headers=headers, oauth=oauth)


def remote_desired(
    t: HttpTransport | SseTransport,
    url_key: str,
    headers_key: str = "headers",
    oauth_key: str | None = "oauth",
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        url_key: pick(existing, url_key, t.url, str),
        headers_key: pick(existing, headers_key, t.headers, str_dict),
    }
    if oauth_key:
        out[oauth_key] = pick(existing, oauth_key, t.oauth, opt_dict)
    return out


def flag_desired(
    out: dict[str, Any], key: str, existing: dict[str, Any] | None, value: bool, *, invert: bool
) -> None:
    """Add an enabled/disabled flag only when it must be written (present already, or turned off)."""
    present = existing is not None and key in existing
    if present or not value:
        out[key] = (not value) if invert else value


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, (list, dict)) and not value)


def strip_keys(
    old: Transport | None, new: Transport | None, mapped: frozenset[str], drop: Mapping[str, frozenset[str]]
) -> frozenset[str]:
    """Keys that must not survive in `extra`: on a new entry or a transport kind change, every mapped
    key plus the new kind's `drop` list (keys only another kind understands). Same kind: none."""
    if new is None or (old is not None and old.kind == new.kind):
        return frozenset()
    return mapped | drop.get(new.kind, frozenset())


def merge(
    existing: dict[str, Any] | None,
    desired: dict[str, Any],
    extra: dict[str, Any],
    strip: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Edit `existing` in place (or start from {}) so it holds exactly `desired` + `extra`.

    `desired` (the transport's mapped keys) always wins: `extra` never overrides it, and keys in
    `strip` are removed from `extra`. Untouched keys keep their position and (for TOML) comments;
    changed keys are rewritten in place; new keys are appended; keys in neither mapping are removed;
    empty desired values drop the key unless it is already empty."""
    extra = {k: v for k, v in extra.items() if k not in desired and k not in strip}
    out: dict[str, Any] = existing if existing is not None else {}
    for key in list(out):
        if key not in desired and key not in extra:
            del out[key]
    for key, value in desired.items():
        if is_empty(value):
            if key in out and not is_empty(out[key]):
                del out[key]
            continue
        if key not in out or out[key] != value:
            out[key] = value
    for key, value in extra.items():
        if key not in out or out[key] != value:
            out[key] = value
    return out


def root_at(doc: Any, key: str, create: bool) -> MutableMapping[str, Any] | None:
    if not isinstance(doc, MutableMapping):
        return None
    node = cast("MutableMapping[str, Any]", doc)
    current: Any = node.get(key)
    if current is None:
        if not create:
            return None
        node[key] = {}
        current = node[key]
    return cast("MutableMapping[str, Any]", current) if isinstance(current, MutableMapping) else None


def standard_root(
    doc: Any, spec: ClientSpec, scope: Scope, project: str | None, create: bool
) -> MutableMapping[str, Any] | None:
    """`spec.root_key` of the document; local scope descends into an EXISTING `projects[<verbatim key>]`."""
    if scope != "local":
        return root_at(doc, spec.root_key, create)
    if not spec.local_projects_key or project is None or not isinstance(doc, MutableMapping):
        return None
    projects: Any = cast("MutableMapping[str, Any]", doc).get(spec.local_projects_key)
    if not isinstance(projects, MutableMapping):
        return None
    entry: Any = cast("MutableMapping[str, Any]", projects).get(project)
    return root_at(entry, spec.root_key, create) if isinstance(entry, MutableMapping) else None
