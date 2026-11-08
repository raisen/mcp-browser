"""Main Textual application for MCP Browser."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from mcp_browser_core import __version__
from mcp_browser_core.catalog_models import CatalogEntry
from mcp_browser_core.models import ServerEntry
from mcp_browser_core.paths import Paths, default_paths
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Footer, Static

from .backend import DirectCoreBackend
from .models import (
    ConnectRequested,
    GetPromptRequested,
    ReadResourceRequested,
    RunToolRequested,
    ServerSelected,
)
from .screens.confirm_modal import ConfirmModal
from .screens.help_modal import HelpModal
from .styles import TCSS_STYLES
from .widgets.server_detail import ServerDetailWidget
from .widgets.server_list import ServerListWidget

if TYPE_CHECKING:
    from ..cli import Options


class McpBrowserApp(App[int]):
    """Textual terminal UI for discovering, inspecting, and running MCP servers."""

    CSS = TCSS_STYLES

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit"),
        Binding("?", "help", "Help"),
        Binding("/", "focus_search", "Search"),
        Binding("c", "connect_server", "Connect/Scan"),
        Binding("r", "refresh_all", "Refresh"),
        Binding("1", "tab_overview", "1-4:Tabs"),
        Binding("2", "tab_tools", "Tools", show=False),
        Binding("3", "tab_resources", "Resources", show=False),
        Binding("4", "tab_prompts", "Prompts", show=False),
        Binding("[", "prev_tab", "Prev Tab", show=False),
        Binding("]", "next_tab", "Next Tab", show=False),
        Binding("f", "toggle_format", "Format", show=False),
        Binding("m", "toggle_maximize", "Maximize", show=False),
        Binding("ctrl+enter", "run_tool", "Run Tool", show=False),
    ]

    selected_entry: reactive[ServerEntry | None] = reactive(None)

    def __init__(self, paths: Paths | None = None, opts: Options | None = None) -> None:
        super().__init__()
        self.paths = paths or default_paths()
        self.opts = opts
        self.backend = DirectCoreBackend(self.paths)
        self.discovered_entries: list[ServerEntry] = []
        self.catalog_map: dict[str, CatalogEntry] = {}
        self._stats_view = Static("", id="header-stats")
        self.stats_view = self._stats_view

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-bar"):
            yield Static(f"mcp-browser v{__version__}", id="header-title")
            yield self._stats_view
            yield Static("? Help  q Quit", id="header-help")
        with Horizontal(id="main-container"):
            yield ServerListWidget(id="server-list")
            yield ServerDetailWidget(id="server-detail")
        yield Footer()

    def on_mount(self) -> None:
        """Discover servers and load catalog on startup."""
        self.refresh_data()
        self.query_one(ServerListWidget).focus_tree()
        if self.opts and getattr(self.opts, "filter", None):
            filt = str(self.opts.filter)
            s_list = self.query_one(ServerListWidget)
            s_list.filter_query = filt
            from textual.widgets import Input

            s_list.query_one("#server-search", Input).value = filt

    @work
    async def refresh_data(self) -> None:
        """Run discovery and load catalog cache in background."""
        self.backend.load_catalog()
        result = self.backend.discover_servers()
        self.discovered_entries = result.entries
        self.catalog_map = self.backend.all_cached_catalog()
        s_list = self.query_one(ServerListWidget)
        s_list.set_servers(self.discovered_entries, self.catalog_map)
        self._update_header_stats()

        if self.discovered_entries and self.selected_entry is None:
            self.selected_entry = self.discovered_entries[0]
            self.query_one(ServerDetailWidget).set_server(
                self.selected_entry, self.catalog_map.get(self.selected_entry.id)
            )

    def _update_header_stats(self) -> None:
        total = len(self.discovered_entries)
        ok_count = sum(1 for c in self.catalog_map.values() if c.status == "ok")
        self._stats_view.update(f"[● {total} Servers | {ok_count} Verified]")

    def on_server_selected(self, message: ServerSelected) -> None:
        self.selected_entry = message.entry
        self.query_one(ServerDetailWidget).set_server(message.entry, self.catalog_map.get(message.entry.id))

    def on_connect_requested(self, message: ConnectRequested) -> None:
        self.selected_entry = message.entry
        self.action_connect_server()

    async def ensure_trusted(self, entry: ServerEntry) -> bool:
        if self.backend.is_trusted(entry):
            return True
        detail = self.backend.confirmation_detail(entry)
        confirmed = await self.push_screen_wait(ConfirmModal(entry, detail))
        if confirmed:
            self.backend.mark_trusted(entry.id)
            return True
        return False

    _ensure_trusted = ensure_trusted

    @work
    async def action_connect_server(self) -> None:
        """Connect to and scan the currently selected server."""
        entry = self.selected_entry
        if entry is None:
            return
        if not await self._ensure_trusted(entry):
            return
        cat = await self.backend.scan_server(entry)
        self.catalog_map[entry.id] = cat
        self.query_one(ServerListWidget).update_catalog(self.catalog_map)
        self.query_one(ServerDetailWidget).set_server(entry, cat)
        self._update_header_stats()

    def action_refresh_all(self) -> None:
        self.refresh_data()

    def action_focus_search(self) -> None:
        self.query_one(ServerListWidget).focus_search()

    def action_tab_overview(self) -> None:
        self.query_one(ServerDetailWidget).switch_tab("tab-overview")

    def action_tab_tools(self) -> None:
        self.query_one(ServerDetailWidget).switch_tab("tab-tools")

    def action_tab_resources(self) -> None:
        self.query_one(ServerDetailWidget).switch_tab("tab-resources")

    def action_tab_prompts(self) -> None:
        self.query_one(ServerDetailWidget).switch_tab("tab-prompts")

    def action_prev_tab(self) -> None:
        self.query_one(ServerDetailWidget).prev_tab()

    def action_next_tab(self) -> None:
        self.query_one(ServerDetailWidget).next_tab()

    def action_run_tool(self) -> None:
        self.query_one(ServerDetailWidget).tool_runner.action_run_selected_tool()

    def action_toggle_format(self) -> None:
        self.query_one(ServerDetailWidget).tool_runner.action_toggle_format()

    def action_toggle_maximize(self) -> None:
        self.query_one(ServerDetailWidget).toggle_maximize()

    def action_help(self) -> None:
        self.push_screen(HelpModal())

    @work
    async def on_run_tool_requested(self, message: RunToolRequested) -> None:
        """Execute a tool on the selected server."""
        entry = self.selected_entry
        if entry is None:
            return
        if not await self._ensure_trusted(entry):
            self.query_one(ServerDetailWidget).tool_runner.set_error("Execution cancelled: Untrusted server.")
            return
        try:
            res = await self.backend.call_tool(entry, message.tool_name, message.args)
            self.query_one(ServerDetailWidget).tool_runner.set_result(res)
        except Exception as exc:
            self.query_one(ServerDetailWidget).tool_runner.set_error(str(exc))

    @work
    async def on_read_resource_requested(self, message: ReadResourceRequested) -> None:
        entry = self.selected_entry
        if entry is None:
            return
        if not await self._ensure_trusted(entry):
            self.query_one(ServerDetailWidget).resources_widget.set_error("Cancelled: Untrusted server.")
            return
        try:
            res = await self.backend.read_resource(entry, message.uri)
            self.query_one(ServerDetailWidget).resources_widget.set_result(res)
        except Exception as exc:
            self.query_one(ServerDetailWidget).resources_widget.set_error(str(exc))

    @work
    async def on_get_prompt_requested(self, message: GetPromptRequested) -> None:
        entry = self.selected_entry
        if entry is None:
            return
        if not await self._ensure_trusted(entry):
            self.query_one(ServerDetailWidget).prompts_widget.set_error("Cancelled: Untrusted server.")
            return
        try:
            res = await self.backend.get_prompt(entry, message.prompt_name, message.args)
            self.query_one(ServerDetailWidget).prompts_widget.set_result(res)
        except Exception as exc:
            self.query_one(ServerDetailWidget).prompts_widget.set_error(str(exc))


def run_tui(paths: Paths, opts: Any = None) -> int:
    """Launch the MCP Browser Textual TUI."""
    app = McpBrowserApp(paths=paths, opts=opts)
    result = app.run()
    return result if isinstance(result, int) else 0
