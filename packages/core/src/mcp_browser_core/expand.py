"""Placeholder expansion for transports (`${VAR}`, `${env:VAR}`, `%VAR%`, ...)."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

from .models import HttpTransport, SseTransport, StdioTransport, Transport

_PATTERN = re.compile(
    r"\$\{(?P<braced>[^}]*)\}|\$(?P<bare>[A-Za-z_][A-Za-z0-9_]*)|%(?P<pct>[A-Z_][A-Z0-9_]*)%"
)


def expand(value: str, env: Mapping[str, str], *, project: str | None, home: Path) -> tuple[str, list[str]]:
    """Handles ${VAR}, ${VAR:-d}, $VAR, ${env:VAR}, %VAR%, ${userHome}, ${workspaceFolder},
    ${pathSeparator}. Returns (text, unresolved names); unresolved placeholders stay verbatim."""
    unresolved: list[str] = []

    def lookup(name: str, default: str | None, original: str) -> str:
        found = env.get(name)
        if found is not None and (found != "" or default is None):
            return found
        if default is not None:
            return default
        if name not in unresolved:
            unresolved.append(name)
        return original

    def replace(m: re.Match[str]) -> str:
        original = m.group(0)
        if m.group("bare") is not None:
            return lookup(m.group("bare"), None, original)
        if m.group("pct") is not None:
            return env.get(m.group("pct"), original)
        body: str = m.group("braced")
        fixed = {"userHome": str(home), "pathSeparator": os.sep, "workspaceFolder": project}
        if body in fixed:
            text = fixed[body]
            if text is None:
                if body not in unresolved:
                    unresolved.append(body)
                return original
            return text
        if body.startswith("env:"):
            body = body[4:]
        name, sep, default = body.partition(":-")
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            return lookup(name, default if sep else None, original)
        if body not in unresolved:
            unresolved.append(body)  # e.g. "input:token" (VS Code input variables)
        return original

    return _PATTERN.sub(replace, value), unresolved


def placeholder_names(value: str) -> list[str]:
    """Names of the environment variables a string would read (no values; fixed names excluded)."""
    out: list[str] = []
    for m in _PATTERN.finditer(value):
        if m.group("bare") is not None:
            name = m.group("bare")
        elif m.group("pct") is not None:
            name = m.group("pct")
        else:
            body: str = m.group("braced")
            body = body[4:] if body.startswith("env:") else body
            name = body.partition(":-")[0]
            if body in ("userHome", "pathSeparator", "workspaceFolder") or not re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*", name
            ):
                continue
        if name not in out:
            out.append(name)
    return out


def parse_env_file(text: str) -> dict[str, str]:
    """`KEY=VALUE` lines; blank lines and `#` comments are skipped, `export ` and quotes are stripped."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        line = line.removeprefix("export ").strip()
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key.strip()] = val
    return out


def expand_transport(
    t: Transport, env: Mapping[str, str], *, project: str | None, home: Path
) -> tuple[Transport, list[str]]:
    """Expand command/args/env/cwd/url/headers; load `env_file` (KEY=VALUE, `#` comments) under the
    entry env. Callers raise UnresolvedPlaceholders when the list is non-empty."""
    unresolved: list[str] = []

    def ex(value: str) -> str:
        text, bad = expand(value, env, project=project, home=home)
        unresolved.extend(n for n in bad if n not in unresolved)
        return text

    def ex_map(values: Mapping[str, str]) -> dict[str, str]:
        return {k: ex(v) for k, v in values.items()}

    if isinstance(t, (HttpTransport, SseTransport)):
        return t.model_copy(update={"url": ex(t.url), "headers": ex_map(t.headers)}), unresolved
    assert isinstance(t, StdioTransport)
    cwd = ex(t.cwd) if t.cwd else None
    merged: dict[str, str] = {}
    if t.env_file:
        path = Path(ex(t.env_file))
        base = Path(cwd) if cwd else (Path(project) if project else None)
        if not path.is_absolute() and base is not None:
            path = base / path
        try:
            merged.update(parse_env_file(path.read_text(encoding="utf-8")))
        except OSError:
            unresolved.append(f"envFile:{path.name}")
    merged.update(ex_map(t.env))
    update = {
        "command": ex(t.command),
        "args": [ex(a) for a in t.args],
        "env": merged,
        "cwd": cwd,
        "env_file": None,
    }
    return t.model_copy(update=update), unresolved
