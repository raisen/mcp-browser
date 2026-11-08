"""Keyboard interaction and UI navigation tests for McpBrowserApp."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest
from mcp_browser.tui.app import McpBrowserApp
from mcp_browser.tui.models import ServerSelected
from mcp_browser.tui.screens.help_modal import HelpModal
from mcp_browser.tui.widgets.server_detail import ServerDetailWidget
from mcp_browser.tui.widgets.server_list import ServerListWidget
from mcp_browser_core.catalog_models import CatalogEntry
from mcp_browser_core.discovery import active_user_file
from mcp_browser_core.models import ServerEntry
from mcp_browser_core.paths import Paths
from mcp_browser_core.specs import REGISTRY
from textual.widgets import Button, Input, TabbedContent, Tree

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "configs"


def setup_desktop_fixture(paths: Paths) -> None:
    dest = active_user_file(paths, REGISTRY["claude-desktop"])
    assert dest is not None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / "claude-desktop.json", dest)


@pytest.mark.anyio
async def test_keyboard_navigation_and_selection(paths: Paths) -> None:
    setup_desktop_fixture(paths)
    app = McpBrowserApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.pause()
        s_list = app.query_one(ServerListWidget)
        detail = app.query_one(ServerDetailWidget)
        assert len(app.discovered_entries) >= 2

        first_entry = app.selected_entry
        assert first_entry is not None
        assert detail.entry == first_entry

        # Select second entry via tree event
        second_entry = app.discovered_entries[1]
        s_list.post_message(ServerSelected(second_entry))
        await pilot.pause()

        assert app.selected_entry == second_entry
        assert detail.entry == second_entry


@pytest.mark.anyio
async def test_search_filtering_and_focus(paths: Paths) -> None:
    setup_desktop_fixture(paths)
    app = McpBrowserApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.pause()
        s_list = app.query_one(ServerListWidget)
        search_input = s_list.query_one("#server-search", Input)
        tree = cast("Tree[ServerEntry | None]", s_list.query_one("#server-tree", Tree))

        assert not search_input.has_focus

        # Press slash to focus search input
        await pilot.press("slash")
        await pilot.pause()
        assert search_input.has_focus

        # Type filter query
        search_input.value = "files"
        await pilot.pause()
        assert len(s_list.visible_entries) == 1
        assert s_list.visible_entries[0].name.lower() == "files"

        # Press enter to submit search and return focus to tree
        await pilot.press("enter")
        await pilot.pause()
        assert tree.has_focus

        # Clear filter
        search_input.value = ""
        await pilot.pause()
        assert len(s_list.visible_entries) == len(app.discovered_entries)


@pytest.mark.anyio
async def test_tab_switching_keys_and_actions(paths: Paths) -> None:
    setup_desktop_fixture(paths)
    app = McpBrowserApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.pause()
        detail = app.query_one(ServerDetailWidget)
        tabs = detail.query_one(TabbedContent)

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

        # Cycle tabs with [ and ]
        await pilot.press("]")
        await pilot.pause()
        assert tabs.active == "tab-tools"

        await pilot.press("[")
        await pilot.pause()
        assert tabs.active == "tab-overview"

        # Direct actions
        app.action_tab_tools()
        assert tabs.active == "tab-tools"
        app.action_tab_resources()
        assert tabs.active == "tab-resources"
        app.action_tab_prompts()
        assert tabs.active == "tab-prompts"
        app.action_tab_overview()
        assert tabs.active == "tab-overview"
        app.action_next_tab()
        assert tabs.active == "tab-tools"
        app.action_prev_tab()
        assert tabs.active == "tab-overview"


@pytest.mark.anyio
async def test_help_modal_dismiss_variants(paths: Paths) -> None:
    app = McpBrowserApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.pause()

        # Open and dismiss via escape
        await pilot.press("?")
        await pilot.pause()
        assert isinstance(app.screen, HelpModal)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpModal)

        # Open and dismiss via button click
        await pilot.press("?")
        await pilot.pause()
        modal = cast("HelpModal", app.screen)
        close_btn = modal.query_one("#btn-close-help", Button)
        close_btn.press()
        await pilot.pause()
        assert not isinstance(app.screen, HelpModal)

        # Open and dismiss via enter key
        app.action_help()
        await pilot.pause()
        assert isinstance(app.screen, HelpModal)
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, HelpModal)


@pytest.mark.anyio
async def test_refresh_and_connect_actions(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    setup_desktop_fixture(paths)
    app = McpBrowserApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.selected_entry is not None
        target_entry = app.selected_entry

        mock_cat = CatalogEntry(
            entry_id=target_entry.id,
            fingerprint="fp-mock",
            scanned_at=datetime.now(UTC),
            status="ok",
            tools=[],
            resources=[],
            prompts=[],
        )
        monkeypatch.setattr(app.backend, "scan_server", AsyncMock(return_value=mock_cat))

        # Test connect key 'c'
        await pilot.press("c")
        await pilot.pause()
        assert app.catalog_map[target_entry.id] == mock_cat
        assert "[● 2 Servers | 1 Verified]" in str(app.stats_view.content)

        # Test refresh key 'r'
        await pilot.press("r")
        await pilot.pause()
        assert len(app.discovered_entries) >= 2

        # Connect button click
        btn = app.query_one("#btn-connect-scan", Button)
        btn.press()
        await pilot.pause()
        assert app.catalog_map[target_entry.id] == mock_cat
