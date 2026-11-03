"""Remove the real (expanded) secret values of a server entry from any text that leaves the process."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

from .expand import expand, expand_transport
from .models import HttpTransport, ServerEntry, SseTransport, StdioTransport, Transport
from .secrets import MASK, mask_args, mask_url, url_secrets

MIN_LENGTH = 4
_PLACEHOLDER = re.compile(r"\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*|%[A-Z_][A-Z0-9_]*%")
_FIXED = ("${userHome}", "${pathSeparator}", "${workspaceFolder}")


def _pieces(value: str) -> list[str]:
    """The value plus its `=` tail and last word, so partial echoes are caught too."""
    out = [value, value.partition("=")[2]]
    if value.split():
        out.append(value.split()[-1])
    return out


def _substituted(raw: str, env: Mapping[str, str], project: str | None, home: Path) -> list[str]:
    """What each placeholder in `raw` turned into (path-ish fixed placeholders are not secrets)."""
    out: list[str] = []
    for match in _PLACEHOLDER.finditer(raw):
        if match.group(0) not in _FIXED:
            out.append(expand(match.group(0), env, project=project, home=home)[0])
    return out


class Scrubber:
    """Replaces known secret strings with MASK. Values shorter than 4 characters are never scrubbed."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        found = {s for s in secrets if len(s) >= MIN_LENGTH}
        self._secrets = sorted(found, key=len, reverse=True)

    def text(self, value: str | None) -> str | None:
        if not value:
            return value
        for secret in self._secrets:
            value = value.replace(secret, MASK)
        return value

    def str(self, value: str) -> str:
        return self.text(value) or ""

    def obj(self, value: Any) -> Any:
        """Scrub every string (keys and values) inside a JSON-like structure."""
        if isinstance(value, str):
            return self.str(value)
        if isinstance(value, list):
            return [self.obj(v) for v in cast("list[Any]", value)]
        if isinstance(value, dict):
            return {self.str(str(k)): self.obj(v) for k, v in cast("dict[Any, Any]", value).items()}
        return value

    @classmethod
    def build(cls, entry: ServerEntry, expanded: Transport, env: Mapping[str, str], home: Path) -> Scrubber:
        """From the entry as written (placeholders) and the transport `prepare()` expanded from it."""
        raw, found = entry.transport, set[str]()

        def sub(text: str) -> None:
            found.update(_substituted(text, env, entry.project, home))

        if isinstance(expanded, StdioTransport):
            found.update(v for value in expanded.env.values() for v in _pieces(value))
            masked = mask_args(expanded.args)
            found.update(p for a, m in zip(expanded.args, masked, strict=True) if a != m for p in _pieces(a))
            if isinstance(raw, StdioTransport):
                for a in [raw.command, *raw.args, *raw.env.values(), raw.cwd or ""]:
                    sub(a)
                for a, e in zip(raw.args, expanded.args, strict=False):
                    if a != e:
                        found.update(_pieces(e))
        else:
            found.update(p for v in expanded.headers.values() for p in _pieces(v))
            found.update(url_secrets(expanded.url))
            if mask_url(expanded.url) != expanded.url:
                found.add(expanded.url)
            if isinstance(raw, (HttpTransport, SseTransport)):
                sub(raw.url)
                for v in raw.headers.values():
                    sub(v)
        return cls(found)


def expand_for_scrub(entry: ServerEntry, env: Mapping[str, str], home: Path) -> Transport | None:
    """Best-effort expansion (no error on missing variables) for callers that have no `prepare()` result."""
    t = entry.transport
    if t is None:
        return None
    if isinstance(t, (HttpTransport, SseTransport)):
        from .transports import codex_headers

        t = t.model_copy(update={"headers": codex_headers(entry, t.headers)})
    return expand_transport(t, env, project=entry.project, home=home)[0]


def scrubber_for(
    entry: ServerEntry, env: Mapping[str, str] | None = None, home: Path | None = None
) -> Scrubber:
    """Scrubber from an entry alone, using this process's environment."""
    env = dict(os.environ) if env is None else env
    home = home or Path.home()
    expanded = expand_for_scrub(entry, env, home)
    return Scrubber() if expanded is None else Scrubber.build(entry, expanded, env, home)
