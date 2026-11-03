"""What a repo-provided (untrusted) entry would do, for the confirmation dialog. Names only, no values."""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import urlsplit

from .expand import placeholder_names
from .models import HttpTransport, ServerEntry, SseTransport, StdioTransport


def _add(out: list[str], names: list[str]) -> None:
    out.extend(n for n in names if n not in out)


def _str_list(raw: Any) -> list[str]:
    """Names from a list of strings or `{name: ...}` objects (Codex `env_vars`)."""
    items = cast("list[Any]", raw) if isinstance(raw, list) else []
    out: list[str] = []
    for item in items:
        name: Any = cast("dict[str, Any]", item).get("name") if isinstance(item, dict) else item
        if isinstance(name, str):
            out.append(name)
    return out


def env_var_names(entry: ServerEntry) -> list[str]:
    """Every environment variable this entry would read when connected."""
    t = entry.transport
    out: list[str] = []
    if isinstance(t, StdioTransport):
        for text in (t.command, *t.args, *t.env.values(), t.cwd or "", t.env_file or ""):
            _add(out, placeholder_names(text))
        _add(out, _str_list(entry.extra.get("env_vars")))
    elif isinstance(t, (HttpTransport, SseTransport)):
        for text in (t.url, *t.headers.values()):
            _add(out, placeholder_names(text))
        bearer = entry.extra.get("bearer_token_env_var")
        if isinstance(bearer, str) and bearer:
            _add(out, [bearer])
        mapped = entry.extra.get("env_http_headers")
        if isinstance(mapped, dict):
            _add(out, [v for v in cast("dict[str, Any]", mapped).values() if isinstance(v, str)])
    return out


def confirmation_detail(entry: ServerEntry) -> dict[str, Any]:
    """Exact command + args or URL, destination host (None for stdio), env var names."""
    t = entry.transport
    detail: dict[str, Any] = {
        "entry_id": entry.id,
        "name": entry.name,
        "config_path": entry.config_path,
        "env_vars": env_var_names(entry),
        "host": None,
    }
    if isinstance(t, StdioTransport):
        detail |= {"kind": "stdio", "command": t.command, "args": list(t.args), "cwd": t.cwd}
        detail["inherits_environment"] = True  # the child receives this process's whole environment
    elif t is not None:
        detail |= {"kind": t.kind, "url": t.url, "header_names": list(t.headers)}
        try:
            detail["host"] = urlsplit(t.url).netloc.rpartition("@")[2] or None
        except ValueError:
            detail["host"] = None
    return detail
