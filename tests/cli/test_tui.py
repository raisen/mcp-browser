"""Headless pilot tests for the Terminal User Interface."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from mcp_browser import cli
from mcp_browser.tui.app import McpBrowserApp
from mcp_browser.tui.models import RunToolRequested, entry_status
from mcp_browser.tui.screens.confirm_modal import ConfirmModal
from mcp_browser.tui.screens.help_modal import HelpModal
from mcp_browser.tui.widgets.server_detail import ServerDetailWidget
from mcp_browser.tui.widgets.server_list import ServerListWidget
from mcp_browser.tui.widgets.tool_runner import ToolRunnerWidget
from mcp_browser_core.catalog_models import CatalogEntry, ToolInfo
from mcp_browser_core.discovery import active_user_file
from mcp_browser_core.models import HttpTransport, ServerEntry, StdioTransport
from mcp_browser_core.paths import Paths
from mcp_browser_core.specs import REGISTRY
from textual.widgets import TabbedContent

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "configs"


def place_fixture(paths: Paths, spec_id: str, fixture: str) -> Path:
    dest = active_user_file(paths, REGISTRY[spec_id])
    assert dest is not None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / fixture, dest)
    return dest


@pytest.mark.anyio
async def test_tui_launches_and_populates_servers(paths: Paths) -> None:
    place_fixture(paths, "claude-desktop", "claude-desktop.json")
    app = McpBrowserApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.pause()
        s_list = app.query_one(ServerListWidget)
        assert s_list is not None
        assert len(app.discovered_entries) > 0
        assert app.selected_entry is not None
        detail = app.query_one(ServerDetailWidget)
        assert detail.entry is not None


@pytest.mark.anyio
async def test_tui_filtering(paths: Paths) -> None:
    place_fixture(paths, "claude-desktop", "claude-desktop.json")
    app = McpBrowserApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.pause()
        s_list = app.query_one(ServerListWidget)
        total_before = len(s_list.visible_entries)
        await pilot.press("slash")
        for ch in "github":
            await pilot.press(ch)
        await pilot.pause()
        assert len(s_list.visible_entries) < total_before
        assert all("github" in e.name.lower() for e in s_list.visible_entries)


@pytest.mark.anyio
async def test_tui_tab_switching(paths: Paths) -> None:
    place_fixture(paths, "claude-desktop", "claude-desktop.json")
    app = McpBrowserApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.pause()
        detail = app.query_one(ServerDetailWidget)
        tabs = detail.query_one(TabbedContent)
        assert tabs.active == "tab-overview"
        await pilot.press("2")
        await pilot.pause()
        assert tabs.active == "tab-tools"
        await pilot.press("3")
        await pilot.pause()
        assert tabs.active == "tab-resources"
        await pilot.press("4")
        await pilot.pause()
        assert tabs.active == "tab-prompts"
        await pilot.press("1")
        await pilot.pause()
        assert tabs.active == "tab-overview"


@pytest.mark.anyio
async def test_tui_help_modal(paths: Paths) -> None:
    app = McpBrowserApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("?")
        await pilot.pause()
        assert isinstance(app.screen, HelpModal)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpModal)


@pytest.mark.anyio
async def test_tui_confirm_modal_dismiss() -> None:
    t = StdioTransport(command="echo", args=["test"])
    entry = ServerEntry(
        id="u1",
        name="untrusted-srv",
        client_id="claude-desktop",
        scope="project",
        config_path="/path/to/repo/.mcp.json",
        transport=t,
        untrusted=True,
    )
    detail: dict[str, Any] = {
        "kind": "stdio",
        "command": "echo",
        "args": ["test"],
        "cwd": "/path/to/repo",
        "env_vars": ["SECRET_KEY"],
    }
    modal = ConfirmModal(entry, detail)
    assert modal.entry.name == "untrusted-srv"


@pytest.mark.anyio
async def test_tool_runner_interaction() -> None:
    runner = ToolRunnerWidget()
    tool = ToolInfo(
        name="test_tool",
        description="A test tool",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "search query"}},
            "required": ["query"],
        },
    )
    runner.set_tools([tool])
    assert runner.selected_tool == tool
    assert '"query": ""' in runner.args_text

    # Test invalid json error
    runner.args_text = "{invalid json"
    runner.action_run_selected_tool()
    assert "Invalid JSON" in runner.last_output

    # Test valid json trigger
    runner.args_text = '{"query": "hello"}'
    messages: list[RunToolRequested] = []
    runner.post_message = lambda m: messages.append(m) if isinstance(m, RunToolRequested) else None  # type: ignore[method-assign]
    runner.action_run_selected_tool()
    assert len(messages) == 1
    assert messages[0].tool_name == "test_tool"
    assert messages[0].args == {"query": "hello"}


def test_cli_tui_options_parsing(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    opts = cli.parse_options(["tui", "--filter", "git", "--project", "/tmp/proj"])
    assert opts.command == "tui"
    assert opts.filter == "git"
    assert opts.project == "/tmp/proj"

    def fake_cmd_tui(_paths: Paths, _opts: cli.Options) -> int:
        return 99

    monkeypatch.setattr(cli, "cmd_tui", fake_cmd_tui)
    assert cli.run(["tui"], paths) == 99


def test_entry_status_and_server_detail_rendering() -> None:
    e_clean = ServerEntry(
        id="s1",
        name="srv-clean",
        client_id="claude-desktop",
        scope="user",
        config_path="/x",
        transport=StdioTransport(command="echo", args=["hi"], cwd="/tmp", env={"A": "1"}),
    )
    e_err = ServerEntry(
        id="s2",
        name="srv-err",
        client_id="vscode",
        scope="project",
        config_path="/y",
        transport=None,
        error="Bad config format",
    )
    e_untr = ServerEntry(
        id="s3",
        name="srv-untr",
        client_id="zed",
        scope="project",
        config_path="/z",
        transport=HttpTransport(url="https://example.com/mcp", headers={"Authorization": "Bearer 123"}),
        untrusted=True,
    )

    # Status tests
    assert entry_status(e_clean, None) == "idle"
    assert entry_status(e_err, None) == "error"
    assert entry_status(e_untr, None) == "untrusted"

    now = datetime.now(UTC)
    cat_ok = CatalogEntry(
        entry_id="s1", fingerprint="fp", scanned_at=now, status="ok", tools=[], resources=[], prompts=[]
    )
    cat_err = CatalogEntry(
        entry_id="s1", fingerprint="fp", scanned_at=now, status="error", error="Fail", stderr_tail="err"
    )
    cat_auth = CatalogEntry(entry_id="s1", fingerprint="fp", scanned_at=now, status="needs_auth")

    assert entry_status(e_clean, cat_ok) == "connected"
    assert entry_status(e_clean, cat_err) == "error"
    assert entry_status(e_clean, cat_auth) == "untrusted"

    # Server detail widget rendering
    detail = ServerDetailWidget()
    detail.set_server(None, None)
    assert "No server selected" in str(detail.title_view.content)
    assert detail.connect_btn.disabled is True

    detail.set_server(e_clean, cat_ok)
    assert "srv-clean" in str(detail.title_view.content)
    assert "Stdio (process)" in str(detail.overview_view.content)
    assert "1 variables defined" in str(detail.overview_view.content)

    detail.set_server(e_untr, cat_err)
    assert "HTTP (remote)" in str(detail.overview_view.content)
    assert "Authorization" in str(detail.overview_view.content)
    assert "Stderr Log Tail" in str(detail.overview_view.content)
