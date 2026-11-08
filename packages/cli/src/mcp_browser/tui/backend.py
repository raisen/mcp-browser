"""Async backend bridge connecting the TUI directly to mcp-browser-core APIs."""

from __future__ import annotations

from typing import Any

import anyio
from mcp_browser_core.catalog import Catalog, scan_one
from mcp_browser_core.catalog_models import CallResult, CatalogEntry
from mcp_browser_core.connect import ConnectOptions, session
from mcp_browser_core.discovery import discover
from mcp_browser_core.models import DiscoveryResult, ServerEntry, fingerprint
from mcp_browser_core.paths import Paths
from mcp_browser_core.trust import confirmation_detail


class DirectCoreBackend:
    """Standalone direct core engine for discovery, catalog cache, and live MCP execution."""

    def __init__(
        self,
        paths: Paths,
        connect_timeout: float = 15.0,
        call_timeout: float = 60.0,
        max_concurrency: int = 5,
    ) -> None:
        self.paths = paths
        self.catalog = Catalog(paths.catalog_file)
        self.connect_opts = ConnectOptions(connect_timeout=connect_timeout, call_timeout=call_timeout)
        self.limiter = anyio.CapacityLimiter(max_concurrency)
        self.trusted_entries: set[str] = set()
        self.catalog.load()

    def discover_servers(self) -> DiscoveryResult:
        """Discover server entries across client configs."""
        return discover(self.paths)

    def load_catalog(self) -> None:
        """Reload catalog cache from disk."""
        self.catalog.load()

    def get_cached_catalog(self, entry: ServerEntry) -> CatalogEntry | None:
        """Retrieve catalog entry from cache if the fingerprint matches."""
        fp = fingerprint(entry.transport)
        return self.catalog.get(entry.id, fp)

    def all_cached_catalog(self) -> dict[str, CatalogEntry]:
        """Map of entry_id -> CatalogEntry for all cached items."""
        return {e.entry_id: e for e in self.catalog.all()}

    async def scan_server(self, entry: ServerEntry) -> CatalogEntry:
        """Connect to and inspect an MCP server, updating the catalog cache."""
        result = await scan_one(entry, self.paths, self.connect_opts, self.limiter, oauth=None)
        self.catalog.put(result)
        return result

    async def call_tool(self, entry: ServerEntry, name: str, args: dict[str, Any]) -> CallResult:
        """Call a specific tool on a connected server."""
        async with session(entry, self.paths, self.connect_opts, oauth=None, limiter=self.limiter) as s:
            return await s.call_tool(name, args, self.connect_opts.call_timeout)

    async def read_resource(self, entry: ServerEntry, uri: str) -> list[dict[str, Any]]:
        """Read a resource URI from a connected server."""
        async with session(entry, self.paths, self.connect_opts, oauth=None, limiter=self.limiter) as s:
            return await s.read_resource(uri)

    async def get_prompt(self, entry: ServerEntry, name: str, args: dict[str, str]) -> dict[str, Any]:
        """Fetch a prompt template with rendered arguments from a connected server."""
        async with session(entry, self.paths, self.connect_opts, oauth=None, limiter=self.limiter) as s:
            return await s.get_prompt(name, args)

    def is_trusted(self, entry: ServerEntry) -> bool:
        """Check if an untrusted server has been approved by the user."""
        return not entry.untrusted or entry.id in self.trusted_entries

    def mark_trusted(self, entry_id: str) -> None:
        """Mark an untrusted server as trusted for the lifetime of this session."""
        self.trusted_entries.add(entry_id)

    def confirmation_detail(self, entry: ServerEntry) -> dict[str, Any]:
        """Extract security confirmation metadata for an untrusted entry."""
        return confirmation_detail(entry)
