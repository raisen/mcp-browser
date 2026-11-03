"""Proves the SDK call forms documented in PLAN.md section 7 against the installed `mcp` package."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import TextIO, cast

import anyio
import pytest
from mcp import Client, MCPError, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = """
import sys
from mcp.server.mcpserver import MCPServer
s = MCPServer("smoke")

@s.tool()
def add(a: int, b: int) -> int:
    return a + b

@s.tool()
def fail() -> str:
    raise RuntimeError("boom")

print("smoke-stderr", file=sys.stderr, flush=True)
s.run("stdio")
"""


def leaves(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        group = cast("BaseExceptionGroup[BaseException]", exc)
        return [leaf for sub in group.exceptions for leaf in leaves(sub)]
    return [exc]


@pytest.mark.anyio
async def test_stdio_round_trip_with_stderr_capture(tmp_path: Path) -> None:
    script = tmp_path / "server.py"
    script.write_text(SERVER, encoding="utf-8")
    params = StdioServerParameters(command=sys.executable, args=[str(script)], env={"X": "1"})
    with tempfile.TemporaryFile("w+b") as err:
        with anyio.fail_after(60):
            async with Client(stdio_client(params, errlog=cast("TextIO", err)), cache=None) as c:
                tools = await c.list_tools()
                assert sorted(t.name for t in tools.tools) == ["add", "fail"]
                assert tools.next_cursor is None
                assert tools.tools[0].input_schema["type"] == "object"
                result = await c.call_tool("add", {"a": 1, "b": 2})
                assert result.is_error is False
                assert result.structured_content == {"result": 3}
                assert result.content[0].model_dump(mode="json", exclude_none=True)["text"] == "3"
                assert (await c.call_tool("fail", {})).is_error is True
        err.seek(0)
        assert b"smoke-stderr" in err.read()


@pytest.mark.anyio
async def test_startup_failures_arrive_wrapped(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        with anyio.fail_after(30):
            async with Client(stdio_client(StdioServerParameters(command="/no/such/command")), cache=None):
                pass
    script = tmp_path / "exits.py"
    script.write_text("import sys; sys.exit(3)", encoding="utf-8")
    with tempfile.TemporaryFile("w+b") as err, pytest.raises(BaseExceptionGroup) as info:
        with anyio.fail_after(30):
            params = StdioServerParameters(command=sys.executable, args=[str(script)])
            async with Client(stdio_client(params, errlog=cast("TextIO", err)), cache=None):
                pass
    assert any(isinstance(leaf, MCPError) for leaf in leaves(info.value))
