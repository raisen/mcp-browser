"""Tiny MCP server used by the tests: `fixture_server.py [stdio|streamable-http|sse] [port]`.

Set FIXTURE_PID_FILE to have it write its pid on startup (orphan checks)."""

from __future__ import annotations

import logging
import os
import sys

import anyio
from mcp.server.mcpserver import MCPServer

logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[logging.StreamHandler(sys.stderr)])

server = MCPServer("fixture")


@server.tool()
def echo(text: str) -> str:
    return text


@server.tool()
def add(a: int, b: int) -> int:
    return a + b


@server.tool()
async def slow(seconds: float) -> str:
    await anyio.sleep(seconds)
    return "done"


@server.tool()
def fail() -> str:
    raise RuntimeError("boom")


@server.resource("res://a")
def resource_a() -> str:
    return "resource a"


@server.resource("env://var/{name}")
def env_value(name: str) -> str:
    return os.environ.get(name, "<unset>")


@server.prompt()
def greet(name: str) -> str:
    return f"Hello {name}"


def main() -> None:
    pid_file = os.environ.get("FIXTURE_PID_FILE")
    if pid_file:
        with open(pid_file, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
    print("fixture-server-started", file=sys.stderr, flush=True)
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport == "stdio":
        server.run("stdio")
    else:
        server.run(transport, host="127.0.0.1", port=int(sys.argv[2]))  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
