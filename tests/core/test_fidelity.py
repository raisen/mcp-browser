"""Edits never rewrite what they did not touch: raw value types, stale keys, extra vs mapped keys."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mcp_browser_core.discovery import active_user_file, discover
from mcp_browser_core.errors import UnsupportedTransport
from mcp_browser_core.formats import load, plain
from mcp_browser_core.models import EntryPatch, HttpTransport, NewEntry, StdioTransport, Target
from mcp_browser_core.mutate import add, update
from mcp_browser_core.paths import Paths
from mcp_browser_core.specs import REGISTRY


def put(paths: Paths, client: str, text: str) -> Path:
    dest = active_user_file(paths, REGISTRY[client])
    assert dest is not None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest


def entry_id(paths: Paths, client: str, name: str) -> str:
    return next(e.id for e in discover(paths).entries if e.client_id == client and e.name == name)


def servers(path: Path, key: str = "mcpServers") -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))[key]


RAW_ENV = {"PORT": 8080, "F": True, "N": None, "O": 1.5, "S": "s"}
RAW_ARGS = ["a", 1, True]


@pytest.mark.parametrize("client", ["cursor", "claude-code", "gemini", "windsurf"])
def test_rename_keeps_non_string_env_and_args(paths: Paths, client: str) -> None:
    f = put(
        paths, client, json.dumps({"mcpServers": {"a": {"command": "x", "args": RAW_ARGS, "env": RAW_ENV}}})
    )
    update(entry_id(paths, client, "a"), EntryPatch(name="b"), paths=paths)
    assert servers(f)["b"] == {"command": "x", "args": RAW_ARGS, "env": RAW_ENV}


def test_vscode_and_remote_headers_keep_raw_values(paths: Paths) -> None:
    f = put(
        paths, "vscode", json.dumps({"servers": {"a": {"type": "stdio", "command": "x", "env": RAW_ENV}}})
    )
    update(entry_id(paths, "vscode", "a"), EntryPatch(name="a2"), paths=paths)
    assert servers(f, "servers")["a2"]["env"] == RAW_ENV
    g = put(
        paths,
        "cursor",
        json.dumps({"mcpServers": {"r": {"url": "https://h.test/m", "headers": {"N": 5, "T": False}}}}),
    )
    update(entry_id(paths, "cursor", "r"), EntryPatch(name="r2"), paths=paths)
    assert servers(g)["r2"]["headers"] == {"N": 5, "T": False}


def test_partial_edit_changes_only_edited_values(paths: Paths) -> None:
    f = put(
        paths, "cursor", json.dumps({"mcpServers": {"a": {"command": "x", "args": RAW_ARGS, "env": RAW_ENV}}})
    )
    eid = entry_id(paths, "cursor", "a")
    t = next(e for e in discover(paths).entries if e.id == eid).transport
    assert isinstance(t, StdioTransport)
    assert t.env["PORT"] == "8080" and t.args == ["a", "1", "True"]
    env = dict(t.env, S="new", PORT="9090")
    update(
        eid,
        EntryPatch(transport=t.model_copy(update={"env": env, "args": ["a", "1", "True", "z"]})),
        paths=paths,
    )
    out = servers(f)["a"]
    assert out["env"] == {"PORT": "9090", "F": True, "N": None, "O": 1.5, "S": "new"}
    assert out["args"] == ["a", 1, True, "z"]


def _codex_file(paths: Paths, body: str) -> Path:
    return put(paths, "codex", body)


HTTP_TOML = """[mcp_servers.r]
url = "https://h.test/m"
bearer_token_env_var = "TOK"
env_http_headers = { X = "Y" }
scopes = ["a"]
auth = "x"
oauth_resource = "https://h.test"

[mcp_servers.r.http_headers]
A = "1"
"""
STDIO_TOML = """[mcp_servers.s]
command = "npx"
args = ["-y"]
cwd = "/w"
env_vars = ["HOME"]
startup_timeout_sec = 20

