"""CRUD, masking, reveal, error bodies and static files, against real config files."""

from __future__ import annotations

import json
import logging
import mimetypes
from pathlib import Path
from typing import Any

import pytest
from mcp_browser_core import mutate
from mcp_browser_core.paths import Paths
from mcp_browser_server import deps
from starlette.testclient import TestClient

from .conftest import SECRETS, TOKEN, AsgiCall, cursor_file, entry_id, write_json


def add_body(name: str = "gamma", **transport: Any) -> dict[str, Any]:
    t = {
        "kind": "stdio",
        "command": "gamma-cmd",
        "args": ["a"],
        "env": {"TOKEN": "REAL_SECRET_1"},
        **transport,
    }
    return {"name": name, "transport": t, "targets": [{"client_id": "cursor", "scope": "user"}]}


def read_servers(paths: Paths) -> dict[str, Any]:
    return json.loads(cursor_file(paths).read_text(encoding="utf-8"))["mcpServers"]


def test_healthz_reports_version_and_pid(anon: TestClient) -> None:
    import os

    body = anon.get("/healthz").json()
    assert body["ok"] is True and body["pid"] == os.getpid() and body["version"]


@pytest.mark.usefixtures("secret_config")
def test_only_reveal_returns_real_values(client: TestClient) -> None:
    ident = entry_id(client, "alpha")
    for path in ("/api/servers", f"/api/servers/{ident}", "/api/clients", "/api/projects"):
        r = client.get(path)
        assert r.status_code == 200
        assert not any(s in r.text for s in SECRETS), path
        assert TOKEN not in r.text
    assert "•••" in client.get(f"/api/servers/{ident}").text
    revealed = client.get(f"/api/servers/{ident}/reveal").json()
    assert revealed["transport"]["env"] == {"API_KEY": "SECRET_ENV_VALUE"}
    assert "SECRET_ARG_VALUE" in revealed["transport"]["args"]
    beta = client.get(f"/api/servers/{entry_id(client, 'beta')}/reveal").json()["transport"]
    assert "SECRET_QUERY_VALUE" in beta["url"] and beta["headers"]["Authorization"].endswith(
        "SECRET_HEADER_TOKEN"
    )


def test_unknown_id_is_404_with_error_body(client: TestClient) -> None:
    for method, path in [("GET", "x"), ("GET", "x/reveal"), ("PUT", "x"), ("DELETE", "x")]:
        r = client.request(method, f"/api/servers/{path}", json={})
        assert r.status_code == 404 and r.json()["error"] == "not_found"


def test_scan_route_does_not_collide_with_id_routes(client: TestClient) -> None:
    assert client.post("/api/servers/scan", json={"ids": []}).json() == []
    r = client.get("/api/servers/scan")
    assert r.status_code == 404 and r.json()["error"] == "not_found"  # an id, not a route
    assert client.delete("/api/servers/scan").status_code == 404


def test_add_returns_add_results_masked_and_writes_the_file(client: TestClient, paths: Paths) -> None:
    r = client.post("/api/servers", json=add_body())
    assert r.status_code == 200 and "REAL_SECRET_1" not in r.text
    [result] = r.json()
    assert result["error"] is None and result["report"]["created_file"] is True
    assert result["report"]["entry"]["transport"]["env"] == {"TOKEN": "•••"}
    assert read_servers(paths)["gamma"]["env"] == {"TOKEN": "REAL_SECRET_1"}
    assert any(e["name"] == "gamma" for e in client.get("/api/servers").json()["entries"])  # cache refreshed


def test_add_duplicate_is_409_and_nothing_is_written(client: TestClient, paths: Paths) -> None:
    assert client.post("/api/servers", json=add_body()).status_code == 200
    two = add_body()
    two["targets"].append({"client_id": "windsurf", "scope": "user"})
    r = client.post("/api/servers", json=two)
    assert r.status_code == 409 and r.json()["error"] == "name_exists"
    assert not (paths.home / ".codeium").exists()


def test_masked_values_are_rejected_everywhere(client: TestClient, paths: Paths, secret_config: Path) -> None:
    before = secret_config.read_text(encoding="utf-8")
    ident = entry_id(client, "alpha")
    bad = add_body(env={"TOKEN": "•••"})
    r = client.post("/api/servers", json=bad)
    assert r.status_code == 400 and r.json()["error"] == "invalid_arguments"
    r = client.post("/api/servers", json={**add_body(), "extra": {"note": "x•••y"}})
    assert r.status_code == 400
    r = client.put(
        f"/api/servers/{ident}", json={"transport": add_body()["transport"] | {"env": {"K": "•••"}}}
    )
    assert r.status_code == 400 and r.json()["error"] == "invalid_arguments"
    r = client.put(f"/api/servers/{ident}", json={"extra": {"headers": {"A": "•••"}}})
    assert r.status_code == 400
    assert secret_config.read_text(encoding="utf-8") == before


def test_invalid_body_error_does_not_echo_secrets(client: TestClient) -> None:
    body = add_body(kind="carrier-pigeon")
    r = client.post("/api/servers", json=body)
    assert r.status_code == 400 and r.json()["error"] == "invalid_arguments"
    assert "REAL_SECRET_1" not in r.text and r.json()["detail"]["errors"]
    assert (
        client.post(
            "/api/servers", content=b"{nope", headers={"content-type": "application/json"}
        ).status_code
        == 400
    )


