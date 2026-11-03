"""JSON with comments: read with json5, comment detection by a string-aware scanner."""

from __future__ import annotations

from typing import Any

import json5


def load(text: str) -> Any:
    text = text.lstrip("﻿")
    return json5.loads(text) if text.strip() else {}  # pyright: ignore[reportUnknownMemberType]


def has_comments(text: str) -> bool:
    """True if `//` or `/* */` appears outside a string. Handles `\\` escapes inside strings."""
    in_string = False
    quote = ""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 1
            elif ch == quote:
                in_string = False
        elif ch in "\"'":
            in_string, quote = True, ch
        elif ch == "/" and i + 1 < n and text[i + 1] in "/*":
            return True
        i += 1
    return False
