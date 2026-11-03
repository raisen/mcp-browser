"""mcpServers JSON variants: type styles, url keys, websocket, transport switching."""

from __future__ import annotations

from typing import Any

from mcp_browser_core.dialects import get_dialect
from mcp_browser_core.models import HttpTransport, ServerEntry, SseTransport, StdioTransport, Transport
from mcp_browser_core.specs import REGISTRY

D = get_dialect("mcpservers_json")


def _render(
    spec_id: str, t: Transport | None, existing: dict[str, Any] | None = None, **kw: Any
) -> dict[str, Any]:
    entry = ServerEntry(
        id="x", name="n", client_id=spec_id, scope="user", config_path="/p", transport=t, **kw
    )
    return D.render(entry, existing, REGISTRY[spec_id])


def test_type_written_per_style() -> None:
    http = HttpTransport(url="https://h.test/m")
    assert _render("claude-code", http)["type"] == "http"
    assert _render("cursor", SseTransport(url="https://h.test/s"))["type"] == "sse"
    assert _render("cline", http)["type"] == "streamableHttp"
    assert _render("cline", SseTransport(url="https://h.test/s"))["type"] == "sse"
    assert "type" not in _render("claude-desktop", StdioTransport(command="x"))
    assert "type" not in _render("windsurf", http)


def test_url_key_per_spec_and_existing_spelling_kept() -> None:
    http = HttpTransport(url="https://h.test/m")
    assert _render("antigravity", http) == {"serverUrl": "https://h.test/m"}
    assert _render("windsurf", http) == {"serverUrl": "https://h.test/m"}
    assert _render("cursor", http)["url"] == "https://h.test/m"
    out = _render("cursor", HttpTransport(url="https://new.test/m"), {"serverUrl": "https://old.test/m"})
    assert out == {"serverUrl": "https://new.test/m"}


def test_native_type_spelling_is_kept_when_kind_unchanged() -> None:
    existing = {"type": "streamable-http", "url": "https://h.test/m"}
    out = _render("claude-code", HttpTransport(url="https://h.test/m2"), existing)
    assert out["type"] == "streamable-http"
    assert out["url"] == "https://h.test/m2"


def test_ws_entry_is_listed_with_error_and_untouched_on_render() -> None:
    raw = {"type": "ws", "url": "wss://x.test", "keep": 1}
    transport, error, enabled, extra = D.parse("w", raw, REGISTRY["claude-code"])
    assert transport is None
    assert error is not None
    assert enabled
    assert _render("claude-code", None, dict(raw), error=error, extra=extra) == raw


def test_entry_without_command_or_url_has_error() -> None:
    transport, error, _, extra = D.parse("w", {"foo": 1}, REGISTRY["cursor"])
    assert transport is None
    assert error is not None
    assert extra == {"foo": 1}


def test_switching_kind_drops_old_keys_and_keeps_extra() -> None:
    existing = {"command": "x", "args": ["a"], "env": {"A": "1"}, "custom": 5, "type": "stdio"}
    out = _render("claude-code", HttpTransport(url="https://h.test/m"), existing, extra={"custom": 5})
    assert out == {"type": "http", "custom": 5, "url": "https://h.test/m"}


def test_removed_extra_key_and_cleared_env_are_removed() -> None:
    existing = {"command": "x", "env": {"A": "1"}, "legacy": True}
    assert _render("claude-desktop", StdioTransport(command="x"), existing) == {"command": "x"}


def test_disabled_flag() -> None:
    t = StdioTransport(command="x")
    assert _render("cline", t, enabled=False)["disabled"] is True
    assert "disabled" not in _render("cline", t)
    assert _render("cline", t, {"command": "x", "disabled": True})["disabled"] is False
    assert D.parse("n", {"command": "x", "disabled": True}, REGISTRY["cline"])[2] is False
