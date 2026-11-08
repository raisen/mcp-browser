"""Sidebar widget displaying searchable tree of MCP servers."""

from __future__ import annotations

from collections import defaultdict

from mcp_browser_core.catalog_models import CatalogEntry
from mcp_browser_core.models import ServerEntry
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Input, Tree
from textual.widgets.tree import TreeNode

from ..models import BADGE_STYLES, BADGE_SYMBOLS, ServerSelected, entry_status


class ServerListWidget(Widget):
    """Sidebar widget containing a filter input and a hierarchical tree of servers."""

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self.entries: list[ServerEntry] = []
        self.catalog_map: dict[str, CatalogEntry] = {}
        self.filter_query: str = ""
        self._tree: Tree[ServerEntry | None] = Tree("Servers", id="server-tree")
        self._tree.show_root = False

    def compose(self) -> ComposeResult:
        with Vertical(id="sidebar"):
            yield Input(placeholder="Search servers... [/]", id="server-search")
            yield self._tree

    @property
    def visible_entries(self) -> list[ServerEntry]:
        """All entries currently matching the filter query."""
        q = self.filter_query.strip().lower()
        if not q:
            return list(self.entries)
        return [
            e
            for e in self.entries
            if q in e.name.lower()
            or q in e.client_id.lower()
            or (e.project and q in e.project.lower())
            or (e.transport and q in str(e.transport).lower())
        ]

    def set_servers(self, entries: list[ServerEntry], catalog_map: dict[str, CatalogEntry]) -> None:
        """Update server list and cached catalog map, rebuilding the tree."""
        self.entries = list(entries)
        self.catalog_map = dict(catalog_map)
        self._rebuild_tree()

    def update_catalog(self, catalog_map: dict[str, CatalogEntry]) -> None:
        """Update catalog map and refresh node badges."""
        self.catalog_map = dict(catalog_map)
        self._rebuild_tree()

    def focus_search(self) -> None:
        """Focus the search input bar."""
        self.query_one("#server-search", Input).focus()

    def focus_tree(self) -> None:
        """Focus the server tree widget."""
        self._tree.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter tree whenever search text changes."""
        self.filter_query = event.value
        self._rebuild_tree()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        """Return focus to tree on enter."""
        self._tree.focus()

    def on_tree_node_selected(self, event: Tree.NodeSelected[ServerEntry | None]) -> None:
        """Emit selection event when an entry node is activated with Enter or click."""
        if event.node.data is not None:
            self.post_message(ServerSelected(event.node.data))

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[ServerEntry | None]) -> None:
        """Emit selection event when navigating tree items with arrow keys."""
        if event.node.data is not None:
            self.post_message(ServerSelected(event.node.data))

    def _format_node_label(self, entry: ServerEntry) -> Text:
        cat = self.catalog_map.get(entry.id)
        badge = entry_status(entry, cat)
        symbol = BADGE_SYMBOLS[badge]
        style = BADGE_STYLES[badge]
        label = Text()
        label.append(f"{symbol} ", style=style)
        label.append(entry.name)
        if entry.untrusted:
            label.append(" [untr]", style="yellow")
        return label

    def _rebuild_tree(self) -> None:
        self._tree.clear()
        matching = self.visible_entries

        # Group by client display or project
        groups: dict[str, list[ServerEntry]] = defaultdict(list)
        for entry in matching:
            if entry.scope == "project" and entry.project:
                grp = f"Project: {entry.project.rstrip('/').rpartition('/')[2] or entry.project}"
            else:
                grp = entry.client_id.replace("_", " ").title()
            groups[grp].append(entry)

        for group_name in sorted(groups.keys()):
            items = groups[group_name]
            group_node: TreeNode[ServerEntry | None] = self._tree.root.add(
                f"{group_name} ({len(items)})", expand=True
            )
            for item in sorted(items, key=lambda x: x.name):
                label = self._format_node_label(item)
                group_node.add_leaf(label, data=item)

        self._tree.root.expand_all()
