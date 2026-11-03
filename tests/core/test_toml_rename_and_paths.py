"""TOML rename keeps order and comments; home paths with glob characters resolve literally."""

from __future__ import annotations

import sys
from pathlib import Path

from mcp_browser_core.discovery import active_user_file, discover
from mcp_browser_core.formats import load, plain
from mcp_browser_core.mutate import rename
from mcp_browser_core.paths import Paths
from mcp_browser_core.specs import REGISTRY
from mcp_browser_core.specs.base import PathRule

TOML = """# top
model = "m"  # why

# about a
[mcp_servers.a]
# inside a
command = "x"  # tail

[mcp_servers.a.env]
K = "v"  # k comment

# about b
[mcp_servers.b]
# inside b
command = "y"

[profiles.fast]
x = 1
"""


def test_toml_rename_keeps_position_and_comments(paths: Paths) -> None:
    f = active_user_file(paths, REGISTRY["codex"])
    assert f is not None
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(TOML)
    eid = next(e.id for e in discover(paths).entries if e.name == "a" and e.client_id == "codex")
    rename(eid, "renamed one", paths=paths)
    out = f.read_text()
    for kept in (
        "# top",
        "# why",
        "# about a",
        "# inside a",
        "# tail",
        "# k comment",
        "# about b",
        "# inside b",
    ):
        assert kept in out
    assert (
        out.index('[mcp_servers."renamed one"]') < out.index("[mcp_servers.b]") < out.index("[profiles.fast]")
    )
    assert 'mcp_servers."renamed one".env' in out and "mcp_servers.a" not in out
    doc = plain(load(out, "toml"))
    assert list(doc["mcp_servers"]) == ["renamed one", "b"]
    assert doc["mcp_servers"]["renamed one"] == {"command": "x", "env": {"K": "v"}}


def test_toml_rename_last_table_stays_last(paths: Paths) -> None:
    f = active_user_file(paths, REGISTRY["codex"])
    assert f is not None
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(TOML)
    eid = next(e.id for e in discover(paths).entries if e.name == "b" and e.client_id == "codex")
    rename(eid, "c", paths=paths)
    out = f.read_text()
    assert out.index("[mcp_servers.a]") < out.index("[mcp_servers.c]") < out.index("[profiles.fast]")
    assert "# about b" in out and "# inside b" in out


def test_glob_characters_in_home_are_literal(tmp_path: Path) -> None:
    home_name = "ho[me]" if sys.platform == "win32" else "ho[me]?*"
    home = tmp_path / home_name
    manifest = home / "Library/Application Support/Claude/Claude Extensions/ext1/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}")
    decoy = tmp_path / "hoe" / "Library/Application Support/Claude/Claude Extensions/evil/manifest.json"
    decoy.parent.mkdir(parents=True)
    decoy.write_text("{}")
    p = Paths({"HOME": str(home)}, "darwin", tmp_path)
    rule = PathRule("{claude_desktop_dir}/Claude Extensions/*/manifest.json")
    assert p.candidates(rule) == [manifest]
    star = PathRule("{home}/*/m.json")
    (home / "d").mkdir()
    (home / "d" / "m.json").write_text("{}")
    assert p.candidates(star) == [home / "d" / "m.json"]
