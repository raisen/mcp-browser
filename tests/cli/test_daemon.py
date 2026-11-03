"""Daemon logic with Popen, signals and the health probe mocked."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import webbrowser
from typing import Any

import pytest
from mcp_browser import cli, daemon, runtime
from mcp_browser.runtime import PidInfo
from mcp_browser_core.paths import Paths

from . import fakes


class FakeProc:
    def __init__(self, pid: int = 555, exited: bool = False) -> None:
        self.pid = pid
        self._exited = exited

    def poll(self) -> int | None:
        return 1 if self._exited else None


def open_stub(address: str) -> bool:
    return True


@pytest.fixture(autouse=True)
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", fakes.no_sleep)
    monkeypatch.setattr(runtime, "port_free", fakes.port_free)
    monkeypatch.setattr(webbrowser, "open", open_stub)


def capture_popen(monkeypatch: pytest.MonkeyPatch, proc: FakeProc) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def fake(cmd: list[str], **kwargs: Any) -> FakeProc:
        seen["cmd"], seen["kwargs"] = cmd, kwargs
        return proc

    monkeypatch.setattr(subprocess, "Popen", fake)
    return seen


def test_command_unfrozen_uses_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    cmd = daemon.serve_command(8765)
    assert cmd[:3] == [sys.executable, "-m", "mcp_browser"]
    assert cmd[3:6] == ["serve", "--no-open", "--detached"]


def test_command_frozen_uses_executable_with_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    cmd = daemon.serve_command(9000)
    assert cmd == [sys.executable, "serve", "--no-open", "--detached", "--port", "9000"]


def test_start_spawns_detached_and_writes_pid(
    paths: Paths, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = capture_popen(monkeypatch, FakeProc(pid=555))
    calls = [0]

    def probe(port: int, timeout: float = 1.0) -> dict[str, Any] | None:
        calls[0] += 1
        return None if calls[0] == 1 else {"ok": True, "pid": 555}

    monkeypatch.setattr(runtime, "probe", probe)
    assert cli.run(["start", "--no-open"], paths) == 0
    kwargs = seen["kwargs"]
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["stderr"] is kwargs["stdout"]
    if sys.platform == "win32":
        assert kwargs["creationflags"]
    else:
        assert kwargs["start_new_session"] is True
    assert runtime.read_pid(paths) == PidInfo(555, 8765)
    out = capsys.readouterr().out
    assert "#token=" in out
    assert runtime.load_token(paths) not in paths.log_file.read_text()


def test_start_reports_early_exit(
    paths: Paths, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    capture_popen(monkeypatch, FakeProc(exited=True))
    monkeypatch.setattr(runtime, "probe", fakes.probe_none)
    assert cli.run(["start"], paths) == 1
    assert "server.log" in capsys.readouterr().err
    assert not paths.pid_file.exists()


def test_stop_signals_confirmed_pid(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime.write_pid(paths, PidInfo(900, 8765))
    alive = [True]
    live = fakes.probe_pid(900)

    def probe(port: int, timeout: float = 1.0) -> dict[str, Any] | None:
        return live(port, timeout) if alive[0] else None

    monkeypatch.setattr(runtime, "probe", probe)
    kills: list[tuple[int, int]] = []

    def fake_kill(pid: int, sig: int) -> None:
        kills.append((pid, sig))
        alive[0] = False

    monkeypatch.setattr(os, "kill", fake_kill)
    assert "stopped" in daemon.stop(paths)
    assert kills == [(900, signal.SIGTERM)]
    assert not paths.pid_file.exists()


def test_stop_refuses_mismatched_pid(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime.write_pid(paths, PidInfo(900, 8765))
    monkeypatch.setattr(runtime, "probe", fakes.probe_pid(1))
    monkeypatch.setattr(os, "kill", fakes.no_kill)
    assert "stale" in daemon.stop(paths)
    assert not paths.pid_file.exists()


def test_stop_dead_server_clears_file(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime.write_pid(paths, PidInfo(900, 8765))
    monkeypatch.setattr(runtime, "probe", fakes.probe_none)
    monkeypatch.setattr(os, "kill", fakes.no_kill)
    assert "stale" in daemon.stop(paths)
    assert not paths.pid_file.exists()


def test_stop_without_pid_file(paths: Paths) -> None:
    assert daemon.stop(paths) == "not running"


def test_stop_timeout_keeps_pid_file(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime.write_pid(paths, PidInfo(900, 8765))
    monkeypatch.setattr(runtime, "probe", fakes.probe_pid(900))
    monkeypatch.setattr(os, "kill", fakes.kill_noop)
    clock = [0.0]

    def monotonic() -> float:
        clock[0] += 3.0
        return clock[0]

    monkeypatch.setattr(time, "monotonic", monotonic)
    assert "did not exit" in daemon.stop(paths)
    assert paths.pid_file.exists()
