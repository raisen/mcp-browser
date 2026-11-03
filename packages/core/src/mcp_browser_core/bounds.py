"""Limits that keep a hostile or buggy server from exhausting memory, time or the UI."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar, cast

MAX_PAGES = 100
MAX_ITEMS = 5000
MAX_RESULT_BYTES = 10 * 1024 * 1024

_T = TypeVar("_T")


class _Page(Protocol):
    @property
    def next_cursor(self) -> str | None: ...


async def collect_pages(
    fetch: Callable[[str | None], Awaitable[Any]], pick: Callable[[Any], list[_T]]
) -> list[_T]:
    """Follow `next_cursor` for at most 100 pages / 5000 items; a repeated cursor ends the walk."""
    out: list[_T] = []
    seen: set[str] = set()
    cursor: str | None = None
    for _ in range(MAX_PAGES):
        page = cast("_Page", await fetch(cursor))
        out += pick(page)
        if len(out) >= MAX_ITEMS:
            return out[:MAX_ITEMS]
        cursor = page.next_cursor
        if cursor is None or cursor in seen:
            break
        seen.add(cursor)
    return out


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8", "replace"))


def _walk(root: Any) -> tuple[list[tuple[Any, Any, int]], list[list[Any]]]:
    """String leaves as (container, key, length) and every list, found iteratively."""
    strings: list[tuple[Any, Any, int]] = []
    lists: list[list[Any]] = []
    stack: list[Any] = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            items: list[tuple[Any, Any]] = list(cast("dict[Any, Any]", node).items())
        elif isinstance(node, list):
            lst = cast("list[Any]", node)
            lists.append(lst)
            items = list(enumerate(lst))
        else:
            continue
        for key, child in items:
            if isinstance(child, str):
                strings.append((cast("Any", node), key, len(child)))
            else:
                stack.append(child)
    return strings, lists


def fit(value: Any, limit: int | None = None) -> tuple[Any, bool]:
    """`value` if its JSON is within `limit` bytes (default 10 MB), else a trimmed deep copy and True.
    The longest strings are cut first; if none is left, list tails are dropped."""
    limit = MAX_RESULT_BYTES if limit is None else limit
    size = _size(value)
    if size <= limit:
        return value, False
    data: Any = json.loads(json.dumps(value))
    for _ in range(200):
        over = size - limit
        if over <= 0:
            break
        strings, lists = _walk(data)
        biggest = max(strings, key=lambda s: s[2], default=None)
        if biggest is not None and biggest[2] > 0:
            node, key, length = biggest
            node[key] = node[key][: max(0, length - over)]
        else:
            longest = max(lists, key=len, default=None)
            if not longest:
                break
            del longest[len(longest) // 2 :]
        size = _size(data)
    return data, True


def fit_list(items: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    """Trim a list of content dicts; every trimmed or last-kept dict gets `"truncated": true`."""
    fitted, cut = fit(items, limit)
    if not cut:
        return items
    out = cast("list[dict[str, Any]]", fitted)
    for i, item in enumerate(out):
        if item != items[i] or i == len(out) - 1:
            item["truncated"] = True
    return out
