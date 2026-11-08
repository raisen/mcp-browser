"""Backend integration tests for DirectCoreBackend."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from mcp_browser.tui.backend import DirectCoreBackend
from mcp_browser_core.catalog_models import CatalogEntry
from mcp_browser_core.models import ServerEntry, StdioTransport
from mcp_browser_core.paths import Paths

FIXTURE_PATH = str(Path(__file__).resolve().parents[1] / "fixtures" / "fixture_server.py")


def make_fixture_entry(entry_id: str = "fx-1", untrusted: bool = False) -> ServerEntry:
    transport = StdioTransport(command=sys.executable, args=[FIXTURE_PATH])
    return ServerEntry(
        id=entry_id,
        name="fixture-server",
        client_id="claude-desktop",
        scope="user",
        config_path="/dummy/path.json",
        transport=transport,
        untrusted=untrusted,
    )


def test_backend_initialization_and_trust(paths: Paths) -> None:
    backend = DirectCoreBackend(paths, connect_timeout=5.0, call_timeout=10.0, max_concurrency=2)
    assert backend.paths == paths
    assert backend.connect_opts.connect_timeout == 5.0
    assert backend.connect_opts.call_timeout == 10.0

    trusted_entry = make_fixture_entry("t1", untrusted=False)
    untrusted_entry = make_fixture_entry("u1", untrusted=True)

    assert backend.is_trusted(trusted_entry) is True
    assert backend.is_trusted(untrusted_entry) is False

    backend.mark_trusted(untrusted_entry.id)
    assert backend.is_trusted(untrusted_entry) is True

    detail = backend.confirmation_detail(untrusted_entry)
    assert detail["kind"] == "stdio"
    assert detail["command"] == sys.executable


def test_backend_discover_servers(paths: Paths) -> None:
    import shutil

    from mcp_browser_core.discovery import active_user_file
    from mcp_browser_core.specs import REGISTRY

    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures" / "configs"
    dest = active_user_file(paths, REGISTRY["claude-desktop"])
    assert dest is not None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixtures_dir / "claude-desktop.json", dest)

    backend = DirectCoreBackend(paths)
    disc = backend.discover_servers()
    assert len(disc.entries) > 0
    assert any(e.client_id == "claude-desktop" for e in disc.entries)


def test_backend_catalog_cache(paths: Paths) -> None:
    backend = DirectCoreBackend(paths)
    entry = make_fixture_entry("cat-1")

    assert backend.get_cached_catalog(entry) is None
    assert backend.all_cached_catalog() == {}

    fake_cat = CatalogEntry(
        entry_id=entry.id,
        fingerprint="fp123",
        scanned_at=datetime.now(UTC),
        status="ok",
        tools=[],
        resources=[],
        prompts=[],
    )
    backend.catalog.put(fake_cat)
    backend.load_catalog()
    assert entry.id in backend.all_cached_catalog()


@pytest.mark.anyio
async def test_backend_scan_server(paths: Paths) -> None:
    backend = DirectCoreBackend(paths)
    entry = make_fixture_entry("scan-1")

    cat = await backend.scan_server(entry)
    assert cat.status == "ok"
    tool_names = {t.name for t in cat.tools}
    assert {"add", "echo", "fail", "slow"}.issubset(tool_names)
    resource_uris = {r.uri for r in cat.resources}
    assert "res://a" in resource_uris
    prompt_names = {p.name for p in cat.prompts}
    assert "greet" in prompt_names

    cached = backend.all_cached_catalog()
    assert entry.id in cached
    assert cached[entry.id].status == "ok"


@pytest.mark.anyio
async def test_backend_call_tool_success_and_fail(paths: Paths) -> None:
    backend = DirectCoreBackend(paths)
    entry = make_fixture_entry("call-1")

    res_add = await backend.call_tool(entry, "add", {"a": 40, "b": 2})
    assert not res_add.is_error
    assert res_add.structured == {"result": 42}
    assert res_add.duration_ms >= 0

    res_fail = await backend.call_tool(entry, "fail", {})
    assert res_fail.is_error


@pytest.mark.anyio
async def test_backend_read_resource_and_get_prompt(paths: Paths) -> None:
    backend = DirectCoreBackend(paths)
    entry = make_fixture_entry("res-prompt-1")

    res = await backend.read_resource(entry, "res://a")
    assert isinstance(res, list)
    assert any("resource a" in str(item.get("text", "")) for item in res)

    prompt = await backend.get_prompt(entry, "greet", {"name": "Alice"})
    assert isinstance(prompt, dict)
    assert "Alice" in str(prompt)
