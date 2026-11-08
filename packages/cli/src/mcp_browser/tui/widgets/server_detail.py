"""Detailed view panel containing header, metadata overview, and tabs."""

from __future__ import annotations

from typing import ClassVar

from mcp_browser_core.catalog_models import CatalogEntry
from mcp_browser_core.models import HttpTransport, ServerEntry, SseTransport, StdioTransport
from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Static, TabbedContent, TabPane

from ..models import BADGE_STYLES, BADGE_SYMBOLS, ConnectRequested, entry_status
from .resource_prompts import PromptsWidget, ResourcesWidget
from .tool_runner import ToolRunnerWidget


class ServerDetailWidget(Widget):
    """Right-hand panel inspecting a selected MCP server with interactive tabs."""

    TABS: ClassVar[tuple[str, ...]] = ("tab-overview", "tab-tools", "tab-resources", "tab-prompts")

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self.entry: ServerEntry | None = None
        self.catalog: CatalogEntry | None = None
        self.tool_runner = ToolRunnerWidget(id="tool-runner")
        self.resources_widget = ResourcesWidget(id="resources-widget")
        self.prompts_widget = PromptsWidget(id="prompts-widget")
        self._title = Static("[bold]Select a server[/]", id="header-title-text")
        self._sub = Static("Choose an MCP server from the left sidebar.", id="header-sub-text")
        self._connect_btn = Button("Connect (c)", variant="primary", id="btn-connect-scan")
        self._overview_text = Static("", id="overview-content")
        self.title_view = self._title
        self.sub_view = self._sub
        self.connect_btn = self._connect_btn
        self.overview_view = self._overview_text

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-container"):
            with Horizontal(id="server-header"):
                with Vertical(id="header-info"):
                    yield self._title
                    yield self._sub
                with Horizontal(id="header-actions"):
                    yield self._connect_btn
            with TabbedContent(id="detail-tabs"):
                with TabPane("Overview (1)", id="tab-overview"), VerticalScroll(id="overview-scroll"):
                    yield self._overview_text
                with TabPane("Tools (2)", id="tab-tools"):
                    yield self.tool_runner
                with TabPane("Resources (3)", id="tab-resources"):
                    yield self.resources_widget
                with TabPane("Prompts (4)", id="tab-prompts"):
                    yield self.prompts_widget

    def set_server(self, entry: ServerEntry | None, catalog: CatalogEntry | None) -> None:
        """Update active server and inspect its catalog metadata."""
        self.entry = entry
        self.catalog = catalog
        if entry is None:
            self._title.update("[dim]No server selected[/]")
            self._sub.update("")
            self._connect_btn.disabled = True
            self._overview_text.update("[dim]Select an MCP server from the left sidebar.[/]")
            self.tool_runner.set_tools([])
            self.resources_widget.set_resources([])
            self.prompts_widget.set_prompts([])
            return

        self._connect_btn.disabled = False
        badge = entry_status(entry, catalog)
        sym = BADGE_SYMBOLS[badge]
        style = BADGE_STYLES[badge]
        badge_str = f"[{style} bold]{sym} {badge.upper()}[/]"
        scope_str = f"[cyan]{escape(entry.client_id)}[/] • [yellow]{escape(entry.scope)}[/]"
        self._title.update(f"[bold]{escape(entry.name)}[/]  {badge_str}")
        self._sub.update(f"{scope_str} • {escape(entry.config_path)}")

        # Update tabs
        tools = catalog.tools if catalog else []
        resources = catalog.resources if catalog else []
        prompts = catalog.prompts if catalog else []
        self.tool_runner.set_tools(tools)
        self.resources_widget.set_resources(resources)
        self.prompts_widget.set_prompts(prompts)
        self._update_overview()

    def _update_overview(self) -> None:
        if self.entry is None:
            return
        e = self.entry
        lines: list[str] = [
            "[bold cyan]Server Metadata[/]",
            f"  [bold]Name:[/] {e.name}",
            f"  [bold]Client:[/] {e.client_id}",
            f"  [bold]Scope:[/] {e.scope}",
            f"  [bold]Enabled:[/] {'Yes' if e.enabled else 'No'}",
            f"  [bold]Config File:[/] {e.config_path}",
        ]
        if e.project:
            lines.append(f"  [bold]Project Directory:[/] {e.project}")

        lines.append("\n[bold cyan]Transport Details[/]")
        t = e.transport
        if isinstance(t, StdioTransport):
            lines.append("  [bold]Type:[/] Stdio (process)")
            lines.append(f"  [bold]Command:[/] [green]{t.command}[/]")
            if t.args:
                lines.append(f"  [bold]Arguments:[/] {' '.join(t.args)}")
            if t.cwd:
                lines.append(f"  [bold]CWD:[/] {t.cwd}")
            if t.env:
                lines.append(f"  [bold]Environment:[/] {len(t.env)} variables defined")
        elif isinstance(t, (HttpTransport, SseTransport)):
            lines.append(f"  [bold]Type:[/] {t.kind.upper()} (remote)")
            lines.append(f"  [bold]URL:[/] [green]{t.url}[/]")
            if t.headers:
                lines.append(f"  [bold]Headers:[/] {', '.join(t.headers.keys())}")
        elif e.error:
            lines.append(f"  [bold red]Invalid Transport:[/] {escape(e.error)}")

        lines.append("\n[bold cyan]Catalog & Health Status[/]")
        if self.catalog is not None:
            c = self.catalog
            stat_style = "green" if c.status == "ok" else "red"
            lines.append(f"  [bold]Status:[/] [{stat_style}]{c.status.upper()}[/]")
            lines.append(f"  [bold]Scanned At:[/] {c.scanned_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            lines.append(f"  [bold]Tools Exposed:[/] {len(c.tools)}")
            lines.append(f"  [bold]Resources Exposed:[/] {len(c.resources)}")
            lines.append(f"  [bold]Prompts Exposed:[/] {len(c.prompts)}")
            if c.error:
                lines.append(f"  [bold red]Error:[/] {escape(c.error)}")
            if c.stderr_tail:
                lines.append("\n[bold yellow]Stderr Log Tail:[/]")
                lines.append(escape(c.stderr_tail.strip()))
        else:
            lines.append("  [dim]Not scanned yet. Press 'c' or the Connect button to inspect.[/]")

        self._overview_text.update("\n".join(lines))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-connect-scan" and self.entry is not None:
            self.post_message(ConnectRequested(self.entry))

    def switch_tab(self, tab_id: str) -> None:
        """Switch active tab."""
        self.query_one(TabbedContent).active = tab_id

    def prev_tab(self) -> None:
        """Cycle to previous tab."""
        tc = self.query_one(TabbedContent)
        active = tc.active or self.TABS[0]
        if active in self.TABS:
            idx = (self.TABS.index(active) - 1) % len(self.TABS)
            tc.active = self.TABS[idx]

    def next_tab(self) -> None:
        """Cycle to next tab."""
        tc = self.query_one(TabbedContent)
        active = tc.active or self.TABS[0]
        if active in self.TABS:
            idx = (self.TABS.index(active) + 1) % len(self.TABS)
            tc.active = self.TABS[idx]

    def toggle_maximize(self) -> None:
        """Toggle maximize/restore on currently active tab."""
        tc = self.query_one(TabbedContent)
        if tc.active == "tab-tools":
            self.tool_runner.action_toggle_maximize()
