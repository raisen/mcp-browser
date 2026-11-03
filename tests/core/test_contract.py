"""Wave 0 contract checks: models, errors and Paths behave as PLAN.md section 2-3 says."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mcp_browser_core import StdioTransport, fingerprint, make_entry_id
from mcp_browser_core.errors import CommentsWouldBeLost, NotFound, UnresolvedPlaceholders
from mcp_browser_core.models import HttpTransport, Platform
from mcp_browser_core.paths import Paths
from mcp_browser_core.specs.base import PathRule


def test_ids_and_fingerprint_are_stable() -> None:
    assert make_entry_id("cursor", "user", "/x/mcp.json", "a") == make_entry_id(
        "cursor", "user", "/x/mcp.json", "a"
    )
    assert make_entry_id("cursor", "user", "/x/mcp.json", "a") != make_entry_id(
        "cursor", "user", "/x/mcp.json", "b"
    )
    assert fingerprint(None) == fingerprint(None)
    a, b = StdioTransport(command="x"), HttpTransport(url="http://h/mcp")
    assert fingerprint(a) != fingerprint(b)
    assert len(fingerprint(a)) == 16


def test_error_bodies() -> None:
    assert NotFound("nope").to_body() == {"error": "not_found", "message": "nope", "detail": {}}
    assert NotFound.status == 404
    body = CommentsWouldBeLost("c", can_override=False).to_body()
    assert body["detail"] == {"can_override": False}
    assert UnresolvedPlaceholders("p", placeholders=["A"]).detail["placeholders"] == ["A"]


def test_isolated_paths_stay_under_tmp(paths: Paths, tmp_path: Path) -> None:
    assert tmp_path in paths.home.parents
    assert tmp_path in paths.state_dir.parents
    assert paths.token_file.parent == paths.state_dir


def test_platform_tables(paths_for: Callable[[Platform], Paths]) -> None:
    mac, win, lin = paths_for("darwin"), paths_for("win32"), paths_for("linux")
    assert mac.claude_desktop_dir() == mac.home / "Library" / "Application Support" / "Claude"
    assert win.claude_desktop_dir() == win.appdata / "Claude"  # no Store package present
    assert lin.claude_desktop_dir() == lin.xdg_config / "Claude"
    assert mac.code_user_dir().name == win.code_user_dir().name == lin.code_user_dir().name == "User"
    assert win.state_dir.parent == win.home or win.state_dir.name == "state"  # MCP_BROWSER_STATE_DIR wins


def test_candidates_and_globs(paths_for: Callable[[Platform], Paths]) -> None:
    win = paths_for("win32")
    package = win.localappdata / "Packages" / "Claude_abc" / "LocalCache" / "Roaming" / "Claude"
    package.mkdir(parents=True)
    assert win.claude_desktop_dir() == package
    rule = PathRule("{claude_desktop_dir}/claude_desktop_config.json")
    assert win.candidates(rule) == [package / "claude_desktop_config.json"]
    assert win.candidates(PathRule("{home}/x", platforms=("darwin",))) == []
    ext = package / "Claude Extensions" / "e1"
    ext.mkdir(parents=True)
    (ext / "manifest.json").write_text("{}")
    glob_rule = PathRule("{claude_desktop_dir}/Claude Extensions/*/manifest.json")
    assert win.candidates(glob_rule) == [ext / "manifest.json"]


def test_claude_json_dir_follows_config_dir(paths_for: Callable[[Platform], Paths]) -> None:
    p = paths_for("linux")
    assert p.claude_json_dir() == p.home
    custom = Paths({**p.environ, "CLAUDE_CONFIG_DIR": str(p.home / "cc")}, "linux", p.cwd)
    assert custom.claude_json_dir() == custom.claude_dir() == p.home / "cc"
