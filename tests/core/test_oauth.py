"""OAuth: unit tests for storage and hook, plus a full authorization-code flow against a stub server
(httpx2.MockTransport) driving the real SDK provider. Not covered: a real browser, a real provider's
metadata quirks, token refresh and dynamic-registration failures."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import anyio
import httpx2
import pytest
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientInformationFull, OAuthToken
from mcp_browser_core.errors import ConnectFailed, OperationTimeout
from mcp_browser_core.oauth import FileTokenStorage, OAuthHook, make_provider

CALLBACK = "http://127.0.0.1:8765/oauth/callback"
BASE = "http://as.test"


@pytest.mark.anyio
async def test_storage_round_trip_with_private_mode(tmp_path: Path) -> None:
    storage = FileTokenStorage(tmp_path / "oauth" / "s.json")
    assert await storage.get_tokens() is None and await storage.get_client_info() is None
    await storage.set_tokens(OAuthToken(access_token="at", token_type="Bearer", refresh_token="rt"))
    info = OAuthClientInformationFull.model_validate({"client_id": "cid", "redirect_uris": [CALLBACK]})
    await storage.set_client_info(info)
    again = FileTokenStorage(storage.path)
    tokens = await again.get_tokens()
    assert tokens is not None and tokens.access_token == "at" and tokens.refresh_token == "rt"
    client = await again.get_client_info()
    assert client is not None and client.client_id == "cid"
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(storage.path).st_mode) == 0o600
    (tmp_path / "oauth" / "s.json").write_text("not json")
    assert await again.get_tokens() is None


@pytest.mark.anyio
async def test_hook_redirect_callback_complete() -> None:
    opened: list[str] = []
    hook = OAuthHook(CALLBACK, open_browser=lambda url: opened.append(url) or True)
    redirect, callback = hook.handlers()
    await redirect(f"{BASE}/authorize?client_id=c&state=st-1")
    assert opened and "state=st-1" in opened[0]
    results: list[AuthorizationCodeResult] = []

    async def waiter() -> None:
        results.append(await callback())

    async with anyio.create_task_group() as tg:
        tg.start_soon(waiter)
        await anyio.sleep(0.05)
        assert hook.complete("code-9", "unknown") is False
        assert hook.complete("code-9", "st-1", "iss") is True
        assert hook.complete("again", "st-1") is False
    assert (results[0].code, results[0].state, results[0].iss) == ("code-9", "st-1", "iss")


@pytest.mark.anyio
async def test_callback_times_out_and_forgets_state() -> None:
    hook = OAuthHook(CALLBACK, open_browser=lambda _u: True, wait_timeout=0.1)
    redirect, callback = hook.handlers()
    await redirect(f"{BASE}/authorize?state=s2")
    with pytest.raises(OperationTimeout):
        await callback()
    assert hook.complete("c", "s2") is False


@pytest.mark.anyio
async def test_fail_ends_the_pending_wait_at_once() -> None:
    hook = OAuthHook(CALLBACK, open_browser=lambda _u: True, wait_timeout=30)
    redirect, callback = hook.handlers()
    await redirect(f"{BASE}/authorize?state=s3")
    assert hook.fail("nope", "x") is False
    outcome: list[BaseException] = []

    async def wait() -> None:
        try:
            await callback()
        except ConnectFailed as exc:
            outcome.append(exc)

    with anyio.fail_after(5):
        async with anyio.create_task_group() as tg:
            tg.start_soon(wait)
            await anyio.sleep(0.05)
            assert hook.fail("s3", "access_denied: user said no") is True
    assert len(outcome) == 1 and "access_denied" in str(outcome[0])
    assert hook.fail("s3", "again") is False and hook.complete("c", "s3") is False


def stub_server(seen: list[str]) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        seen.append(f"{request.method} {path}")
        if path == "/mcp":
            if request.headers.get("authorization") == "Bearer at-1":
                return httpx2.Response(200, json={"ok": True})
            header = f'Bearer resource_metadata="{BASE}/.well-known/oauth-protected-resource/mcp"'
            return httpx2.Response(401, headers={"WWW-Authenticate": header})
        if path.startswith("/.well-known/oauth-protected-resource"):
            return httpx2.Response(200, json={"resource": f"{BASE}/mcp", "authorization_servers": [BASE]})
        if path.startswith("/.well-known/"):
            meta = {
                "issuer": BASE,
                "authorization_endpoint": f"{BASE}/authorize",
                "token_endpoint": f"{BASE}/token",
                "registration_endpoint": f"{BASE}/register",
                "response_types_supported": ["code"],
                "code_challenge_methods_supported": ["S256"],
            }
            return httpx2.Response(200, json=meta)
        if path == "/register":
            body = json.loads(request.content)
            return httpx2.Response(201, json={"client_id": "cid", "redirect_uris": body["redirect_uris"]})
        if path == "/token":
            form = parse_qs(request.content.decode())
            assert form["code"] == ["the-code"] and form["grant_type"] == ["authorization_code"]
            return httpx2.Response(
                200, json={"access_token": "at-1", "token_type": "Bearer", "expires_in": 3600}
            )
        return httpx2.Response(404)

    return httpx2.MockTransport(handler)


@pytest.mark.anyio
async def test_full_flow_against_stub_server(tmp_path: Path) -> None:
    holder: list[OAuthHook] = []
    visited: list[str] = []

    def open_browser(url: str) -> bool:
        parsed = urlparse(url)
        visited.append(parsed.path)
        state = parse_qs(parsed.query)["state"][0]
        assert holder[0].complete("the-code", state)  # what the /oauth/callback route does
        return True

    hook = OAuthHook(CALLBACK, open_browser=open_browser)
    holder.append(hook)
    storage = FileTokenStorage(tmp_path / "tok.json")
    provider = make_provider(f"{BASE}/mcp", hook, storage, scope="read")
    seen: list[str] = []
    with anyio.fail_after(20):
        async with httpx2.AsyncClient(transport=stub_server(seen), auth=provider) as client:
            response = await client.post(f"{BASE}/mcp", json={})
            assert response.status_code == 200
            assert (await client.post(f"{BASE}/mcp", json={})).status_code == 200
    assert visited == ["/authorize"] and "POST /register" in seen and "POST /token" in seen
    tokens = await storage.get_tokens()
    assert tokens is not None and tokens.access_token == "at-1"
