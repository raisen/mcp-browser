"""Foreground serve with uvicorn and create_app mocked: pid file lifecycle and token hygiene."""

from __future__ import annotations

import os
import sys
import types
from typing import Any

import pytest
from mcp_browser import cli, runtime
from mcp_browser_core.paths import Paths

from . import fakes


@pytest.fixture
def fake_uvicorn(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    calls: dict[str, Any] = {}
    module = types.ModuleType("uvicorn")

    def run(app: object, **kwargs: Any) -> None:
        calls["app"], calls["kwargs"] = app, kwargs
        calls["pid_during"] = runtime.read_pid(calls["paths"])

    module.run = run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", module)
    import mcp_browser_server.app as server_app

    def create_app(settings: object) -> object:
        calls["settings"] = settings
        return settings

    monkeypatch.setattr(server_app, "create_app", create_app)
    monkeypatch.setattr(runtime, "probe", fakes.probe_none)
    monkeypatch.setattr(runtime, "port_free", fakes.port_free)
    return calls


def test_serve_binds_loopback_and_tracks_pid(
    paths: Paths, fake_uvicorn: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    fake_uvicorn["paths"] = paths
    assert cli.run(["serve", "--no-open", "--port", "9200"], paths) == 0
    assert fake_uvicorn["kwargs"]["host"] == "127.0.0.1"
    assert fake_uvicorn["kwargs"]["port"] == 9200
    assert fake_uvicorn["settings"].port == 9200
    assert fake_uvicorn["pid_during"].pid == os.getpid()
    assert not paths.pid_file.exists()  # cleaned on exit
    assert "#token=" in capsys.readouterr().out


def test_detached_serve_never_prints_token(
    paths: Paths, fake_uvicorn: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    fake_uvicorn["paths"] = paths
    assert cli.run(["serve", "--no-open", "--detached"], paths) == 0
    captured = capsys.readouterr()
    assert runtime.load_token(paths) not in captured.out + captured.err
