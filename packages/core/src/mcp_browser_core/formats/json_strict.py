"""Strict JSON that keeps the file's indent unit and trailing newline."""

from __future__ import annotations

import json
import re
from typing import Any

from ..errors import InvalidArguments

_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def load(text: str) -> Any:
    text = text.lstrip("﻿")
    return json.loads(text) if text.strip() else {}


def dump(doc: Any, *, indent: int | str = 2, newline: bool = True) -> str:
    """Pretty JSON. Non-finite numbers are refused (they are not JSON); lone surrogates, which
    cannot be encoded as UTF-8, are written as `\\udXXX` escapes and read back identically."""
    try:
        out = json.dumps(doc, indent=indent, ensure_ascii=False, allow_nan=False)
    except ValueError as exc:
        raise InvalidArguments(
            "the file holds a NaN or Infinity number, which JSON cannot store; fix that value first"
        ) from exc
    out = _LONE_SURROGATE.sub(lambda m: f"\\u{ord(m.group()):04x}", out)
    return out + "\n" if newline else out


def indent_unit(text: str) -> int | str:
    """Indent of the first indented line: a number of spaces, or "\\t"."""
    for line in text.splitlines():
        body = line.lstrip(" \t")
        if not body or body == line:
            continue
        lead = line[: len(line) - len(body)]
        return "\t" if lead.startswith("\t") else len(lead)
    return 2
