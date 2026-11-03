"""Codex TOML dialect, including comment preservation when editing in place."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from mcp_browser_core.dialects import get_dialect
from mcp_browser_core.errors import UnsupportedTransport
from mcp_browser_core.formats import dump, load, plain
from mcp_browser_core.models import HttpTransport, ServerEntry, SseTransport, StdioTransport
from mcp_browser_core.specs import REGISTRY

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "configs" / "codex.toml"
SPEC = REGISTRY["codex"]
D = get_dialect("codex")


def test_parse_fixture() -> None:
    doc = load(FIXTURE.read_text(encoding="utf-8"), "toml")
    docs = cast("dict[str, Any]", plain(doc["mcp_servers"]["docs"]))
    t, err, enabled, extra = D.parse("docs", docs, SPEC)
    assert err is None
    assert enabled
    assert t == StdioTransport(
        command="npx", args=["-y", "@example/docs"], env={"DOCS_TOKEN": "fake-token-444"}
    )
    assert extra == {"startup_timeout_sec": 20, "env_vars": ["HOME"]}
    remote = cast("dict[str, Any]", plain(doc["mcp_servers"]["remote"]))
    t, err, enabled, extra = D.parse("remote", remote, SPEC)
    assert t == HttpTransport(url="https://codex.example.test/mcp", headers={"X-Demo": "1"})
    assert not enabled
    assert extra == {"bearer_token_env_var": "FAKE_REMOTE_TOKEN"}


def test_edit_in_place_keeps_comments_and_other_tables() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    doc = load(text, "toml")
    live = doc["mcp_servers"]["docs"]
    _, _, _, extra = D.parse("docs", cast("dict[str, Any]", plain(live)), SPEC)
    entry = ServerEntry(
        id="x",
        name="docs",
        client_id="codex",
        scope="user",
        config_path="/p",
        transport=StdioTransport(
            command="npx", args=["-y", "@example/docs", "--new"], env={"DOCS_TOKEN": "fake-token-444"}
        ),
        extra=extra,
    )
    D.render(entry, live, SPEC)
    out = dump(doc, "toml")
    assert "# Codex demo config" in out
    assert "# main docs server" in out
    assert "# pinned later" not in out or "--new" in out  # the edited line may lose its tail comment
    assert "[profiles.fast]" in out
    assert load(out, "toml")["mcp_servers"]["docs"]["args"] == ["-y", "@example/docs", "--new"]
    assert load(out, "toml")["mcp_servers"]["remote"]["enabled"] is False


def test_sse_is_rejected() -> None:
    entry = ServerEntry(
        id="x",
        name="s",
        client_id="codex",
        scope="user",
        config_path="/p",
        transport=SseTransport(url="https://h.test/s"),
    )
    with pytest.raises(UnsupportedTransport):
        D.render(entry, None, SPEC)


def test_new_entry_roundtrips_through_toml() -> None:
    entry = ServerEntry(
        id="x",
        name="n",
        client_id="codex",
        scope="user",
        config_path="/p",
        transport=HttpTransport(url="https://h.test/m", headers={"A": "b"}),
        enabled=False,
    )
    doc = load("", "toml")
    doc["mcp_servers"] = {}
    doc["mcp_servers"]["my.srv"] = D.render(entry, None, SPEC)
    back = load(dump(doc, "toml"), "toml")
    assert plain(back["mcp_servers"]["my.srv"]) == {
        "url": "https://h.test/m",
        "http_headers": {"A": "b"},
        "enabled": False,
    }
