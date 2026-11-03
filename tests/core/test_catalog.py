from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import anyio
import pytest
from mcp_browser_core.catalog import Catalog
from mcp_browser_core.catalog_models import CatalogEntry
from mcp_browser_core.connect import ConnectOptions
from mcp_browser_core.models import ServerEntry, StdioTransport, fingerprint
from mcp_browser_core.paths import Paths

FIXTURE = str(Path(__file__).parents[1] / "fixtures" / "fixture_server.py")


def cat_entry(entry_id: str, fp: str = "fp") -> CatalogEntry:
    return CatalogEntry(entry_id=entry_id, fingerprint=fp, scanned_at=datetime.now(UTC), status="ok")


def server(name: str, command: str, args: list[str]) -> ServerEntry:
    t = StdioTransport(command=command, args=args)
    return ServerEntry(id=name, name=name, client_id="x", scope="user", config_path="/x", transport=t)


def test_put_get_drop_and_reload(tmp_path: Path) -> None:
    path = tmp_path / "state" / "catalog.json"
    cat = Catalog(path)
    cat.load()
    assert cat.all() == []
    cat.put(cat_entry("a", "f1"))
    cat.put(cat_entry("b"))
    assert cat.get("a", "f1") is not None and cat.get("a", "other") is None
    fresh = Catalog(path)
    fresh.load()
    assert sorted(e.entry_id for e in fresh.all()) == ["a", "b"]
    fresh.drop("a")
    fresh.drop("missing")
    again = Catalog(path)
    again.load()
    assert [e.entry_id for e in again.all()] == ["b"]
    assert [p.name for p in path.parent.iterdir()] == ["catalog.json"]  # no temp files left behind


def test_damaged_file_loads_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    for text in ("{broken", "[]", json.dumps({"entries": {"a": {"nope": 1}}})):
        path.write_text(text)
        cat = Catalog(path)
        cat.load()
        assert cat.all() == []


@pytest.mark.anyio
async def test_scan_records_success_and_errors_without_raising(paths: Paths, tmp_path: Path) -> None:
    good = server("good", sys.executable, [FIXTURE])
    bad = server("bad", "/no/such/cmd", [])
    nothing = ServerEntry(id="ws", name="ws", client_id="x", scope="user", config_path="/x", error="no ws")
    unresolved = server("unres", "${NOT_SET_ANYWHERE}", [])
    cat = Catalog(tmp_path / "catalog.json")
    opts = ConnectOptions(connect_timeout=60, call_timeout=60)
    found = await cat.scan([good, bad, nothing, unresolved], paths, opts, limiter=anyio.CapacityLimiter(8))
    by_id = {e.entry_id: e for e in found}
    assert [e.entry_id for e in found] == ["good", "bad", "ws", "unres"]
    assert by_id["good"].status == "ok" and len(by_id["good"].tools) == 4
    assert by_id["good"].fingerprint == fingerprint(good.transport)
    assert by_id["good"].prompts[0].name == "greet" and by_id["good"].resources[0].uri == "res://a"
    assert by_id["bad"].status == "error" and "command not found" in (by_id["bad"].error or "")
    assert by_id["ws"].error == "no ws"
    assert "NOT_SET_ANYWHERE" in (by_id["unres"].error or "")
    reloaded = Catalog(tmp_path / "catalog.json")
    reloaded.load()
    assert len(reloaded.all()) == 4
