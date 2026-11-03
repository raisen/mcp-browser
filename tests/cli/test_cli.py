"""CLI parsing, token handling and command flows. Network, Popen and signals are mocked."""

from __future__ import annotations

import os
import stat
import sys
import webbrowser

import pytest
from mcp_browser import cli, runtime
from mcp_browser.runtime import PidInfo
from mcp_browser_core.paths import Paths

from . import fakes


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Nothing talks to a real port or browser; returns the URLs 'opened'."""
    opened: list[str] = []

    def fake_open(address: str) -> bool:
        opened.append(address)
        return True

    monkeypatch.setattr(runtime, "probe", fakes.probe_none)
    monkeypatch.setattr(runtime, "port_free", fakes.port_free)
    monkeypatch.setattr(runtime, "pid_alive", fakes.alive)
    monkeypatch.setattr(webbrowser, "open", fake_open)
    return opened


def healthy(monkeypatch: pytest.MonkeyPatch, pid: int, port: int = 8765) -> None:
    monkeypatch.setattr(runtime, "probe", fakes.probe_pid(pid, port))
    monkeypatch.setattr(runtime, "read_pid", fakes.pid_file(pid, port))  # as a real run's pid file


def test_defaults_to_serve() -> None:
    opts = cli.parse_options([])
    assert (opts.command, opts.port, opts.no_open) == ("serve", 8765, False)


def test_port_and_no_open_before_or_after_subcommand() -> None:
    assert cli.parse_options(["--port", "9000", "start"]).port == 9000
    after = cli.parse_options(["start", "--port", "9001", "--no-open"])
    assert (after.port, after.no_open) == (9001, True)


@pytest.mark.parametrize("flag", ["--host", "--allow-remote"])
def test_no_remote_flags(flag: str) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.parse_options([flag, "0.0.0.0"])
    assert exc.value.code == 2


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.parse_options(["--help"])
    assert exc.value.code == 0
    assert "status" in capsys.readouterr().out


def test_token_created_once_with_private_mode(paths: Paths) -> None:
    first = runtime.load_token(paths)
    assert len(first) >= 32
    assert runtime.load_token(paths) == first
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(paths.token_file).st_mode) == 0o600


def test_status_stopped(paths: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.run(["status"], paths) == 1
    assert "stopped" in capsys.readouterr().out


def test_status_running(
    paths: Paths, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime.write_pid(paths, PidInfo(4242, 8765))
    healthy(monkeypatch, 4242)
    assert cli.run(["status"], paths) == 0
    out = capsys.readouterr().out
    assert "4242" in out
    assert "#token=" not in out


def test_stale_pid_file_is_cleaned(paths: Paths) -> None:
    runtime.write_pid(paths, PidInfo(4242, 8765))
    assert cli.run(["status"], paths) == 1
    assert not paths.pid_file.exists()


def test_open_when_running_prints_tokenized_url(
    paths: Paths, monkeypatch: pytest.MonkeyPatch, no_network: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    healthy(monkeypatch, 77)
    monkeypatch.setattr(sys, "platform", "darwin")  # Linux opens a launcher file instead
    assert cli.run(["open"], paths) == 0
    token = runtime.load_token(paths)
    assert no_network == [f"http://127.0.0.1:8765/#token={token}"]
    assert token in capsys.readouterr().out


def test_open_when_stopped_is_friendly(paths: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.run(["open"], paths) == 1
    assert "mcp-browser start" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["serve", "start"])
def test_already_running_prints_url_instead_of_crashing(
    command: str, paths: Paths, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    healthy(monkeypatch, 77)
    assert cli.run([command, "--no-open"], paths) == 0
    out = capsys.readouterr().out
    assert "already running" in out
    assert "http://127.0.0.1:8765/#token=" in out


@pytest.mark.parametrize("command", ["serve", "start"])
def test_port_in_use_is_friendly(
    command: str, paths: Paths, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(runtime, "port_free", fakes.port_busy)
    assert cli.run([command, "--port", "9100"], paths) == 1
    err = capsys.readouterr().err
    assert "9100" in err
    assert "--port" in err
