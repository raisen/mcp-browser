"""Config file formats: strict JSON, JSONC (read with json5, written as strict JSON) and TOML."""

from __future__ import annotations

from typing import Any

from ..models import Format
from . import json_strict, jsonc, toml


def load(text: str, fmt: Format) -> Any:
    """Parse text: json, json5 (jsonc) or a tomlkit document (toml)."""
    if fmt == "toml":
        return toml.load(text)
    if fmt == "jsonc":
        return jsonc.load(text)
    return json_strict.load(text)


def dump(doc: Any, fmt: Format, *, indent: int | str = 2, newline: bool = True) -> str:
    """Serialize; jsonc is written as strict json, toml keeps comments and ordering."""
    if fmt == "toml":
        return toml.dump(doc, newline=newline)
    return json_strict.dump(doc, indent=indent, newline=newline)


def detect_indent(text: str) -> int:
    """Width of the first indented line (a tab counts as 2); 2 when nothing is indented."""
    unit = json_strict.indent_unit(text)
    return 2 if isinstance(unit, str) else unit


def indent_unit(text: str) -> int | str:
    """Like `detect_indent` but returns "\\t" for tab-indented files."""
    return json_strict.indent_unit(text)


def has_comments(text: str, fmt: Format) -> bool:
    """jsonc only: a string-aware character scan for `//` and `/* */` (never a regex)."""
    return jsonc.has_comments(text) if fmt == "jsonc" else False


def plain(obj: Any) -> Any:
    """Convert tomlkit items to builtin Python values; builtins pass through unchanged."""
    unwrap = getattr(obj, "unwrap", None)
    return unwrap() if callable(unwrap) else obj


__all__ = ["detect_indent", "dump", "has_comments", "indent_unit", "load", "plain"]
