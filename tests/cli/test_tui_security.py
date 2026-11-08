"""Tests for untrusted server security modal and approval flows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp_browser.tui.app import McpBrowserApp
from mcp_browser.tui.models import GetPromptRequested, ReadResourceRequested, RunToolRequested
from mcp_browser.tui.screens.confirm_modal import ConfirmModal
from mcp_browser.tui.widgets.resource_prompts import PromptsWidget, ResourcesWidget
from mcp_browser.tui.widgets.tool_runner import ToolRunnerWidget
from mcp_browser_core.catalog_models import CatalogEntry
from mcp_browser_core.models import HttpTransport, ServerEntry, StdioTransport
from mcp_browser_core.paths import Paths
from textual.widgets import Button


def test_confirm_modal_stdio_composition() -> None:
    entry = ServerEntry(
        id="u-stdio",
        name="workspace-server",
        client_id="vscode",
        scope="project",
        config_path="/project/.vscode/mcp.json",
        transport=StdioTransport(command="node", args=["server.js"]),
        untrusted=True,
    )
    detail: dict[str, Any] = {
        "kind": "stdio",
        "command": "node",
        "args": ["server.js"],
        "cwd": "/project",
        "env_vars": ["API_KEY", "SECRET_TOKEN"],
    }
    modal = ConfirmModal(entry, detail)
    assert modal.entry.name == "workspace-server"

    # Test actions
    dismissed_values: list[bool] = []
    modal.dismiss = lambda val: dismissed_values.append(val)  # type: ignore[method-assign]

    modal.action_cancel()
    assert dismissed_values == [False]

    modal.action_confirm()
    assert dismissed_values == [False, True]

    # Test button clicks
    btn_cancel = Button("Cancel", id="btn-cancel")
    modal.on_button_pressed(Button.Pressed(btn_cancel))
    assert dismissed_values[-1] is False

    btn_confirm = Button("Trust", id="btn-confirm")
    modal.on_button_pressed(Button.Pressed(btn_confirm))
    assert dismissed_values[-1] is True


def test_confirm_modal_http_composition() -> None:
    entry = ServerEntry(
        id="u-http",
        name="remote-server",
        client_id="claude-desktop",
        scope="project",
        config_path="/project/mcp.json",
        transport=HttpTransport(url="https://remote.mcp/sse"),
        untrusted=True,
    )
    detail: dict[str, Any] = {
        "kind": "http",
        "url": "https://remote.mcp/sse",
        "host": "remote.mcp",
    }
    modal = ConfirmModal(entry, detail)
    assert modal.entry.name == "remote-server"


@pytest.mark.anyio
async def test_app_untrusted_security_flow(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    app = McpBrowserApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.pause()
        entry = ServerEntry(
            id="untrusted-1",
            name="malicious-attempt",
            client_id="claude-code",
            scope="project",
            config_path="/repo/.mcp.json",
            transport=StdioTransport(command="rm", args=["-rf", "/"]),
            untrusted=True,
        )
        app.selected_entry = entry

        # 1. User cancels confirmation modal
        monkeypatch.setattr(app, "push_screen_wait", AsyncMock(return_value=False))
        mock_cat = CatalogEntry(
            entry_id=entry.id,
            fingerprint="fp1",
            scanned_at=datetime.now(UTC),
            status="ok",
            tools=[],
            resources=[],
            prompts=[],
        )
        scan_mock = AsyncMock(return_value=mock_cat)
        monkeypatch.setattr(app.backend, "scan_server", scan_mock)

        app.action_connect_server()
        await pilot.pause()
        assert not scan_mock.called
        assert not app.backend.is_trusted(entry)

        # 2. Tool run cancelled
        runner = app.query_one(ToolRunnerWidget)
        app.post_message(RunToolRequested("delete", {}))
        await pilot.pause()
        assert "Execution cancelled: Untrusted server." in runner.last_output

        # 3. Read resource cancelled
        res_widget = app.query_one(ResourcesWidget)
        app.post_message(ReadResourceRequested("res://secret"))
        await pilot.pause()
        assert "Cancelled: Untrusted server." in str(res_widget.output_view.content)

        # 4. Get prompt cancelled
        prompt_widget = app.query_one(PromptsWidget)
        app.post_message(GetPromptRequested("leak", {}))
        await pilot.pause()
        assert "Cancelled: Untrusted server." in str(prompt_widget.output_view.content)

        # 5. User confirms modal -> marked trusted, scan succeeds, subsequent calls skip modal
        monkeypatch.setattr(app, "push_screen_wait", AsyncMock(return_value=True))
        app.action_connect_server()
        await pilot.pause()
        assert scan_mock.called
        assert app.backend.is_trusted(entry)

        # Now ensure_trusted returns True without calling push_screen_wait again
        modal_mock = AsyncMock()
        monkeypatch.setattr(app, "push_screen_wait", modal_mock)
        assert await app.ensure_trusted(entry) is True
        assert not modal_mock.called
