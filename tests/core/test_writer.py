"""Writer: data-loss guarantees. Every test writes into a temp dir with fake data."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp_browser_core.errors import CommentsWouldBeLost, FileChanged, NotFound
from mcp_browser_core.formats import load, plain
from mcp_browser_core.paths import Paths
from mcp_browser_core.writer import KEEP_BACKUPS, write_entry

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes and symlinks")


def _add(name: str = "new") -> Any:
    def mutate(doc: Any) -> None:
        doc["mcpServers"][name] = {"command": "x"}

    return mutate


def _write(path: Path, paths: Paths, mutate: Any, fmt: Any = "json", **kw: Any) -> str | None:
    opts: dict[str, Any] = {"allow_comment_loss": False, "create": False} | kw
    return write_entry(str(path), fmt, mutate, paths=paths, **opts)


def test_unknown_keys_order_indent_and_newline_survive(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.json"
    src = "\n".join(
        [
            "{",
            '    "zeta": [1, {"a": null}],',
            '    "mcpServers": {',
            '        "old": {"command": "o", "weird": 1.5}',
            "    },",
            '    "alpha": "é"',
            "}",
        ]
    )
    f.write_text(src, encoding="utf-8")
    _write(f, paths, _add())
    out = f.read_text(encoding="utf-8")
    assert not out.endswith("\n")
    assert '\n    "zeta"' in out and '\n        "old"' in out
    doc = json.loads(out)
    assert list(doc) == ["zeta", "mcpServers", "alpha"]
    assert doc["alpha"] == "é" and doc["zeta"] == [1, {"a": None}]
    assert list(doc["mcpServers"]) == ["old", "new"]
    assert doc["mcpServers"]["old"] == {"command": "o", "weird": 1.5}


def test_trailing_newline_and_tabs_and_crlf_preserved(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.json"
    f.write_bytes(b'{\r\n\t"mcpServers": {}\r\n}\r\n')
    _write(f, paths, _add())
    raw = f.read_bytes()
    assert raw.endswith(b"}\r\n") and b'\r\n\t"mcpServers"' in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")


@posix_only
def test_symlinked_config_stays_a_symlink(tmp_path: Path, paths: Paths) -> None:
    real = tmp_path / "dotfiles" / "real.json"
    real.parent.mkdir()
    real.write_text('{"mcpServers": {}}\n')
    link = tmp_path / "home.json"
    link.symlink_to(real)
    _write(link, paths, _add())
    assert link.is_symlink() and link.resolve() == real.resolve()
    assert "new" in json.loads(real.read_text())["mcpServers"]


@posix_only
def test_file_mode_is_preserved(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.json"
    f.write_text('{"mcpServers": {}}\n')
    f.chmod(0o640)
    _write(f, paths, _add())
    assert stat.S_IMODE(f.stat().st_mode) == 0o640


def test_backup_holds_original_bytes_and_is_private(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.json"
    f.write_bytes(b'{"mcpServers":{}}')
    backup = _write(f, paths, _add())
    assert backup is not None
    assert Path(backup).read_bytes() == b'{"mcpServers":{}}'
    assert Path(backup).parent == paths.backups_dir
    if sys.platform != "win32":
        assert stat.S_IMODE(Path(backup).stat().st_mode) == 0o600
        assert stat.S_IMODE(paths.backups_dir.stat().st_mode) == 0o700


def test_backups_are_pruned_per_source(tmp_path: Path, paths: Paths) -> None:
    f, other = tmp_path / "c.json", tmp_path / "d.json"
    for p in (f, other):
        p.write_text('{"mcpServers": {}}\n')
    _write(other, paths, _add("o"))
    for i in range(KEEP_BACKUPS + 5):
        _write(f, paths, _add(f"n{i}"))
    mine = [p for p in paths.backups_dir.iterdir() if "c.json" in p.name]
    assert len(mine) == KEEP_BACKUPS
    assert len([p for p in paths.backups_dir.iterdir() if "d.json" in p.name]) == 1


def test_new_file_gets_no_backup_and_private_mode(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "sub" / "new.json"

    def mutate(doc: Any) -> None:
        doc["mcpServers"] = {"a": {"command": "x"}}

    assert _write(f, paths, mutate, create=True) is None
    assert json.loads(f.read_text()) == {"mcpServers": {"a": {"command": "x"}}}
    assert f.read_text().endswith("\n")
    assert not paths.backups_dir.exists() or not list(paths.backups_dir.iterdir())
    if sys.platform != "win32":
        assert stat.S_IMODE(f.stat().st_mode) == 0o600


def test_missing_file_without_create_is_not_found(tmp_path: Path, paths: Paths) -> None:
    with pytest.raises(NotFound):
        _write(tmp_path / "nope.json", paths, _add())
    assert not (tmp_path / "nope.json").exists()


def test_concurrent_change_is_detected_and_retried(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.json"
    f.write_text('{"mcpServers": {}}\n')
    calls = {"n": 0}

    def mutate(doc: Any) -> None:
        calls["n"] += 1
        if calls["n"] == 1:  # another process edits the file while we are working
            f.write_text('{"mcpServers": {"theirs": {"command": "t"}}}\n')
        doc["mcpServers"]["mine"] = {"command": "m"}

    _write(f, paths, mutate)
    assert calls["n"] == 2
    assert list(json.loads(f.read_text())["mcpServers"]) == ["theirs", "mine"]


def test_persistent_concurrent_change_raises_and_keeps_their_file(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.json"
    f.write_text('{"mcpServers": {}}\n')
    counter = {"n": 0}

    def mutate(doc: Any) -> None:
        counter["n"] += 1
        f.write_text(json.dumps({"mcpServers": {f"theirs{counter['n']}": {}}}) + "\n")

    with pytest.raises(FileChanged):
        _write(f, paths, mutate)
    assert "theirs3" in f.read_text()
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_mutate_error_leaves_file_untouched(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.json"
    f.write_text('{"mcpServers": {}}\n')

    def boom(doc: Any) -> None:
        doc["x"] = 1
        raise RuntimeError("no")

    with pytest.raises(RuntimeError):
        _write(f, paths, boom)
    assert f.read_text() == '{"mcpServers": {}}\n'
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_toml_comments_survive(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "config.toml"
    f.write_text('# top\nmodel = "m"  # why\n\n[mcp_servers.a]\n# keep me\ncommand = "x"\n')

    def mutate(doc: Any) -> None:
        doc["mcp_servers"]["b"] = {"command": "y", "args": ["1"]}
        doc["mcp_servers"]["a"]["command"] = "z"

    _write(f, paths, mutate, fmt="toml")
    out = f.read_text()
    assert "# top" in out and "# why" in out and "# keep me" in out
    assert plain(load(out, "toml")) == {
        "model": "m",
        "mcp_servers": {"a": {"command": "z"}, "b": {"command": "y", "args": ["1"]}},
    }


COMMENTED = '{\n  // my note\n  "mcpServers": {}\n}\n'


def test_jsonc_comments_refuse_then_override(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.jsonc"
    f.write_text(COMMENTED)
    with pytest.raises(CommentsWouldBeLost) as info:
        _write(f, paths, _add(), fmt="jsonc")
    assert info.value.detail["can_override"] is True
    assert f.read_text() == COMMENTED and not paths.backups_dir.exists()
    backup = _write(f, paths, _add(), fmt="jsonc", allow_comment_loss=True)
    assert backup and Path(backup).read_text() == COMMENTED
    assert "//" not in f.read_text() and "new" in json.loads(f.read_text())["mcpServers"]


def test_non_dedicated_file_cannot_be_overridden(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "settings.json"
    f.write_text(COMMENTED)
    with pytest.raises(CommentsWouldBeLost) as info:
        _write(f, paths, _add(), fmt="jsonc", allow_comment_loss=True, dedicated_file=False)
    assert info.value.detail["can_override"] is False
    assert f.read_text() == COMMENTED


def test_urls_in_strings_are_not_comments(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.jsonc"
    f.write_text('{"mcpServers": {"u": {"url": "https://h.test/a//b", "q": "/* x */"}}}\n')
    _write(f, paths, _add(), fmt="jsonc", dedicated_file=False)
    doc = json.loads(f.read_text())
    assert doc["mcpServers"]["u"] == {"url": "https://h.test/a//b", "q": "/* x */"}


def test_jsonc_trailing_commas_do_not_count_as_comments(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.jsonc"
    f.write_text('{"mcpServers": {},}\n')
    _write(f, paths, _add(), fmt="jsonc")
    assert "new" in json.loads(f.read_text())["mcpServers"]


def test_symlink_realpath_used_for_lock_and_backup(tmp_path: Path, paths: Paths) -> None:
    real = tmp_path / "real.json"
    real.write_text('{"mcpServers": {}}\n')
    backup = _write(real, paths, _add())
    assert backup and os.path.basename(str(real)) in backup
