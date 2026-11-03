"""Connecting, scanning and calling through the API with the real stdio fixture server."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp_browser_core.models import HttpTransport, ServerEntry, StdioTransport
from mcp_browser_core.paths import Paths
from mcp_browser_server import deps
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.testclient import TestClient

from .conftest import FIXTURE, cursor_file, entry_id, fixture_entry, write_json


@pytest.fixture
def fx(paths: Paths, client: TestClient) -> str:
    write_json(cursor_file(paths), {"mcpServers": {"fx": fixture_entry()}})
    return entry_id(client, "fx")


def call(client: TestClient, ident: str, tool: str, args: dict[str, Any], **extra: Any) -> Any:
    return client.post(f"/api/servers/{ident}/tools/{tool}/call", json={"arguments": args, **extra})


def test_limiter_is_created_in_lifespan(app: Starlette, client: TestClient) -> None:
    assert isinstance(app.state.limiter, anyio.CapacityLimiter) and app.state.limiter.total_tokens == 8
    assert client.get("/healthz").status_code == 200


def test_connect_lists_the_fixture_server_and_stores_the_result(client: TestClient, fx: str) -> None:
    r = client.post(f"/api/servers/{fx}/connect", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["entry_id"] == fx
    assert sorted(t["name"] for t in body["tools"]) == ["add", "echo", "fail", "slow"]
    assert [x["uri"] for x in body["resources"]] == ["res://a"]
    listing = client.get("/api/servers").json()
    assert [c["entry_id"] for c in listing["catalog"]] == [fx]
    assert client.get(f"/api/servers/{fx}").json()["catalog"]["status"] == "ok"
    assert client.post(f"/api/servers/{fx}/connect").status_code == 200  # no body at all


def test_real_stdio_tool_call_end_to_end(client: TestClient, fx: str) -> None:
    client.post(f"/api/servers/{fx}/connect", json={})
    r = call(client, fx, "add", {"a": 1, "b": 2})
    assert r.status_code == 200
    assert r.json()["structured"] == {"result": 3} and r.json()["content"][0]["text"] == "3"
    assert r.json()["is_error"] is False
    assert call(client, fx, "echo", {"text": "hi"}).json()["content"][0]["text"] == "hi"
    failed = call(client, fx, "fail", {})
    assert failed.status_code == 200 and failed.json()["is_error"] is True


def test_schema_violation_is_invalid_arguments_before_anything_starts(client: TestClient, fx: str) -> None:
    client.post(f"/api/servers/{fx}/connect", json={})
    for args in ({"a": "x", "b": 2}, {"a": 1}, {}):
        r = call(client, fx, "add", args)
        assert r.status_code == 400 and r.json()["error"] == "invalid_arguments", args
        assert r.json()["detail"]["errors"]


def test_schema_violation_without_a_prior_connect(client: TestClient, fx: str) -> None:
    r = call(client, fx, "add", {"a": "x", "b": 2})
    assert r.status_code == 400 and r.json()["detail"]["errors"]
    assert call(client, fx, "add", {"a": 2, "b": 2}).json()["structured"] == {"result": 4}


def test_unknown_tool_is_404(client: TestClient, fx: str) -> None:
    r = call(client, fx, "nope", {})
    assert r.status_code == 404 and r.json()["error"] == "not_found"


def test_call_timeout_is_504(client: TestClient, fx: str) -> None:
    r = call(client, fx, "slow", {"seconds": 10}, call_timeout=1)
    assert r.status_code == 504 and r.json()["error"] == "timeout"
    assert call(client, fx, "add", {"a": 1, "b": 1}, call_timeout=-1).status_code == 400


def test_resources_and_prompts(client: TestClient, fx: str) -> None:
    r = client.post(f"/api/servers/{fx}/resources/read", json={"uri": "res://a"})
    assert r.status_code == 200 and r.json()[0]["text"] == "resource a"
    r = client.post(f"/api/servers/{fx}/prompts/greet", json={"arguments": {"name": "Ann"}})
    assert r.status_code == 200 and "Hello Ann" in r.text


def test_scan_connects_only_when_asked(client: TestClient, fx: str) -> None:
    assert client.get("/api/servers").json()["catalog"] == []
    assert client.post("/api/servers/scan", json={"ids": ["unknown"]}).json() == []
    out = client.post("/api/servers/scan", json={"ids": [fx]}).json()
    assert [(c["entry_id"], c["status"]) for c in out] == [(fx, "ok")]
    assert [c["entry_id"] for c in client.get("/api/servers").json()["catalog"]] == [fx]
    assert client.post("/api/servers/scan").json()[0]["status"] == "ok"  # no ids: every usable entry


def test_get_routes_never_spawn_anything(client: TestClient, paths: Paths) -> None:
    marker = paths.home / "spawned.txt"
    code = f"open({str(marker)!r}, 'w').write('x')"
    write_json(cursor_file(paths), {"mcpServers": {"spy": {"command": sys.executable, "args": ["-c", code]}}})
    ident = entry_id(client, "spy")
    for path in ("/api/servers", f"/api/servers/{ident}", f"/api/servers/{ident}/reveal", "/api/clients"):
        assert client.get(path).status_code == 200
    assert not marker.exists()
    client.post("/api/servers/scan", json={"ids": []})
    assert not marker.exists()


def test_connect_failures_map_to_502_with_stderr_tail(client: TestClient, paths: Paths) -> None:
    code = "import os,sys; print(os.environ['K'], file=sys.stderr); sys.exit(1)"
    write_json(
        cursor_file(paths),
        {
            "mcpServers": {
                "missing": {"command": "definitely-not-a-command-xyz"},
                "leaky": {
                    "command": sys.executable,
                    "args": ["-c", code],
                    "env": {"K": "SECRET_ECHOED_VALUE"},
                },
                "refused": {"url": "http://127.0.0.1:1/mcp", "type": "http"},
            }
        },
    )
    for name in ("missing", "leaky", "refused"):
        r = client.post(f"/api/servers/{entry_id(client, name)}/connect", json={"connect_timeout": 20})
        assert r.status_code == 502 and r.json()["error"] == "connect_failed", name
        assert "stderr_tail" in r.json()["detail"]
        assert "SECRET_ECHOED_VALUE" not in r.text
    leaky = client.post(f"/api/servers/{entry_id(client, 'leaky')}/connect", json={})
    assert "•••" in leaky.json()["detail"]["stderr_tail"]
    scanned = client.post("/api/servers/scan", json={"ids": [entry_id(client, "leaky")]})
    assert (
        "SECRET_ECHOED_VALUE" not in scanned.text
        and "SECRET_ECHOED_VALUE" not in client.get("/api/servers").text
    )


def test_unresolved_placeholders_are_400(client: TestClient, paths: Paths) -> None:
    write_json(
        cursor_file(paths), {"mcpServers": {"p": {"command": sys.executable, "args": ["${NOPE_XYZ_UNSET}"]}}}
    )
    r = client.post(f"/api/servers/{entry_id(client, 'p')}/connect", json={})
    assert r.status_code == 400 and r.json()["error"] == "unresolved_placeholders"
    assert r.json()["detail"]["placeholders"] == ["NOPE_XYZ_UNSET"]


def test_connect_deadline_depends_on_oauth_possibility(app: Starlette) -> None:
    def req() -> Request:
        return Request({"type": "http", "app": app, "headers": [], "query_string": b""})

    def entry(t: StdioTransport | HttpTransport) -> ServerEntry:
        return ServerEntry(id="i", name="n", client_id="cursor", scope="user", config_path="/x", transport=t)

    stdio = entry(StdioTransport(command="c"))
    remote = entry(HttpTransport(url="https://example.invalid/mcp"))
    keyed = entry(HttpTransport(url="https://example.invalid/mcp", headers={"authorization": "Bearer x"}))
    assert deps.options(req(), stdio).connect_timeout == 30.0
    assert deps.options(req(), remote).connect_timeout >= 300.0
    assert deps.options(req(), keyed).connect_timeout == 30.0
    assert deps.options(req(), remote, connect=5).connect_timeout == 5.0
    assert deps.options(req(), stdio, call=7).call_timeout == 7.0


def test_fixture_path_is_not_posix_specific() -> None:
    assert Path(FIXTURE).is_file()
