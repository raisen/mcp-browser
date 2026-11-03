"""Discovery over all fixtures on three simulated platforms."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from mcp_browser_core.discovery import active_user_file, discover
from mcp_browser_core.models import DiscoveryResult, Platform, ServerEntry
from mcp_browser_core.paths import Paths
from mcp_browser_core.specs import REGISTRY

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "configs"
USER_FILES = {
    "claude-code": "claude-code.json",
    "claude-desktop": "claude-desktop.json",
    "codex": "codex.toml",
    "gemini": "gemini.json",
    "antigravity": "antigravity.json",
    "cursor": "cursor.json",
    "vscode": "vscode.jsonc",
    "windsurf": "windsurf.json",
    "zed": "zed.jsonc",
    "cline": "cline.json",
}


def place(paths: Paths, spec_id: str, fixture: str) -> Path:
    dest = active_user_file(paths, REGISTRY[spec_id])
    assert dest is not None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / fixture, dest)
    return dest


def install_all(paths: Paths) -> None:
    for spec_id, fixture in USER_FILES.items():
        place(paths, spec_id, fixture)
    root = paths.home / "plug" / "demo-plugin"
    root.mkdir(parents=True)
    shutil.copy(FIXTURES / "plugin-mcp.json", root / ".mcp.json")
    reg = paths.claude_dir() / "plugins" / "installed_plugins.json"
    reg.parent.mkdir(parents=True)
    reg.write_text((FIXTURES / "plugin-installed.json").read_text().replace("__ROOT__/", f"{root.parent}/"))
    ext = paths.claude_desktop_dir() / "Claude Extensions" / "demo-ext" / "manifest.json"
    ext.parent.mkdir(parents=True)
    shutil.copy(FIXTURES / "extension-manifest.json", ext)


def by_name(result: DiscoveryResult, client: str) -> dict[str, ServerEntry]:
    kinds = ("user", "plugin", "extension")
    return {e.name: e for e in result.entries if e.client_id == client and e.scope in kinds}


@pytest.mark.parametrize("platform", ["darwin", "win32", "linux"])
def test_all_twelve_specs_discover_fixtures(
    paths_for: Callable[[Platform], Paths], platform: Platform
) -> None:
    paths = paths_for(platform)
    install_all(paths)
    result = discover(paths)
    assert not result.warnings
    assert {c.id for c in result.clients} == set(REGISTRY)
    expected = {
        "claude-code": {"alpha-stdio", "beta-http", "gamma-sse", "delta-ws"},
        "claude-desktop": {"files", "off"},
        "codex": {"docs", "remote"},
        "gemini": {"g-stdio", "g-http", "g-sse"},
        "antigravity": {"ag-stdio", "ag-http"},
        "cursor": {"cur-stdio", "cur-http"},
        "vscode": {"v-stdio", "v-http", "v-sse"},
        "windsurf": {"ws-stdio", "ws-http"},
        "zed": {"z-stdio", "z-http", "z-legacy"},
        "cline": {"cl-stdio", "cl-http"},
        "claude-code-plugins": {"plug-srv"},
        "claude-desktop-ext": {"demo-ext"},
    }
    for client, names in expected.items():
        assert set(by_name(result, client)) == names, client
    infos = {c.id: c for c in result.clients}
    assert all(any(p.exists for p in infos[c].config_paths) for c in expected)


def test_kinds_and_flags(paths: Paths) -> None:
    install_all(paths)
    result = discover(paths)
    cc = by_name(result, "claude-code")
    assert cc["alpha-stdio"].transport is not None and cc["alpha-stdio"].transport.kind == "stdio"
    assert cc["gamma-sse"].transport is not None and cc["gamma-sse"].transport.kind == "sse"
    assert cc["gamma-sse"].extra == {"futureField": [1, 2]}
    assert cc["delta-ws"].transport is None and cc["delta-ws"].error
    assert not by_name(result, "claude-desktop")["off"].enabled
    assert not by_name(result, "codex")["remote"].enabled
    assert by_name(result, "zed")["z-legacy"].error
    assert not by_name(result, "zed")["z-http"].enabled


def test_placeholders_are_kept_verbatim(paths: Paths) -> None:
    install_all(paths)
    entry = by_name(discover(paths), "vscode")["v-stdio"]
    assert entry.transport is not None and entry.transport.kind == "stdio"
    assert entry.transport.env == {"K": "${input:tok}"}


def test_local_scope_entries_use_verbatim_project_keys(paths: Paths) -> None:
    install_all(paths)
    result = discover(paths)
    local = {e.name: e for e in result.entries if e.scope == "local"}
    assert set(local) == {"local-one", "win-local"}
    assert local["win-local"].project == "C:\\Users\\demo\\work"
    assert local["local-one"].project == "/work/demo-app"
    assert {"/work/demo-app", "C:\\Users\\demo\\work", "/work/other"} <= set(result.projects)
    assert str(paths.cwd) in result.projects
    assert len({e.id for e in result.entries}) == len(result.entries)


def test_same_name_in_two_projects_gets_distinct_ids(paths: Paths) -> None:
    f = place(paths, "claude-code", "claude-code.json")
    one = '{"mcpServers": {"s": {"command": "x"}}}'
    f.write_text(f'{{"projects": {{"/a": {one}, "/b": {one}}}}}')
    ids = [e.id for e in discover(paths).entries]
    assert len(ids) == 2 and len(set(ids)) == 2


def test_project_scope_files(paths: Paths) -> None:
    proj = paths.cwd / "proj"
    (proj / ".cursor").mkdir(parents=True)
    (proj / ".cursor" / "mcp.json").write_text('{"mcpServers": {"p-cur": {"command": "x"}}}')
    (proj / ".mcp.json").write_text('{"mcpServers": {"p-cc": {"url": "https://p.test", "type": "http"}}}')
    f = place(paths, "claude-code", "claude-code.json")
    f.write_text(f'{{"projects": {{"{proj}": {{}}}}}}')
    result = discover(paths)
    project_entries = {e.name: e for e in result.entries if e.scope == "project"}
    assert set(project_entries) == {"p-cur", "p-cc"}
    assert project_entries["p-cur"].project == str(proj)
    assert project_entries["p-cur"].client_id == "cursor"


def test_cwd_equal_to_home_does_not_duplicate_user_files(paths: Paths) -> None:
    place(paths, "gemini", "gemini.json")
    paths.cwd = paths.home
    result = discover(paths)
    assert len([e for e in result.entries if e.client_id == "gemini"]) == 3


def test_unreadable_file_becomes_warning_and_stays_listed(paths: Paths) -> None:
    bad = place(paths, "windsurf", "windsurf.json")
    bad.write_text("{ not json")
    place(paths, "gemini", "gemini.json")
    result = discover(paths)
    assert any(bad.name in w for w in result.warnings)
    assert by_name(result, "gemini")
    info = next(c for c in result.clients if c.id == "windsurf")
    assert any(p.path == str(bad) for p in info.config_paths)


def test_first_existing_candidate_wins(paths: Paths) -> None:
    first = paths.home / ".gemini" / "config" / "mcp_config.json"
    second = paths.home / ".gemini" / "antigravity" / "mcp_config.json"
    for p, name in ((first, "one"), (second, "two")):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"mcpServers": {name: {"command": "x"}}}))
    assert set(by_name(discover(paths), "antigravity")) == {"one"}
    first.unlink()
    assert set(by_name(discover(paths), "antigravity")) == {"two"}


def test_override_paths_add_files(paths: Paths) -> None:
    extra = paths.cwd / "elsewhere" / "cursor.json"
    extra.parent.mkdir()
    extra.write_text('{"mcpServers": {"moved": {"command": "x"}}}')
    paths.state_dir.mkdir(parents=True)
    paths.paths_file.write_text(json.dumps({"cursor": [str(extra)]}))
    assert "moved" in by_name(discover(paths), "cursor")


def test_readonly_entries(paths: Paths) -> None:
    install_all(paths)
    result = discover(paths)
    plug = by_name(result, "claude-code-plugins")["plug-srv"]
    assert plug.read_only and plug.read_only_reason and plug.scope == "plugin"
    assert plug.transport is not None and plug.transport.kind == "stdio"
    assert plug.transport.command.replace("\\", "/").endswith("/demo-plugin/bin/run")
    assert plug.error and "user_config" in plug.error
    ext = by_name(result, "claude-desktop-ext")["demo-ext"]
    assert ext.read_only and ext.scope == "extension"
    assert ext.transport is not None and ext.transport.kind == "stdio"
    assert ext.transport.args[0].replace("\\", "/").endswith("demo-ext/server/index.js")
    assert ext.error is None


def test_comment_flag_on_jsonc_files(paths: Paths) -> None:
    place(paths, "cursor", "cursor.jsonc")
    info = next(c for c in discover(paths).clients if c.id == "cursor")
    assert [p.has_comments for p in info.config_paths if p.exists] == [True]


def test_url_with_double_slash_is_not_a_comment(paths: Paths) -> None:
    place(paths, "vscode", "vscode.jsonc")
    info = next(c for c in discover(paths).clients if c.id == "vscode")
    assert [p.has_comments for p in info.config_paths if p.exists] == [False]
