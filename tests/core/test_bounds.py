"""Paging caps, result truncation and the whole-listing deadline, against a fake SDK client."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import anyio
import pytest
from mcp import types
from mcp_browser_core import bounds
from mcp_browser_core.bounds import collect_pages, fit, fit_list
from mcp_browser_core.connect import Session
from mcp_browser_core.errors import OperationTimeout


def page(items: list[str], cursor: str | None) -> Any:
    return SimpleNamespace(items=items, next_cursor=cursor)


@pytest.mark.anyio
async def test_page_cap_item_cap_and_repeated_cursor() -> None:
    calls: list[str | None] = []

    async def endless(cursor: str | None) -> Any:
        calls.append(cursor)
        return page(["x"], f"c{len(calls)}")

    assert len(await collect_pages(endless, lambda p: p.items)) == bounds.MAX_PAGES
    assert len(calls) == 100

    async def fat(cursor: str | None) -> Any:
        return page(["y"] * 3000, "more")

    assert len(await collect_pages(fat, lambda p: p.items)) == bounds.MAX_ITEMS

    seen: list[str | None] = []

    async def looping(cursor: str | None) -> Any:
        seen.append(cursor)
        return page(["z"], "same")

    await collect_pages(looping, lambda p: p.items)
    assert seen == [None, "same"]  # the repeated cursor ends the walk after one extra page


def test_fit_cuts_longest_string_and_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    small, cut = fit({"a": "ok"}, 1000)
    assert small == {"a": "ok"} and not cut
    big, cut = fit({"a": "ok", "b": "x" * 5000}, 1000)
    assert cut and big["a"] == "ok" and len(big["b"]) < 1000
    many, cut = fit({"l": list(range(10000))}, 1000)
    assert cut and len(many["l"]) < 1000


def test_fit_list_marks_trimmed_content() -> None:
    items = [{"text": "short"}, {"text": "y" * 5000}]
    out = fit_list(items, 500)
    assert out[-1]["truncated"] is True and "truncated" not in out[0]
    assert fit_list([{"text": "s"}], 500) == [{"text": "s"}]


class FakeClient:
    server_capabilities = SimpleNamespace(tools=True)

    def __init__(self, text: str = "") -> None:
        self.text = text

    async def call_tool(self, name: str, args: dict[str, Any]) -> types.CallToolResult:
        return types.CallToolResult(content=[types.TextContent(type="text", text=self.text)])

    async def list_tools(self, cursor: str | None = None) -> Any:
        await anyio.sleep(30)


@pytest.mark.anyio
async def test_oversized_tool_result_is_truncated_with_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bounds, "MAX_RESULT_BYTES", 2000)
    s = Session(FakeClient("q" * 50_000), None, 5)  # pyright: ignore[reportArgumentType]
    result = await s.call_tool("t", {}, 5)
    assert result.truncated and len(result.content[0]["text"]) < 2000
    ok = await Session(FakeClient("fine"), None, 5).call_tool("t", {}, 5)  # pyright: ignore[reportArgumentType]
    assert not ok.truncated and ok.content[0]["text"] == "fine"


@pytest.mark.anyio
async def test_listing_runs_under_one_deadline() -> None:
    s = Session(FakeClient(), None, 0.3)  # pyright: ignore[reportArgumentType]
    with pytest.raises(OperationTimeout):
        await s.list_tools()
