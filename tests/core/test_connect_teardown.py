"""Teardown must never leave a fixture subprocess behind."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp_browser_core.connect import ConnectOptions, session
from mcp_browser_core.errors import OperationTimeout
from mcp_browser_core.models import ServerEntry, StdioTransport
from mcp_browser_core.paths import Paths

FIXTURE = str(Path(__file__).parents[1] / "fixtures" / "fixture_server.py")
OPTS = ConnectOptions(connect_timeout=60, call_timeout=60)


def entry(name: str = "fx", args: list[str] | None = None) -> ServerEntry:
    t = StdioTransport(command=sys.executable, args=[FIXTURE] if args is None else args)
    return ServerEntry(id=name, name=name, client_id="x", scope="user", config_path="/x", transport=t)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


async def assert_gone(pid_file: Path) -> None:
    pid = int(pid_file.read_text())
    with anyio.fail_after(15):
        while alive(pid):
            await anyio.sleep(0.1)


@pytest.fixture
def pid_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "fixture.pid"
    monkeypatch.setenv("FIXTURE_PID_FILE", str(target))
    return target


@pytest.mark.anyio
async def test_no_orphan_after_success(paths: Paths, pid_file: Path) -> None:
    async with session(entry(), paths, OPTS, None, limiter=anyio.CapacityLimiter(8)) as s:
        await s.list_tools()
        assert alive(int(pid_file.read_text()))
    await assert_gone(pid_file)


@pytest.mark.anyio
async def test_no_orphan_after_call_timeout(paths: Paths, pid_file: Path) -> None:
    with pytest.raises(OperationTimeout):
        async with session(entry(), paths, OPTS, None, limiter=anyio.CapacityLimiter(8)) as s:
            await s.call_tool("slow", {"seconds": 60}, 0.5)
    await assert_gone(pid_file)


@pytest.mark.anyio
async def test_no_orphan_after_connect_timeout(paths: Paths, pid_file: Path) -> None:
    code = f"import os,time; open({str(pid_file)!r},'w').write(str(os.getpid())); time.sleep(60)"
    opts = ConnectOptions(connect_timeout=1, call_timeout=5)
    with pytest.raises(OperationTimeout):
        async with session(entry(args=["-c", code]), paths, opts, None, limiter=anyio.CapacityLimiter(8)):
            pass
    await assert_gone(pid_file)


@pytest.mark.anyio
async def test_no_orphan_after_cancellation(paths: Paths, pid_file: Path) -> None:
    in_call = anyio.Event()

    async def work() -> None:
        async with session(entry(), paths, OPTS, None, limiter=anyio.CapacityLimiter(8)) as s:
            in_call.set()
            await s.call_tool("slow", {"seconds": 60}, 60)

    async with anyio.create_task_group() as tg:
        tg.start_soon(work)
        await in_call.wait()
        await anyio.sleep(0.3)
        tg.cancel_scope.cancel()
    await assert_gone(pid_file)


@pytest.mark.anyio
async def test_limiter_caps_concurrent_sessions(paths: Paths) -> None:
    limiter = anyio.CapacityLimiter(2)
    peak = 0
    done = 0

    async def one(i: int) -> None:
        nonlocal peak, done
        async with session(entry(f"s{i}"), paths, OPTS, None, limiter=limiter) as s:
            peak = max(peak, limiter.borrowed_tokens)
            await s.list_tools()
            await anyio.sleep(0.3)
        done += 1

    async with anyio.create_task_group() as tg:
        for i in range(5):
            tg.start_soon(one, i)
    assert done == 5 and peak == 2
    assert limiter.borrowed_tokens == 0
