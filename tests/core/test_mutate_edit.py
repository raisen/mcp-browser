"""update / delete / rename end to end against temp configs (fake servers and tokens only)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from mcp_browser_core.catalog import Catalog
from mcp_browser_core.discovery import active_user_file, discover
from mcp_browser_core.errors import Conflict, InvalidArguments, NotFound, ReadOnly, UnsupportedTransport
from mcp_browser_core.formats import load, plain
from mcp_browser_core.models import EntryPatch, HttpTransport, NewEntry, SseTransport, StdioTransport, Target
from mcp_browser_core.mutate import add, delete, rename, update
from mcp_browser_core.paths import Paths
from mcp_browser_core.secrets import MASK
from mcp_browser_core.specs import REGISTRY

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "configs"
NEW = NewEntry(name="fresh", transport=StdioTransport(command="npx", args=["-y", "@example/fresh"]))
WIN_KEY = "C:\\Users\\demo\\work"


class SpyCatalog(Catalog):
    def __init__(self) -> None:
        super().__init__(Path("unused"))
        self.dropped: list[str] = []

    def drop(self, entry_id: str) -> None:
        self.dropped.append(entry_id)


def place(paths: Paths, spec_id: str, fixture: str) -> Path:
    dest = active_user_file(paths, REGISTRY[spec_id])
    assert dest is not None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / fixture, dest)
    return dest


def find(paths: Paths, client: str, name: str, scope: str = "user", project: str | None = None) -> str:
    for e in discover(paths).entries:
        if (e.client_id, e.name, e.scope, e.project) == (client, name, scope, project):
            return e.id
    raise AssertionError(f"{client}/{name} not found")


def test_local_scope_update_and_delete_by_verbatim_key(paths: Paths) -> None:
    f = place(paths, "claude-code", "claude-code.json")
    before = json.loads(f.read_text())
    eid = find(paths, "claude-code", "win-local", "local", WIN_KEY)
    rep = update(
        eid, EntryPatch(transport=StdioTransport(command="python3", args=["-m", "srv2"])), paths=paths
    )
    assert rep.entry.project == WIN_KEY
    mid = json.loads(f.read_text())
    assert mid["projects"][WIN_KEY]["mcpServers"]["win-local"] == {
        "command": "python3",
        "args": ["-m", "srv2"],
    }
    assert mid["projects"][WIN_KEY]["hasTrustDialogAccepted"] is True
    assert mid["projects"]["/work/demo-app"] == before["projects"]["/work/demo-app"]
    delete(find(paths, "claude-code", "win-local", "local", WIN_KEY), paths=paths)
    end = json.loads(f.read_text())
    assert end["projects"][WIN_KEY] == {"mcpServers": {}, "hasTrustDialogAccepted": True}
    assert end["mcpServers"] == before["mcpServers"]


def test_update_keeps_extra_and_position_and_drops_catalog(paths: Paths) -> None:
    f = place(paths, "gemini", "gemini.json")
    spy = SpyCatalog()
    eid = find(paths, "gemini", "g-stdio")
    rep = update(
        eid, EntryPatch(transport=StdioTransport(command="node", args=["b.js"])), paths=paths, catalog=spy
    )
    assert spy.dropped == [eid] and rep.backup_path
    doc = json.loads(f.read_text())
    assert list(doc["mcpServers"]) == ["g-stdio", "g-http", "g-sse"]
    assert doc["mcpServers"]["g-stdio"] == {
        "command": "node",
        "args": ["b.js"],
        "trust": True,
        "timeout": 5000,
    }
    assert doc["mcpServers"]["g-sse"] == {"url": "https://gem.example.test/sse", "includeTools": ["a"]}


def test_update_switches_transport_kind(paths: Paths) -> None:
    place(paths, "claude-code", "claude-code.json")
    eid = find(paths, "claude-code", "alpha-stdio")
    update(eid, EntryPatch(transport=HttpTransport(url="https://n.test/m")), paths=paths)
    entry = next(e for e in discover(paths).entries if e.name == "alpha-stdio")
    assert entry.transport == HttpTransport(url="https://n.test/m")
    assert entry.extra == {}


def test_rename_preserves_position_in_json(paths: Paths) -> None:
    f = place(paths, "gemini", "gemini.json")
    rep = rename(find(paths, "gemini", "g-http"), "renamed", paths=paths)
    assert rep.entry.name == "renamed" and rep.entry.id == find(paths, "gemini", "renamed")
    assert list(json.loads(f.read_text())["mcpServers"]) == ["g-stdio", "renamed", "g-sse"]
    with pytest.raises(Conflict):
        rename(find(paths, "gemini", "renamed"), "g-sse", paths=paths)
    with pytest.raises(InvalidArguments):
        rename(find(paths, "gemini", "renamed"), "  ", paths=paths)


def test_toml_update_rename_delete_keep_comments(paths: Paths) -> None:
    f = place(paths, "codex", "codex.toml")
    update(find(paths, "codex", "docs"), EntryPatch(extra={"startup_timeout_sec": 99}), paths=paths)
    out = f.read_text()
    assert "# Codex demo config" in out and "# main docs server" in out and "[profiles.fast]" in out
    assert plain(load(out, "toml"))["mcp_servers"]["docs"]["startup_timeout_sec"] == 99
    assert 'DOCS_TOKEN = "fake-token-444"' in out
    rename(find(paths, "codex", "remote"), "remote2", paths=paths)
    assert "remote2" in plain(load(f.read_text(), "toml"))["mcp_servers"]
    delete(find(paths, "codex", "remote2"), paths=paths)
    final = f.read_text()
    assert "# Codex demo config" in final
    assert list(plain(load(final, "toml"))["mcp_servers"]) == ["docs"]


def test_delete_returns_entry_and_missing_is_not_found(paths: Paths) -> None:
    f = place(paths, "windsurf", "windsurf.json")
    eid = find(paths, "windsurf", "ws-http")
    rep = delete(eid, paths=paths)
    assert rep.entry.name == "ws-http" and rep.backup_path
    assert list(json.loads(f.read_text())["mcpServers"]) == ["ws-stdio"]
    with pytest.raises(NotFound):
        delete(eid, paths=paths)


def test_update_rejects_masked_values_and_bad_capabilities(paths: Paths) -> None:
    place(paths, "claude-desktop", "claude-desktop.json")
    eid = find(paths, "claude-desktop", "files")
    with pytest.raises(InvalidArguments):
        update(eid, EntryPatch(extra={"k": MASK}), paths=paths)
    with pytest.raises(UnsupportedTransport):
        update(eid, EntryPatch(transport=SseTransport(url="https://x.test")), paths=paths)


def test_readonly_entries_cannot_be_changed(paths: Paths) -> None:
    ext = paths.claude_desktop_dir() / "Claude Extensions" / "demo-ext" / "manifest.json"
    ext.parent.mkdir(parents=True)
    shutil.copy(FIXTURES / "extension-manifest.json", ext)
    eid = find(paths, "claude-desktop-ext", "demo-ext", "extension")
    before = ext.read_text()
    for call in (
        lambda: update(eid, EntryPatch(name="x"), paths=paths),
        lambda: delete(eid, paths=paths),
        lambda: rename(eid, "y", paths=paths),
    ):
        with pytest.raises(ReadOnly):
            call()
    assert ext.read_text() == before


def test_names_needing_quotes_in_toml(paths: Paths) -> None:
    place(paths, "codex", "codex.toml")
    new = NewEntry(name="my.srv name", transport=StdioTransport(command="x"))
    (res,) = add(new, [Target(client_id="codex", scope="user")], paths=paths)
    assert res.error is None
    names = [e.name for e in discover(paths).entries if e.client_id == "codex"]
    assert "my.srv name" in names


def test_zed_add_into_comment_free_settings_keeps_other_keys(paths: Paths) -> None:
    f = place(paths, "zed", "zed.jsonc")
    add(NEW, [Target(client_id="zed", scope="user")], paths=paths)
    doc: dict[str, Any] = json.loads(f.read_text())
    assert doc["theme"] == "One Dark" and doc["buffer_font_size"] == 14
    assert doc["context_servers"]["fresh"] == {
        "source": "custom",
        "command": "npx",
        "args": ["-y", "@example/fresh"],
    }
