"""Writer data-safety: lost updates, backups, read-only files, odd content. Synthetic data only."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp_browser_core import backup as backup_mod
from mcp_browser_core.backup import KEEP_BACKUPS, prefix_for
from mcp_browser_core.errors import InvalidArguments, McpBrowserError, ReadOnly
from mcp_browser_core.formats import load, plain
from mcp_browser_core.paths import Paths
from mcp_browser_core.writer import write_entry

posix_only = pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="POSIX non-root")


def add_one(name: str = "new") -> Any:
    def mutate(doc: Any) -> None:
        doc["mcpServers"][name] = {"command": "x"}

    return mutate


def run(path: Path, paths: Paths, mutate: Any, fmt: Any = "json", **kw: Any) -> str | None:
    opts: dict[str, Any] = {"allow_comment_loss": False, "create": False} | kw
    return write_entry(str(path), fmt, mutate, paths=paths, **opts)


def test_write_during_backup_is_not_lost_and_backup_holds_replaced_bytes(
    tmp_path: Path, paths: Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "c.json"
    f.write_text('{"mcpServers": {}}\n')
    theirs = '{"mcpServers": {"theirs": {"command": "t"}}}\n'
    real = backup_mod.make_backup
    calls: list[int] = []

    def racing(p: Paths, target: Path, data: bytes) -> str:
        calls.append(1)
        out = real(p, target, data)
        if len(calls) == 1:  # a client saves while we are backing up
            f.write_text(theirs)
        return out

    monkeypatch.setattr("mcp_browser_core.writer.make_backup", racing)
    backup = run(f, paths, add_one())
    assert len(calls) == 2
    assert list(json.loads(f.read_text())["mcpServers"]) == ["theirs", "new"]
    assert backup is not None and Path(backup).read_text() == theirs
    assert len(list(paths.backups_dir.iterdir())) == 1  # the stale first backup was discarded


def test_same_size_rewrite_with_same_content_hash_check(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.json"
    f.write_text('{"mcpServers": {"a": {}}}')
    n = {"n": 0}

    def mutate(doc: Any) -> None:
        n["n"] += 1
        if n["n"] == 1:
            f.write_text('{"mcpServers": {"b": {}}}')  # same length, different bytes
        doc["mcpServers"]["z"] = {}

    run(f, paths, mutate)
    assert list(json.loads(f.read_text())["mcpServers"]) == ["b", "z"]


@posix_only
def test_read_only_file_is_refused_not_replaced(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.json"
    f.write_text('{"mcpServers": {}}\n')
    f.chmod(0o444)
    with pytest.raises(ReadOnly) as info:
        run(f, paths, add_one())
    assert info.value.code == "read_only"
    assert f.read_text() == '{"mcpServers": {}}\n' and f.stat().st_mode & 0o777 == 0o444


@posix_only
def test_unwritable_directory_is_a_permission_error(tmp_path: Path, paths: Paths) -> None:
    d = tmp_path / "ro"
    d.mkdir()
    f = d / "c.json"
    f.write_text('{"mcpServers": {}}\n')
    d.chmod(0o555)
    try:
        with pytest.raises(ReadOnly) as info:
            run(f, paths, add_one())
    finally:
        d.chmod(0o755)
    assert "changed while" not in info.value.message and info.value.detail["reason"] == "permission_denied"
    assert f.read_text() == '{"mcpServers": {}}\n'


def test_non_finite_numbers_are_rejected_cleanly(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.jsonc"
    src = '{"mcpServers": {"a": {"command": "x", "timeout": Infinity}}}\n'
    f.write_text(src)
    with pytest.raises(InvalidArguments, match="NaN or Infinity"):
        run(f, paths, add_one(), fmt="jsonc")
    assert f.read_text() == src
    g = tmp_path / "d.json"
    g.write_text('{"mcpServers": {}, "x": NaN}\n')
    with pytest.raises(InvalidArguments):
        run(g, paths, add_one())


def test_bom_is_preserved_for_json_and_toml(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.json"
    f.write_bytes(b'\xef\xbb\xbf{"mcpServers": {}}\n')
    run(f, paths, add_one())
    assert f.read_bytes().startswith(b"\xef\xbb\xbf{") and b"new" in f.read_bytes()
    t = tmp_path / "c.toml"
    t.write_bytes(b'\xef\xbb\xbf[mcp_servers.a]\ncommand = "x"\n')

    def mutate(doc: Any) -> None:
        doc["mcp_servers"]["b"] = {"command": "y"}

    run(t, paths, mutate, fmt="toml")
    assert t.read_bytes().startswith(b"\xef\xbb\xbf[mcp_servers.a]")
    assert plain(load(t.read_text(encoding="utf-8-sig"), "toml"))["mcp_servers"]["b"] == {"command": "y"}


def test_no_bom_added_and_non_ascii_text_untouched(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.json"
    f.write_text('{"mcpServers": {}, "nome": "João é"}\n', encoding="utf-8")
    run(f, paths, add_one())
    raw = f.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and "João é".encode() in raw


def test_lone_surrogate_round_trips_and_file_stays_editable(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "c.json"
    f.write_text(
        '{"mcpServers": {"a": {"command": "x", "note": "\\ud83d half", "ok": "\\ud83d\\ude00 é"}}}\n',
        encoding="utf-8",
    )
    run(f, paths, add_one("b"))
    run(f, paths, add_one("c"))
    text = f.read_text(encoding="utf-8")
    assert "\\ud83d half" in text and "😀 é" in text
    doc = json.loads(text)["mcpServers"]
    assert doc["a"]["note"] == "\ud83d half" and doc["a"]["ok"] == "😀 é" and "c" in doc


def test_backup_names_are_unique_per_path_and_bounded(tmp_path: Path, paths: Paths) -> None:
    one, two = tmp_path / "x" / "c.json", tmp_path / "y" / "c.json"
    long = tmp_path / ("n" * 200 + ".json")
    for p in (one, two, long):
        p.parent.mkdir(exist_ok=True)
        p.write_text('{"mcpServers": {}}\n')
    assert prefix_for(one) != prefix_for(two)
    names = [Path(run(p, paths, add_one()) or "").name for p in (one, two, long)]
    assert len(set(n.split(".")[0] for n in names)) == 3 and all(len(n) < 140 for n in names)
    for i in range(KEEP_BACKUPS + 3):
        run(one, paths, add_one(f"k{i}"))
    mine = [p for p in paths.backups_dir.iterdir() if p.name.startswith(prefix_for(one) + ".")]
    assert len(mine) == KEEP_BACKUPS
    assert len([p for p in paths.backups_dir.iterdir() if p.name.startswith(prefix_for(two) + ".")]) == 1


def test_toml_appended_content_uses_crlf_in_crlf_files(tmp_path: Path, paths: Paths) -> None:
    f = tmp_path / "config.toml"
    f.write_bytes(b'# top\r\n[mcp_servers.a]\r\ncommand = "x"\r\n')

    def mutate(doc: Any) -> None:
        doc["mcp_servers"]["b"] = {"command": "y", "args": ["1"]}

    run(f, paths, mutate, fmt="toml")
    raw = f.read_bytes()
    assert b"\n" not in raw.replace(b"\r\n", b"") and b"[mcp_servers.b]" in raw


def test_update_surfaces_io_errors_as_clean_errors(
    tmp_path: Path, paths: Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcp_browser_core.discovery import discover
    from mcp_browser_core.models import EntryPatch
    from mcp_browser_core.mutate import delete, update

    cfg = paths.home / ".cursor" / "mcp.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{"mcpServers": {"a": {"command": "x"}}}\n')
    eid = next(e.id for e in discover(paths).entries if e.name == "a")

    def boom(*a: Any, **k: Any) -> str:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("mcp_browser_core.writer.make_backup", boom)
    with pytest.raises(McpBrowserError, match="No space left"):
        update(eid, EntryPatch(name="b"), paths=paths)
    with pytest.raises(McpBrowserError, match="No space left"):
        delete(eid, paths=paths)
    assert "a" in json.loads(cfg.read_text())["mcpServers"]
