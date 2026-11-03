"""Gemini, VS Code and Zed dialect specifics."""

from __future__ import annotations

from typing import Any

import pytest
from mcp_browser_core.dialects import get_dialect
from mcp_browser_core.errors import UnsupportedTransport
from mcp_browser_core.models import HttpTransport, ServerEntry, SseTransport, StdioTransport, Transport
from mcp_browser_core.specs import REGISTRY


def _render(
    spec_id: str, t: Transport | None, existing: dict[str, Any] | None = None, **kw: Any
) -> dict[str, Any]:
    spec = REGISTRY[spec_id]
    entry = ServerEntry(
        id="x", name="n", client_id=spec_id, scope="user", config_path="/p", transport=t, **kw
    )
    return get_dialect(spec.dialect).render(entry, existing, spec)


def test_gemini_http_vs_sse_keys() -> None:
    spec, d = REGISTRY["gemini"], get_dialect("gemini")
    http, *_ = d.parse("h", {"httpUrl": "https://h.test/m"}, spec)
    sse, *_ = d.parse("s", {"url": "https://h.test/s"}, spec)
    assert isinstance(http, HttpTransport)
    assert isinstance(sse, SseTransport)
    assert _render("gemini", http) == {"httpUrl": "https://h.test/m"}
    assert _render("gemini", sse) == {"url": "https://h.test/s"}
    switched = _render("gemini", sse, {"httpUrl": "https://h.test/m", "trust": True}, extra={"trust": True})
    assert switched == {"url": "https://h.test/s", "trust": True}


def test_gemini_keeps_unknown_fields() -> None:
    raw = {"command": "x", "includeTools": ["a"], "timeout": 5}
    t, _, _, extra = get_dialect("gemini").parse("n", raw, REGISTRY["gemini"])
    assert extra == {"includeTools": ["a"], "timeout": 5}
    assert _render("gemini", t, dict(raw), extra=extra) == raw


def test_vscode_always_writes_type() -> None:
    assert _render("vscode", StdioTransport(command="x"))["type"] == "stdio"
    assert _render("vscode", HttpTransport(url="https://h.test"))["type"] == "http"
    assert _render("vscode", SseTransport(url="https://h.test"))["type"] == "sse"


def test_vscode_input_placeholders_are_kept_verbatim() -> None:
    raw = {"type": "stdio", "command": "x", "env": {"K": "${input:tok}"}}
    t, err, _, extra = get_dialect("vscode").parse("n", raw, REGISTRY["vscode"])
    assert err is None
    assert isinstance(t, StdioTransport)
    assert t.env == {"K": "${input:tok}"}
    assert _render("vscode", t, dict(raw), extra=extra) == raw


def test_zed_adds_source_custom_only_for_new_entries() -> None:
    assert _render("zed", StdioTransport(command="x"))["source"] == "custom"
    existing = {"command": "x"}
    assert "source" not in _render("zed", StdioTransport(command="x"), existing)


def test_zed_enabled_flag_and_sse_rejection() -> None:
    assert _render("zed", HttpTransport(url="https://h.test"), enabled=False)["enabled"] is False
    with pytest.raises(UnsupportedTransport):
        _render("zed", SseTransport(url="https://h.test"))


def test_zed_legacy_command_form_is_listed_with_error() -> None:
    raw = {"command": {"path": "npx", "args": ["x"]}}
    t, err, _, extra = get_dialect("zed").parse("n", raw, REGISTRY["zed"])
    assert t is None
    assert err
    assert _render("zed", None, dict(raw), error=err, extra=extra) == raw
