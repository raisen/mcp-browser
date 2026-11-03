"""Port squatting, the Linux launcher file and SIGTERM cleanup (all with synthetic listeners)."""

from __future__ import annotations

import json
import os
import signal
import stat
import sys
import threading
import types
import webbrowser
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

import pytest
from mcp_browser import cli, launcher, runtime
from mcp_browser.runtime import PidInfo
from mcp_browser_core.paths import Paths

from . import fakes


def recorder(sink: list[str]) -> Callable[[str], bool]:
    def record(address: str) -> bool:
        sink.append(address)
        return True

    return record


class Squatter(BaseHTTPRequestHandler):
    hits: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        self.hits.append(self.path + "|" + self.headers.get("Authorization", ""))
        body = json.dumps({"ok": True, "version": "0", "pid": os.getpid()}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return None


@pytest.fixture
def squatter() -> Iterator[int]:
    Squatter.hits.clear()
    srv = HTTPServer(("127.0.0.1", 0), Squatter)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield int(srv.server_address[1])
    srv.shutdown()
    srv.server_close()


def test_foreign_healthz_without_pid_file_is_not_ours(paths: Paths, squatter: int) -> None:
    assert runtime.find_running(paths, squatter) is None


def test_foreign_healthz_with_matching_pid_but_dead_process(paths: Paths, squatter: int) -> None:
    runtime.write_pid(paths, PidInfo(os.getpid(), squatter))  # squatter even reports this pid
    original = runtime.pid_alive
    try:
        runtime.pid_alive = fakes.dead  # type: ignore[assignment]
        assert runtime.find_running(paths, squatter) is None
    finally:
        runtime.pid_alive = original
    assert not paths.pid_file.exists()


def test_status_serve_and_open_never_use_foreign_listener(
    paths: Paths, squatter: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", recorder(opened))
    for command in ("status", "open", "serve", "start"):
        assert cli.run([command, "--port", str(squatter)], paths) == 1
    captured = capsys.readouterr()
    assert "taken by something other than mcp-browser" in captured.out + captured.err
    assert "running" not in captured.out.replace("is stopped", "")
    assert opened == []
    token = runtime.load_token(paths)
    assert token not in captured.out + captured.err
    assert all("Bearer" not in h and token not in h for h in Squatter.hits)


def test_linux_open_uses_private_launcher_not_url(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(webbrowser, "open", recorder(opened))
    monkeypatch.setattr(launcher, "REMOVE_AFTER", 3600.0)
    launcher.open_url(paths, "http://127.0.0.1:8765/#token=SYNTHETIC")
    page = paths.state_dir / launcher.LAUNCHER_NAME
    assert opened == [page.as_uri()]
    assert "SYNTHETIC" not in opened[0]
    assert "location.replace" in page.read_text(encoding="utf-8")
    if os.name != "nt":
        assert stat.S_IMODE(page.stat().st_mode) == 0o600
    launcher.remove_launcher(paths)
    assert not page.exists()


def test_other_platforms_open_the_url(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(webbrowser, "open", recorder(opened))
    launcher.open_url(paths, "http://127.0.0.1:8765/#token=SYNTHETIC")
    assert opened == ["http://127.0.0.1:8765/#token=SYNTHETIC"]
    assert not (paths.state_dir / launcher.LAUNCHER_NAME).exists()


def identity(settings: object) -> object:
    return settings


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_sigterm_handler_exits_so_pid_file_is_removed(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("uvicorn")

    def run(app: object, **kwargs: Any) -> None:
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        assert paths.pid_file.exists()
        handler(signal.SIGTERM, None)  # what a real SIGTERM triggers

    module.run = run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", module)
    import mcp_browser_server.app as server_app

    monkeypatch.setattr(server_app, "create_app", identity)
    monkeypatch.setattr(runtime, "probe", fakes.probe_none)
    monkeypatch.setattr(runtime, "port_free", fakes.port_free)
    previous = signal.getsignal(signal.SIGTERM)
    try:
        with pytest.raises(SystemExit):
            cli.run(["serve", "--no-open", "--port", "9201"], paths)
    finally:
        signal.signal(signal.SIGTERM, previous)
    assert not paths.pid_file.exists()
