"""TOML through tomlkit, which preserves comments, ordering and layout."""

from __future__ import annotations

from typing import Any

import tomlkit


def load(text: str) -> Any:
    return tomlkit.parse(text.removeprefix("\ufeff"))


def dump(doc: Any, *, newline: bool = True) -> str:
    out = tomlkit.dumps(doc)
    if newline and out and not out.endswith("\n"):
        out += "\n"
    return out
