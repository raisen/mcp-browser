"""Masking of secret values before anything leaves the process."""

from __future__ import annotations

import math
import re
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel

from .models import HttpTransport, ServerEntry, SseTransport, StdioTransport

MASK = "•••"
SECRET_KEYS = frozenset(
    {"env", "headers", "http_headers", "env_http_headers", "bearer_token_env_var", "oauth", "auth"}
)
SECRET_WORDS = ("key", "token", "secret", "auth", "password")


def _secret_name(name: str) -> bool:
    lowered = name.lower()
    return any(word in lowered for word in SECRET_WORDS)


def _mask_all(value: Any) -> Any:
    """Every leaf becomes MASK; dict keys are kept."""
    if isinstance(value, dict):
        return {k: _mask_all(v) for k, v in cast("dict[str, Any]", value).items()}
    if isinstance(value, list):
        return [MASK for _ in cast("list[Any]", value)]
    return MASK


_ENV_FLAGS = frozenset({"-e", "--env", "-H", "--header", "--headers"})
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TOKENISH = re.compile(r"[A-Za-z0-9_\-=.~%]{20,}")
_SCHEMES = ("bearer", "basic", "token", "digest")


def _entropy(text: str) -> float:
    counts = {c: text.count(c) for c in set(text)}
    return -sum(n / len(text) * math.log2(n / len(text)) for n in counts.values())


def secret_segment(segment: str) -> bool:
    """A long, mixed letters-and-digits, high-entropy URL path segment looks like a token."""
    return bool(
        _TOKENISH.fullmatch(segment)
        and any(c.isdigit() for c in segment)
        and any(c.isalpha() for c in segment)
        and _entropy(segment) >= 3.5
    )


def url_secrets(url: str) -> list[str]:
    """The raw secret pieces of a URL: userinfo, secret-named query values, token-like path segments."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return []
    out: list[str] = []
    if "@" in parts.netloc:
        out.append(parts.netloc.rsplit("@", 1)[0])
    for pair in parts.query.split("&"):
        name, _, value = pair.partition("=")
        if value and _secret_name(name):
            out.append(value)
    out += [seg for seg in parts.path.split("/") if secret_segment(seg)]
    return out


def mask_url(url: str) -> str:
    """Hide URL userinfo, token-like path segments and the values of secret-named query parameters."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    netloc = parts.netloc
    if "@" in netloc:
        netloc = f"{MASK}@{netloc.rsplit('@', 1)[1]}"
    path = "/".join(MASK if secret_segment(seg) else seg for seg in parts.path.split("/"))
    query = "&".join(
        f"{pair.split('=', 1)[0]}={MASK}" if "=" in pair and _secret_name(pair.split("=", 1)[0]) else pair
        for pair in parts.query.split("&")
    )
    out = urlunsplit((parts.scheme, netloc, path, query, parts.fragment))
    return out.replace("%E2%80%A2", "•")


def mask_header(name: str, value: str) -> str:
    """`Authorization: Bearer x` -> `Authorization: Bearer •••`; other secret headers lose the value."""
    scheme, _, rest = value.strip().partition(" ")
    if rest and scheme.lower() in _SCHEMES:
        return f"{name}: {scheme} {MASK}"
    return f"{name}: {MASK}"


def _mask_pair(value: str) -> str:
    """One `KEY=value` or `Name: value` argument; secret-looking ones lose the value."""
    head, sep, _ = value.partition("=")
    if sep and _IDENT.fullmatch(head) and _secret_name(head):
        return f"{head}={MASK}"
    name, colon, rest = value.partition(":")
    if colon and rest.strip() and (_secret_name(name) or rest.strip().split(" ")[0].lower() in _SCHEMES):
        return mask_header(name.strip(), rest)
    return value


def mask_args(args: list[str]) -> list[str]:
    """`--api-key x`, `--token=x`, `KEY=x` (secret KEY), `-e KEY=x`, `-H 'Authorization: Bearer x'`."""
    out: list[str] = []
    hide_next = pair_next = False
    for arg in args:
        if pair_next or (hide_next and not arg.startswith("-")):
            out.append(_mask_pair(arg) if pair_next else MASK)
            hide_next = pair_next = False
            continue
        hide_next = False
        flag, eq, rest = arg.partition("=")
        if arg in _ENV_FLAGS:
            pair_next = True
        elif eq and flag in _ENV_FLAGS:
            arg = f"{flag}={_mask_pair(rest)}"
        elif arg.startswith("-") and _secret_name(flag):
            if eq:
                arg = f"{flag}={MASK}"
            else:
                hide_next = True
        elif not arg.startswith("-"):
            arg = _mask_pair(arg)
        out.append(arg)
    return out


def mask_entry(entry: ServerEntry) -> ServerEntry:
    """Copy with env/header values, secret-looking URL userinfo/query values, secret flag args
    and SECRET_KEYS inside `extra` replaced by MASK (keys are kept)."""
    t = entry.transport
    transport: StdioTransport | HttpTransport | SseTransport | None = None
    if isinstance(t, StdioTransport):
        transport = t.model_copy(update={"env": {k: MASK for k in t.env}, "args": mask_args(t.args)})
    elif t is not None:
        transport = t.model_copy(
            update={
                "url": mask_url(t.url),
                "headers": {k: MASK for k in t.headers},
                "oauth": _mask_all(t.oauth) if t.oauth else None,
            }
        )
    extra = {k: (_mask_all(v) if k in SECRET_KEYS else v) for k, v in entry.extra.items()}
    return entry.model_copy(update={"transport": transport, "extra": extra})


def contains_mask(entry_or_patch: object) -> bool:
    """True if any string (key or value, at any depth) contains MASK; writes must reject such input."""
    if isinstance(entry_or_patch, str):
        return MASK in entry_or_patch
    if isinstance(entry_or_patch, BaseModel):
        return contains_mask(entry_or_patch.model_dump(mode="python"))
    if isinstance(entry_or_patch, dict):
        items = cast("dict[Any, Any]", entry_or_patch).items()
        return any(contains_mask(k) or contains_mask(v) for k, v in items)
    if isinstance(entry_or_patch, (list, tuple)):
        return any(contains_mask(v) for v in cast("list[Any]", entry_or_patch))
    return False