[mcp_servers.s.env]
K = "v"
"""


def test_codex_http_to_stdio_drops_http_only_keys(paths: Paths) -> None:
    f = _codex_file(paths, HTTP_TOML)
    patch = EntryPatch(transport=StdioTransport(command="npx", args=["-y"]))
    update(entry_id(paths, "codex", "r"), patch, paths=paths)
    assert plain(load(f.read_text(), "toml"))["mcp_servers"]["r"] == {"command": "npx", "args": ["-y"]}


def test_codex_stdio_to_http_drops_stdio_only_keys(paths: Paths) -> None:
    f = _codex_file(paths, STDIO_TOML)
    patch = EntryPatch(transport=HttpTransport(url="https://h.test/m"))
    update(entry_id(paths, "codex", "s"), patch, paths=paths)
    out = plain(load(f.read_text(), "toml"))["mcp_servers"]["s"]
    assert out == {"url": "https://h.test/m", "startup_timeout_sec": 20}


def test_same_kind_edit_keeps_unrelated_keys(paths: Paths) -> None:
    f = _codex_file(paths, STDIO_TOML)
    update(entry_id(paths, "codex", "s"), EntryPatch(name="s2"), paths=paths)
    out = plain(load(f.read_text(), "toml"))["mcp_servers"]["s2"]
    assert out["env_vars"] == ["HOME"] and out["cwd"] == "/w" and out["startup_timeout_sec"] == 20


def test_gemini_and_vscode_kind_change_drop_other_kind_keys(paths: Paths) -> None:
    g = put(
        paths,
        "gemini",
        json.dumps({"mcpServers": {"a": {"httpUrl": "https://h.test/m", "headers": {"A": "1"}, "tcp": 1}}}),
    )
    update(entry_id(paths, "gemini", "a"), EntryPatch(transport=StdioTransport(command="x")), paths=paths)
    assert servers(g)["a"] == {"command": "x"}
    v = put(
        paths,
        "vscode",
        json.dumps({"servers": {"a": {"type": "stdio", "command": "x", "envFile": "/e", "cwd": "/w"}}}),
    )
    update(
        entry_id(paths, "vscode", "a"),
        EntryPatch(transport=HttpTransport(url="https://h.test/m")),
        paths=paths,
    )
    assert servers(v, "servers")["a"] == {"type": "http", "url": "https://h.test/m"}


def test_zed_kind_change_drops_other_kind_keys(paths: Paths) -> None:
    z = put(
        paths,
        "zed",
        json.dumps(
            {"context_servers": {"a": {"source": "custom", "url": "https://h.test/m", "headers": {"A": "1"}}}}
        ),
    )
    update(entry_id(paths, "zed", "a"), EntryPatch(transport=StdioTransport(command="x")), paths=paths)
    assert servers(z, "context_servers")["a"] == {"source": "custom", "command": "x"}


def test_add_extra_cannot_override_mapped_keys(paths: Paths) -> None:
    f = put(paths, "cursor", '{"mcpServers": {}}')
    evil = {"command": "EVIL", "url": "https://evil.test", "args": ["x"], "disabled": True}
    new = NewEntry(name="n", transport=StdioTransport(command="good"), extra=evil | {"keep": 1})
    add(new, [Target(client_id="cursor", scope="user")], paths=paths)
    out = servers(f)["n"]
    assert out["command"] == "good" and "url" not in out and "disabled" not in out and out["keep"] == 1
    http = NewEntry(name="h", transport=HttpTransport(url="https://good.test"), extra=evil)
    add(http, [Target(client_id="cursor", scope="user")], paths=paths)
    out = servers(f)["h"]
    assert out["url"] == "https://good.test" and "command" not in out and "args" not in out


def test_leftover_url_in_extra_does_not_beat_new_transport(paths: Paths) -> None:
    f = put(paths, "cursor", json.dumps({"mcpServers": {"a": {"command": "x", "url": "https://old.test"}}}))
    eid = entry_id(paths, "cursor", "a")
    update(eid, EntryPatch(transport=HttpTransport(url="https://new.test")), paths=paths)
    assert servers(f)["a"]["url"] == "https://new.test"
    put(paths, "codex", '[mcp_servers.a]\ncommand = "x"\nurl = "https://old.test"\n')
    c = entry_id(paths, "codex", "a")
    update(c, EntryPatch(transport=HttpTransport(url="https://new.test")), paths=paths)
    g = active_user_file(paths, REGISTRY["codex"])
    assert g is not None
    assert plain(load(g.read_text(), "toml"))["mcp_servers"]["a"] == {"url": "https://new.test"}


def test_zed_refuses_cwd_up_front_and_writes_nothing(paths: Paths) -> None:
    z = put(paths, "zed", '{"context_servers": {}}\n')
    c = put(paths, "cursor", '{"mcpServers": {}}\n')
    new = NewEntry(name="n", transport=StdioTransport(command="x", cwd="/w"))
    with pytest.raises(UnsupportedTransport, match="cwd"):
        add(
            new,
            [Target(client_id="cursor", scope="user"), Target(client_id="zed", scope="user")],
            paths=paths,
        )
    assert z.read_text() == '{"context_servers": {}}\n' and c.read_text() == '{"mcpServers": {}}\n'


def test_zed_edit_of_entry_with_existing_cwd_key_keeps_it(paths: Paths) -> None:
    z = put(paths, "zed", json.dumps({"context_servers": {"a": {"command": "x", "cwd": "/w"}}}))
    update(entry_id(paths, "zed", "a"), EntryPatch(name="b"), paths=paths)
    assert servers(z, "context_servers")["b"]["cwd"] == "/w"


def test_gemini_settings_with_comments_lists_and_refuses_writes(paths: Paths) -> None:
    from mcp_browser_core.errors import CommentsWouldBeLost

    text = '{\n  // my theme\n  "theme": "dark",\n  "mcpServers": {"a": {"command": "x"}}\n}\n'
    f = put(paths, "gemini", text)
    assert entry_id(paths, "gemini", "a")
    with pytest.raises(CommentsWouldBeLost) as info:
        update(entry_id(paths, "gemini", "a"), EntryPatch(name="b"), paths=paths, allow_comment_loss=True)
    assert info.value.detail["can_override"] is False
    assert f.read_text() == text
