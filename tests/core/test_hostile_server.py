"""A hostile stdio server cannot exhaust disk, leak expanded secrets or flood the log."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import anyio
import pytest
from mcp_browser_core.catalog import scan_one
from mcp_browser_core.connect import ConnectOptions, session
from mcp_browser_core.errors import ConnectFailed, OperationTimeout
from mcp_browser_core.models import ServerEntry, StdioTransport
from mcp_browser_core.paths import Paths
from mcp_browser_core.transports import STDERR_TAIL_BYTES, StderrCapture

OPTS = ConnectOptions(connect_timeout=20, call_timeout=20)


def stdio_entry(code: str, args: list[str] | None = None, env: dict[str, str] | None = None) -> ServerEntry:
    t = StdioTransport(command=sys.executable, args=["-c", code, *(args or [])], env=env or {})
    return ServerEntry(id="h", name="h", client_id="x", scope="user", config_path="/x", transport=t)


def test_stderr_capture_is_bounded_and_keeps_the_end(tmp_path: Path) -> None:
    cap = StderrCapture()
    code = (
        "import sys\nfor i in range(2000): sys.stderr.write('x' * 10000 + '\\n')\nsys.stderr.write('THE-END')"
    )
    subprocess.run([sys.executable, "-c", code], stderr=cap.stream, check=True)
    cap.close()
    tail = cap.tail()
    assert len(tail) <= STDERR_TAIL_BYTES and tail.endswith("THE-END")


@pytest.mark.anyio
async def test_flooding_server_error_carries_only_the_tail(paths: Paths) -> None:
    code = "import sys\nfor i in range(500): sys.stderr.write('f' * 10000)\nsys.stderr.write('LAST')\nsys.exit(2)"  # noqa: E501
    with pytest.raises(ConnectFailed) as info:
        async with session(stdio_entry(code), paths, OPTS, None, limiter=anyio.CapacityLimiter(2)):
            pass
    tail = info.value.detail["stderr_tail"]
    assert len(tail) <= STDERR_TAIL_BYTES and tail.endswith("LAST")


@pytest.mark.anyio
async def test_expanded_secrets_never_reach_errors_or_the_catalog(
    paths: Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MY_SECRET", "s3cr3t-real-value")
    code = "import sys; print('boom', sys.argv[1], sys.argv[2], file=sys.stderr); sys.exit(1)"
    entry = stdio_entry(code, ["--tag=${MY_SECRET}", "-e"], env={"K": "${MY_SECRET}"})
    with pytest.raises(ConnectFailed) as info:
        async with session(entry, paths, OPTS, None, limiter=anyio.CapacityLimiter(2)):
            pass
    assert "s3cr3t-real-value" not in info.value.detail["stderr_tail"]
    assert "•••" in info.value.detail["stderr_tail"]
    found = await scan_one(entry, paths, OPTS, anyio.CapacityLimiter(2), None)
    assert found.status == "error"
    assert "s3cr3t-real-value" not in found.model_dump_json()


@pytest.mark.anyio
async def test_non_json_stdout_logs_one_concise_line(paths: Paths, caplog: pytest.LogCaptureFixture) -> None:
    code = "import time; print('this is not json ' * 20, flush=True); time.sleep(30)"
    opts = ConnectOptions(connect_timeout=1.5, call_timeout=5)
    with (
        caplog.at_level(logging.ERROR, logger="mcp.client.stdio"),
        pytest.raises((OperationTimeout, ConnectFailed)),
    ):
        async with session(stdio_entry(code), paths, opts, None, limiter=anyio.CapacityLimiter(2)):
            pass
    records = [r for r in caplog.records if r.name == "mcp.client.stdio"]
    assert records and all(r.exc_info is None for r in records)
    assert all(r.getMessage().startswith("server wrote non-JSON to stdout") for r in records)
    assert all(len(r.getMessage()) < 200 for r in records)
