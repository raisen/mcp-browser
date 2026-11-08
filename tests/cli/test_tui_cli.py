"""Tests for TUI CLI option parsing, subcommand dispatch, and app filter options."""

from __future__ import annotations

import pytest
from mcp_browser import cli
from mcp_browser.runtime import DEFAULT_PORT
from mcp_browser.tui.app import McpBrowserApp
from mcp_browser.tui.widgets.server_list import ServerListWidget
from mcp_browser_core.paths import Paths
from textual.widgets import Input


def test_cli_tui_defaults() -> None:
    opts = cli.parse_options(["tui"])
    assert opts.command == "tui"
    assert opts.port == DEFAULT_PORT
    assert opts.project is None
    assert opts.filter is None
    assert opts.no_open is False


def test_cli_tui_flags() -> None:
    opts = cli.parse_options(["tui", "--filter", "github", "--project", "/workspace/repo", "--port", "5432"])
    assert opts.command == "tui"
    assert opts.filter == "github"
    assert opts.project == "/workspace/repo"
    assert opts.port == 5432


def test_cli_global_flags_with_tui() -> None:
    opts = cli.parse_options(["--port", "7777", "--project", "/my/proj", "--filter", "sqlite", "tui"])
    assert opts.command == "tui"
    assert opts.port == 7777
    assert opts.project == "/my/proj"
    assert opts.filter == "sqlite"


def test_cli_tui_help(capsys: pytest.CaptureFixture[str]) -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["tui", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--project" in out
    assert "--filter" in out


def test_cli_tui_run_dispatch(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[Paths, cli.Options]] = []

    def fake_cmd_tui(p: Paths, o: cli.Options) -> int:
        captured.append((p, o))
        return 42

    monkeypatch.setattr(cli, "cmd_tui", fake_cmd_tui)
    exit_code = cli.run(["tui", "--filter", "test-filt"], paths)
    assert exit_code == 42
    assert len(captured) == 1
    assert captured[0][0] == paths
    assert captured[0][1].filter == "test-filt"


def test_cmd_tui_calls_run_tui(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    opts = cli.parse_options(["tui"])
    called: list[tuple[Paths, cli.Options]] = []

    def fake_run_tui(p: Paths, o: cli.Options) -> int:
        called.append((p, o))
        return 0

    import mcp_browser.tui.app as tui_app_mod

    monkeypatch.setattr(tui_app_mod, "run_tui", fake_run_tui)
    assert cli.cmd_tui(paths, opts) == 0
    assert len(called) == 1
    assert called[0][0] == paths


def test_run_tui_function(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_browser.tui.app import run_tui

    def fake_run_seven(_app: McpBrowserApp) -> int:
        return 7

    def fake_run_none(_app: McpBrowserApp) -> None:
        return None

    monkeypatch.setattr(McpBrowserApp, "run", fake_run_seven)
    assert run_tui(paths) == 7

    monkeypatch.setattr(McpBrowserApp, "run", fake_run_none)
    assert run_tui(paths) == 0


@pytest.mark.anyio
async def test_app_initializes_with_filter_opt(paths: Paths) -> None:
    opts = cli.parse_options(["tui", "--filter", "prefilled_search"])
    app = McpBrowserApp(paths=paths, opts=opts)
    async with app.run_test() as pilot:
        await pilot.pause()
        s_list = app.query_one(ServerListWidget)
        assert s_list.filter_query == "prefilled_search"
        search_input = s_list.query_one("#server-search", Input)
        assert search_input.value == "prefilled_search"