@pytest.mark.usefixtures("secret_config")
def test_put_renames_and_replaces_extra_in_one_write(client: TestClient, paths: Paths) -> None:
    old = entry_id(client, "alpha")
    body: dict[str, Any] = {
        "name": "alpha2",
        "transport": {
            "kind": "stdio",
            "command": "new-cmd",
            "args": [],
            "env": {"API_KEY": "SECRET_ENV_VALUE"},
        },
        "extra": {"timeout": 5},
    }
    r = client.put(f"/api/servers/{old}", json=body)
    assert r.status_code == 200 and "SECRET_ENV_VALUE" not in r.text
    report = r.json()
    assert report["entry"]["name"] == "alpha2" and report["backup_path"]
    servers = read_servers(paths)
    assert (
        "alpha" not in servers
        and servers["alpha2"]["command"] == "new-cmd"
        and servers["alpha2"]["timeout"] == 5
    )
    assert client.get(f"/api/servers/{old}").status_code == 404
    assert client.get(f"/api/servers/{report['entry']['id']}").status_code == 200
    assert next(iter(servers)) == "alpha2"  # position kept


@pytest.mark.usefixtures("secret_config")
def test_rename_to_existing_name_is_409(client: TestClient) -> None:
    r = client.put(f"/api/servers/{entry_id(client, 'alpha')}", json={"name": "beta"})
    assert r.status_code == 409 and r.json()["error"] == "name_exists"


@pytest.mark.usefixtures("secret_config")
def test_delete_removes_entry_and_masks_the_report(client: TestClient, paths: Paths) -> None:
    r = client.delete(f"/api/servers/{entry_id(client, 'alpha')}?allow_comment_loss=false")
    assert r.status_code == 200 and "SECRET_ENV_VALUE" not in r.text
    assert "alpha" not in read_servers(paths) and "beta" in read_servers(paths)


def test_comments_in_jsonc_block_the_write_with_can_override(client: TestClient, paths: Paths) -> None:
    f = cursor_file(paths)
    f.parent.mkdir(parents=True)
    f.write_text('{\n  // keep me\n  "mcpServers": {}\n}\n', encoding="utf-8")
    r = client.post("/api/servers", json=add_body())
    assert r.status_code == 409 and r.json()["error"] == "comments_would_be_lost"
    assert r.json()["detail"]["can_override"] is True and "keep me" in f.read_text(encoding="utf-8")
    assert client.post("/api/servers", json=add_body() | {"allow_comment_loss": True}).status_code == 200


def test_restart_hint_data_comes_from_clients(client: TestClient) -> None:
    body = add_body() | {"targets": [{"client_id": "claude-desktop", "scope": "user"}]}
    [result] = client.post("/api/servers", json=body).json()
    clients = {c["id"]: c for c in client.get("/api/clients").json()}
    assert result["report"] and clients[result["target"]["client_id"]]["needs_restart"] is True
    assert clients["cursor"]["needs_restart"] is False


def test_claude_code_offers_a_local_target_per_project_key(client: TestClient, paths: Paths) -> None:
    key = "/work/some project"
    write_json(paths.home / ".claude.json", {"projects": {key: {"mcpServers": {}}, "C:\\Work\\p": {}}})
    code = next(c for c in client.get("/api/clients").json() if c["id"] == "claude-code")
    local = {p["project"] for p in code["config_paths"] if p["scope"] == "local"}
    assert local == {key, "C:\\Work\\p"}
    body = add_body() | {"targets": [{"client_id": "claude-code", "scope": "local", "project": key}]}
    [result] = client.post("/api/servers", json=body).json()
    assert result["error"] is None and result["report"]["entry"]["project"] == key


def test_io_failure_is_a_clean_json_error(
    client: TestClient, secret_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ident = entry_id(client, "alpha")

    def boom(*_a: object, **_k: object) -> None:
        raise PermissionError(13, "Permission denied", "/private/SECRET_PATH_PART")

    monkeypatch.setattr(mutate, "delete", boom)
    monkeypatch.setattr(mutate, "update", boom)
    for r in (
        client.delete(f"/api/servers/{ident}"),
        client.put(f"/api/servers/{ident}", json={"name": "z"}),
    ):
        assert r.status_code == 500 and r.json()["error"] == "io_error"
        assert "SECRET_PATH_PART" not in r.text and "Traceback" not in r.text
    assert secret_config.exists()


def test_unexpected_exception_leaks_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("SECRET_BOOM_TEXT")

    monkeypatch.setattr(deps, "discover", boom)
    with caplog.at_level(logging.DEBUG):
        r = client.get("/api/servers?refresh=1")
    assert r.status_code == 500
    assert r.json() == {"error": "internal_error", "message": "internal error", "detail": {}}
    assert "SECRET_BOOM_TEXT" not in r.text + caplog.text and "RuntimeError" in caplog.text


@pytest.mark.usefixtures("secret_config")
def test_discovery_is_cached_until_refresh(client: TestClient, paths: Paths) -> None:
    assert len(client.get("/api/servers").json()["entries"]) == 2
    write_json(cursor_file(paths), {"mcpServers": {"only": {"command": "x"}}})
    assert len(client.get("/api/servers").json()["entries"]) == 2
    assert [e["name"] for e in client.get("/api/servers?refresh=1").json()["entries"]] == ["only"]


@pytest.mark.anyio
async def test_static_files_have_explicit_types(asgi: AsgiCall) -> None:
    mimetypes.add_type("text/plain", ".js")  # what a broken Windows registry can do
    expected = {
        "/static/js/main.js": "text/javascript",
        "/static/css/base.css": "text/css",
        "/": "text/html",
    }
    for path, kind in expected.items():
        status, headers, _ = await asgi(path)
        assert status == 200 and headers["content-type"].startswith(kind), path
    for path in ("/static/js/nope.js", "/static/js", "/static//js/main.js", "/static/js/main.js/"):
        assert (await asgi(path))[0] == 404, path
