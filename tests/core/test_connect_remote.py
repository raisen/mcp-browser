from __future__ import annotations

import socket
import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import closing, contextmanager
from pathlib import Path

import anyio
import pytest
from mcp_browser_core.connect import ConnectOptions, session
from mcp_browser_core.errors import ConnectFailed
from mcp_browser_core.models import HttpTransport, ServerEntry, SseTransport
from mcp_browser_core.oauth import OAuthHook
from mcp_browser_core.paths import Paths
from mcp_browser_core.transports import choose_auth

FIXTURE = str(Path(__file__).parents[1] / "fixtures" / "fixture_server.py")
OPTS = ConnectOptions(connect_timeout=30, call_timeout=30)


def free_port() -> int:
    with closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def remote_server(transport: str) -> Generator[int, None, None]:
    port = free_port()
    proc = subprocess.Popen([sys.executable, FIXTURE, transport, str(port)], stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.1)
        yield port
    finally:
        proc.kill()
        proc.wait()


def remote_entry(port: int, kind: str, path: str) -> ServerEntry:
    url = f"http://127.0.0.1:{port}{path}"
    t = HttpTransport(url=url) if kind == "http" else SseTransport(url=url)
    return ServerEntry(id="r", name="r", client_id="x", scope="user", config_path="/x", transport=t)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kind", "server_transport", "path"), [("http", "streamable-http", "/mcp"), ("sse", "sse", "/sse")]
)
async def test_remote_round_trip(paths: Paths, kind: str, server_transport: str, path: str) -> None:
    with remote_server(server_transport) as port:
        entry = remote_entry(port, kind, path)
        async with session(entry, paths, OPTS, None, limiter=anyio.CapacityLimiter(8)) as s:
            assert sorted(t.name for t in await s.list_tools()) == ["add", "echo", "fail", "slow"]
            result = await s.call_tool("add", {"a": 2, "b": 5}, 20)
            assert result.structured == {"result": 7}
            assert s.stderr_tail == ""


@pytest.mark.anyio
async def test_refused_connection_is_connect_failed(paths: Paths) -> None:
    entry = remote_entry(free_port(), "http", "/mcp")
    with pytest.raises(ConnectFailed) as info:
        async with session(entry, paths, OPTS, None, limiter=anyio.CapacityLimiter(8)):
            pass
    assert not isinstance(info.value, BaseExceptionGroup)


def test_static_authorization_header_skips_oauth(paths: Paths) -> None:
    hook = OAuthHook("http://127.0.0.1:1/oauth/callback", open_browser=lambda _url: True)
    plain = HttpTransport(url="https://h/mcp")
    assert choose_auth(plain, paths, None) is None  # no hook, no OAuth
    assert choose_auth(plain, paths, hook) is not None
    for header in ("Authorization", "authorization"):
        with_header = HttpTransport(url="https://h/mcp", headers={header: "Bearer x"})
        assert choose_auth(with_header, paths, hook) is None
