"""Every /api route needs the token; Host and Origin are checked; the open paths are exact."""

from __future__ import annotations

import json

import anyio
import pytest
from mcp_browser_core.errors import ConnectFailed
from mcp_browser_server.auth import needs_token
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from .conftest import HOST, PORT, TOKEN, AsgiCall

BEARER = {"Authorization": f"Bearer {TOKEN}"}


def api_routes(app: Starlette) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for route in app.routes:
        if isinstance(route, Route) and route.path.startswith("/api"):
            path = route.path.replace("{id}", "x").replace("{tool}", "t").replace("{name}", "n")
            out += [(m, path) for m in sorted(route.methods or ()) if m not in ("HEAD", "OPTIONS")]
    return out


def test_route_table_is_covered(app: Starlette) -> None:
    routes = api_routes(app)
    assert len(routes) >= 13  # a vacuous iteration would pass the tests below
    assert ("POST", "/api/servers/scan") in routes


@pytest.mark.parametrize("header", [None, "Bearer wrong", f"Basic {TOKEN}", TOKEN, "Bearer "])
def test_every_api_route_rejects_missing_or_wrong_token(
    anon: TestClient, app: Starlette, header: str | None
) -> None:
    headers = {"Authorization": header} if header is not None else {}
    for method, path in api_routes(app):
        r = anon.request(method, path, headers=headers, json={})
        assert r.status_code == 401, (method, path)
        assert r.json()["error"] == "unauthorized"
        assert set(r.json()) == {"error", "message", "detail"}


def test_unknown_paths_need_the_token_too(anon: TestClient, client: TestClient) -> None:
    assert anon.get("/nope").status_code == 401
    r = client.get("/nope")
    assert r.status_code == 404 and r.json()["error"] == "not_found"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "evil.example:8765",
        "127.0.0.1",
        "localhost",
        "127.0.0.1:9999",
        f"127.0.0.1:{PORT}.evil.example",
        f"127.0.0.1.evil.example:{PORT}",
        f"localhost.evil.example:{PORT}",
        f"[::1]:{PORT}",
        f"0.0.0.0:{PORT}",
        f"user@127.0.0.1:{PORT}",
        "",
    ],
)
async def test_foreign_host_is_400(asgi: AsgiCall, host: str) -> None:
    for path in ("/healthz", "/", "/api/clients", "/oauth/callback"):
        status, _, body = await asgi(path, BEARER, host=host)
        assert status == 400, (host, path)
        assert json.loads(body)["error"] == "bad_host"


@pytest.mark.anyio
async def test_missing_host_is_400(asgi: AsgiCall) -> None:
    assert (await asgi("/healthz", host=None))[0] == 400


@pytest.mark.anyio
@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "null",
        f"http://127.0.0.1:{PORT}.evil.example",
        "http://127.0.0.1",
        "ftp://127.0.0.1:8765",
    ],
)
async def test_foreign_origin_is_403(asgi: AsgiCall, origin: str) -> None:
    for path in ("/healthz", "/api/clients"):
        status, _, body = await asgi(path, {**BEARER, "Origin": origin})
        assert status == 403, (origin, path)
        assert json.loads(body)["error"] == "bad_origin"


@pytest.mark.anyio
@pytest.mark.parametrize("origin", [f"http://{HOST}", f"http://localhost:{PORT}", f"https://{HOST}"])
async def test_own_origin_is_accepted(asgi: AsgiCall, origin: str) -> None:
    assert (await asgi("/api/clients", {**BEARER, "Origin": origin}))[0] == 200


@pytest.mark.anyio
async def test_the_token_free_allowlist_is_exact(asgi: AsgiCall) -> None:
    assert (await asgi("/healthz"))[0] == 200
    assert (await asgi("/"))[0] == 200
    status, headers, _ = await asgi("/static/js/main.js")
    assert status == 200 and headers["content-type"].startswith("text/javascript")
    assert (await asgi("/oauth/callback"))[0] == 400  # reached the handler, not the auth wall
    for path in ("/healthz/", "/healthz/x", "/oauth/callback/x", "/static", "//", "/index.html", "/api"):
        assert (await asgi(path))[0] == 401, path


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    [
        "/static/../api/servers",
        "/healthz/../api/servers",
        "/static/./../api/servers",
        "/static/js/../../api/servers",
        "/static/..\\api\\servers",
        "/static/%2e%2e/api/servers",
        "/oauth/callback/../api/servers",
        "//api/servers",
    ],
)
async def test_path_tricks_do_not_bypass_auth(asgi: AsgiCall, path: str) -> None:
    status, _, body = await asgi(path)
    assert status == 401 and json.loads(body)["error"] == "unauthorized"
    status, _, body = await asgi(path, BEARER)  # with the token the API still must not answer
    assert "entries" not in body and status != 200


def test_needs_token_unit() -> None:
    assert [needs_token(p) for p in ("/healthz", "/", "/static/a.js", "/api/servers", "/static/../x")] == [
        False,
        False,
        False,
        True,
        True,
    ]


@pytest.mark.anyio
async def test_oauth_callback_rejects_unknown_state_and_escapes(asgi: AsgiCall) -> None:
    status, _, body = await asgi("/oauth/callback", query="code=c&state=%3Cb%3Eguess")
    assert status == 400 and "<b>" not in body
    status, _, body = await asgi("/oauth/callback", query="error=%3Cscript%3Ealert(1)%3C/script%3E&state=s")
    assert status == 400
    assert "<script>" not in body and "&lt;script&gt;" in body
    status, _, _ = await asgi("/oauth/callback", query="state=abc")  # no code
    assert status == 400


@pytest.mark.anyio
async def test_oauth_callback_completes_a_pending_sign_in_once(app: Starlette, asgi: AsgiCall) -> None:
    redirect, callback = app.state.oauth_hook.handlers()
    await redirect("https://idp.invalid/authorize?state=known-state&x=1")
    result: list[str] = []

    async def wait() -> None:
        result.append((await callback()).code)

    async with anyio.create_task_group() as tg:
        tg.start_soon(wait)
        await anyio.sleep(0.05)
        status, _, body = await asgi("/oauth/callback", query="code=the-code&state=known-state")
        assert status == 200 and "close this tab" in body
    assert result == ["the-code"]
    assert (await asgi("/oauth/callback", query="code=the-code&state=known-state"))[0] == 400


@pytest.mark.anyio
async def test_oauth_callback_error_fails_the_pending_sign_in_immediately(
    app: Starlette, asgi: AsgiCall
) -> None:
    redirect, callback = app.state.oauth_hook.handlers()
    await redirect("https://idp.invalid/authorize?state=denied-state")
    failures: list[str] = []

    async def wait() -> None:
        try:
            await callback()
        except ConnectFailed as exc:
            failures.append(str(exc))

    with anyio.fail_after(5):
        async with anyio.create_task_group() as tg:
            tg.start_soon(wait)
            await anyio.sleep(0.05)
            status, _, _ = await asgi("/oauth/callback", query="error=access_denied&state=denied-state")
            assert status == 400
    assert len(failures) == 1 and "access_denied" in failures[0]
