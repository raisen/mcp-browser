"""add / update / delete / rename end to end against temp configs (fake servers and tokens only)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from mcp_browser_core.catalog import Catalog
from mcp_browser_core.discovery import active_user_file, discover
from mcp_browser_core.errors import (
    CommentsWouldBeLost,
    Conflict,
    InvalidArguments,
    NotFound,
    ReadOnly,
    UnsupportedTransport,
)
from mcp_browser_core.models import HttpTransport, NewEntry, StdioTransport, Target
from mcp_browser_core.mutate import add
from mcp_browser_core.paths import Paths
from mcp_browser_core.secrets import MASK
from mcp_browser_core.specs import REGISTRY

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "configs"
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


NEW = NewEntry(name="fresh", transport=StdioTransport(command="npx", args=["-y", "@example/fresh"]))


def test_add_to_existing_file_keeps_everything_else(paths: Paths) -> None:
    f = place(paths, "claude-code", "claude-code.json")
    src = f.read_text()
    before = json.loads(src)
    (res,) = add(NEW, [Target(client_id="claude-code", scope="user")], paths=paths)
    assert res.error is None and res.report is not None
    assert not res.report.created_file and res.report.backup_path
    after = json.loads(f.read_text())
    assert list(after) == list(before)
    assert after["projects"] == before["projects"]
    assert list(after["mcpServers"])[-1] == "fresh"
    assert after["mcpServers"]["fresh"] == {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@example/fresh"],
    }
    assert f.read_text().endswith("\n") == src.endswith("\n")


def test_add_creates_missing_file_without_backup(paths: Paths) -> None:
    target = Target(client_id="cursor", scope="user")
    (res,) = add(NEW, [target], paths=paths)
    assert res.report and res.report.created_file and res.report.backup_path is None
    assert json.loads(Path(res.report.path).read_text()) == {
        "mcpServers": {"fresh": {"type": "stdio", "command": "npx", "args": ["-y", "@example/fresh"]}}
    }
    assert res.report.entry.name == "fresh" and res.report.entry.id


def test_add_multiple_targets_formats(paths: Paths) -> None:
    place(paths, "codex", "codex.toml")
    targets = [Target(client_id=c, scope="user") for c in ("codex", "gemini", "vscode", "zed", "windsurf")]
    http = NewEntry(name="web", transport=HttpTransport(url="https://x.test/mcp", headers={"A": "fake"}))
    results = add(http, targets, paths=paths)
    assert [r.error for r in results] == [None] * 5
    found = {e.client_id: e for e in discover(paths).entries if e.name == "web"}
    assert set(found) == {"codex", "gemini", "vscode", "zed", "windsurf"}
    assert all(e.transport == http.transport for e in found.values())
    assert found["zed"].extra == {"source": "custom"}
    codex = active_user_file(paths, REGISTRY["codex"])
    assert codex and "# Codex demo config" in codex.read_text()


def test_preflight_failure_writes_nothing(paths: Paths) -> None:
    gem = place(paths, "gemini", "gemini.json")
    before = gem.read_text()
    http = NewEntry(name="web", transport=HttpTransport(url="https://x.test/mcp"))
    with pytest.raises(UnsupportedTransport):
        add(
            http,
            [Target(client_id="gemini", scope="user"), Target(client_id="claude-desktop", scope="user")],
            paths=paths,
        )
    assert gem.read_text() == before
    dup = NewEntry(name="g-stdio", transport=StdioTransport(command="x"))
    with pytest.raises(Conflict):
        add(
            dup,
            [Target(client_id="cursor", scope="user"), Target(client_id="gemini", scope="user")],
            paths=paths,
        )
    assert gem.read_text() == before
    cursor = active_user_file(paths, REGISTRY["cursor"])
    assert cursor and not cursor.exists()
    assert not paths.backups_dir.exists()


def test_preflight_comment_rule_and_override(paths: Paths) -> None:
    cur = place(paths, "cursor", "cursor.jsonc")
    zed = place(paths, "zed", "zed-comments.jsonc")
    targets = [Target(client_id="cursor", scope="user"), Target(client_id="zed", scope="user")]
    with pytest.raises(CommentsWouldBeLost) as info:
        add(NEW, targets, paths=paths, allow_comment_loss=True)
    assert info.value.detail["can_override"] is False
    assert "// my note" not in cur.read_text() and "// user comment" in cur.read_text()
    assert "// editor tweaks" in zed.read_text()
    with pytest.raises(CommentsWouldBeLost) as info2:
        add(NEW, targets[:1], paths=paths)
    assert info2.value.detail["can_override"] is True
    (res,) = add(NEW, targets[:1], paths=paths, allow_comment_loss=True)
    assert res.error is None and "//" not in cur.read_text().replace("https://cur.example.test/a//b", "")


def test_add_validation(paths: Paths) -> None:
    with pytest.raises(InvalidArguments):
        add(
            NewEntry(name=" ", transport=StdioTransport(command="x")),
            [Target(client_id="cursor", scope="user")],
            paths=paths,
        )
    masked = NewEntry(name="m", transport=StdioTransport(command="x", env={"K": MASK}))
    with pytest.raises(InvalidArguments):
        add(masked, [Target(client_id="cursor", scope="user")], paths=paths)
    with pytest.raises(NotFound):
        add(NEW, [Target(client_id="nope", scope="user")], paths=paths)
    with pytest.raises(ReadOnly):
        add(NEW, [Target(client_id="claude-code-plugins", scope="user")], paths=paths)
    with pytest.raises(InvalidArguments):
        add(NEW, [Target(client_id="windsurf", scope="project", project=str(paths.cwd))], paths=paths)
    with pytest.raises(InvalidArguments):
        add(
            NEW,
            [Target(client_id="cursor", scope="project", project=str(paths.cwd / "missing"))],
            paths=paths,
        )


def test_project_scope_add_creates_project_file(paths: Paths) -> None:
    proj = paths.cwd / "proj"
    proj.mkdir()
    (res,) = add(NEW, [Target(client_id="cursor", scope="project", project=str(proj))], paths=paths)
    assert res.report and Path(res.report.path) == proj / ".cursor" / "mcp.json"
    assert res.report.entry.scope == "project" and res.report.entry.project == str(proj)


def test_local_scope_touches_only_the_named_project(paths: Paths) -> None:
    f = place(paths, "claude-code", "claude-code.json")
    before = json.loads(f.read_text())
    for key in ("/work/other", WIN_KEY):
        (res,) = add(NEW, [Target(client_id="claude-code", scope="local", project=key)], paths=paths)
        assert res.error is None and res.report and res.report.entry.project == key
    after = json.loads(f.read_text())
    assert after["projects"]["/work/other"]["mcpServers"]["fresh"]["command"] == "npx"
    assert (
        "fresh" in after["projects"][WIN_KEY]["mcpServers"]
        and "win-local" in after["projects"][WIN_KEY]["mcpServers"]
    )
    assert after["projects"]["/work/demo-app"] == before["projects"]["/work/demo-app"]
    assert after["mcpServers"] == before["mcpServers"]
    assert list(after["projects"]) == ["/work/demo-app", WIN_KEY, "/work/other"]
    assert not any(
        k.lower().replace("/", "\\") == WIN_KEY.lower() and k != WIN_KEY for k in after["projects"]
    )


def test_local_scope_requires_existing_project_key(paths: Paths) -> None:
    f = place(paths, "claude-code", "claude-code.json")
    before = f.read_text()
    for key in ("/work/never-seen", "C:/Users/demo/work", None):
        with pytest.raises(InvalidArguments):
            add(NEW, [Target(client_id="claude-code", scope="local", project=key)], paths=paths)
    assert f.read_text() == before
