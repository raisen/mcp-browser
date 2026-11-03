from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp_browser_core.connect import ConnectOptions, flatten, map_error, session
from mcp_browser_core.errors import (
    ConnectFailed,
    OperationTimeout,
    UnresolvedPlaceholders,
    UnsupportedTransport,
)
from mcp_browser_core.models import HttpTransport, ServerEntry, StdioTransport
from mcp_browser_core.paths import Paths
from mcp_browser_core.transports import prepare

FIXTURE = str(Path(__file__).parents[1] / "fixtures" / "fixture_server.py")
OPTS = ConnectOptions(connect_timeout=60, call_timeout=60)


def entry(
    command: str = sys.executable,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> ServerEntry:
    t = StdioTransport(command=command, args=[FIXTURE] if args is None else args, env=env or {})
    return ServerEntry(
        id="e1", name="fx", client_id="codex", scope="user", config_path="/x", transport=t, extra=extra or {}
    )


@pytest.mark.anyio
async def test_connect_list_and_call(paths: Paths) -> None:
    async with session(entry(), paths, OPTS, None, limiter=anyio.CapacityLimiter(8)) as s:
        tools = await s.list_tools()
        assert sorted(t.name for t in tools) == ["add", "echo", "fail", "slow"]
        assert next(t for t in tools if t.name == "add").input_schema["type"] == "object"
        assert [r.uri for r in await s.list_resources()] == ["res://a"]
        assert [p.name for p in await s.list_prompts()] == ["greet"]
        result = await s.call_tool("add", {"a": 1, "b": 2}, 30)
        assert result.structured == {"result": 3} and result.content[0]["text"] == "3"
        assert not result.is_error and result.duration_ms >= 0
        assert (await s.call_tool("fail", {}, 30)).is_error
        assert (await s.call_tool("nope", {}, 30)).is_error
        assert (await s.read_resource("res://a"))[0]["text"] == "resource a"
        assert "Hello Ann" in str(await s.get_prompt("greet", {"name": "Ann"}))
        assert "fixture-server-started" in s.stderr_tail


@pytest.mark.anyio
async def test_slow_call_times_out(paths: Paths) -> None:
    async with session(entry(), paths, OPTS, None, limiter=anyio.CapacityLimiter(8)) as s:
        with pytest.raises(OperationTimeout):
            await s.call_tool("slow", {"seconds": 5}, 1)


@pytest.mark.anyio
async def test_timeout_inside_body_propagates_unchanged_through_teardown(paths: Paths) -> None:
    with pytest.raises(OperationTimeout):
        async with session(entry(), paths, OPTS, None, limiter=anyio.CapacityLimiter(8)) as s:
            await s.call_tool("slow", {"seconds": 5}, 0.5)


@pytest.mark.anyio
async def test_missing_command_names_it(paths: Paths) -> None:
    with pytest.raises(ConnectFailed, match="command not found: /no/such/cmd"):
        async with session(entry("/no/such/cmd", []), paths, OPTS, None, limiter=anyio.CapacityLimiter(8)):
            pass


@pytest.mark.anyio
async def test_server_exiting_at_startup_reports_stderr(paths: Paths) -> None:
    code = "import sys; print('bad config', file=sys.stderr); sys.exit(3)"
    with pytest.raises(ConnectFailed) as info:
        async with session(entry(args=["-c", code]), paths, OPTS, None, limiter=anyio.CapacityLimiter(8)):
            pass
    assert "bad config" in info.value.detail["stderr_tail"]
    assert not isinstance(info.value, BaseExceptionGroup)


@pytest.mark.anyio
async def test_silent_server_hits_connect_timeout(paths: Paths) -> None:
    opts = ConnectOptions(connect_timeout=1, call_timeout=5)
    with pytest.raises(OperationTimeout):
        async with session(
            entry(args=["-c", "import time; time.sleep(60)"]),
            paths,
            opts,
            None,
            limiter=anyio.CapacityLimiter(8),
        ):
            pass


@pytest.mark.anyio
async def test_stdio_env_filters_mcp_browser_and_expands(
    paths: Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCP_BROWSER_SECRET", "hidden")
    monkeypatch.setenv("PLAIN_VAR", "visible")
    monkeypatch.setenv("CODEX_PASS", "passed")
    e = entry(env={"FX": "${PLAIN_VAR}-x"}, extra={"env_vars": ["CODEX_PASS", "MCP_BROWSER_SECRET"]})
    async with session(e, paths, OPTS, None, limiter=anyio.CapacityLimiter(8)) as s:

        async def var(name: str) -> str:
            return (await s.read_resource(f"env://var/{name}"))[0]["text"]

        assert await var("MCP_BROWSER_SECRET") == "<unset>"
        assert await var("FX") == "visible-x"
        assert await var("CODEX_PASS") == "passed"


@pytest.mark.anyio
async def test_unresolved_placeholders_raise_before_spawning(paths: Paths) -> None:
    with pytest.raises(UnresolvedPlaceholders) as info:
        async with session(
            entry(args=["${NOT_SET_ANYWHERE}"]), paths, OPTS, None, limiter=anyio.CapacityLimiter(8)
        ):
            pass
    assert info.value.detail["placeholders"] == ["NOT_SET_ANYWHERE"]
    with pytest.raises(UnresolvedPlaceholders, match="cannot be resolved here") as info2:
        prepare(entry(args=["${input:api-key}"]), paths)
    assert info2.value.detail["placeholders"] == ["input:api-key"]


def test_transport_less_entry_is_unsupported(paths: Paths) -> None:
    e = ServerEntry(
        id="w", name="ws", client_id="x", scope="user", config_path="/x", error="websocket not supported"
    )
    with pytest.raises(UnsupportedTransport, match="websocket"):
        prepare(e, paths)


def test_codex_http_extras_are_honored(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_BEARER", "abc")
    monkeypatch.setenv("MY_TEAM", "t1")
    t = HttpTransport(url="https://h/mcp", headers={"X-A": "1"})
    extra = {
        "bearer_token_env_var": "MY_BEARER",
        "env_http_headers": {"X-Team": "MY_TEAM", "X-Skip": "UNSET_V"},
    }
    e = ServerEntry(
        id="h", name="h", client_id="codex", scope="user", config_path="/x", transport=t, extra=extra
    )
    out, _ = prepare(e, paths)
    assert isinstance(out, HttpTransport)
    assert out.headers == {"X-A": "1", "Authorization": "Bearer abc", "X-Team": "t1"}
    monkeypatch.delenv("MY_BEARER")
    with pytest.raises(UnresolvedPlaceholders) as info:
        prepare(e, paths)
    assert info.value.detail["placeholders"] == ["MY_BEARER"]


@pytest.mark.anyio
async def test_error_mapping_flattens_nested_groups() -> None:
    nested = ExceptionGroup("a", [ExceptionGroup("b", [FileNotFoundError("x")]), OSError("boom")])
    assert len(flatten(nested)) == 2
    mapped = map_error(nested, "tail", "mycmd")
    assert isinstance(mapped, ConnectFailed) and "command not found: mycmd" in mapped.message
    assert mapped.detail["stderr_tail"] == "tail"
    assert isinstance(map_error(ExceptionGroup("t", [TimeoutError()]), "", None), OperationTimeout)
