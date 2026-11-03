"""OAuth wiring for HTTP/SSE servers: file token storage and the browser-callback hook."""

from __future__ import annotations

import json
import os
import tempfile
import webbrowser
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import anyio
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.shared.auth import (
    AuthorizationCodeResult,
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)
from pydantic import AnyUrl

from .errors import AuthRequired, ConnectFailed, OperationTimeout


class FileTokenStorage:
    """Implements `mcp.client.auth.TokenStorage` over a 0600 JSON file (tokens + client info)."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return cast("dict[str, Any]", data) if isinstance(data, dict) else {}

    def _write(self, key: str, value: dict[str, Any]) -> None:
        data = self._read()
        data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".oauth-")  # created 0600
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, self.path)

    async def get_tokens(self) -> OAuthToken | None:
        raw = self._read().get("tokens")
        return OAuthToken.model_validate(raw) if isinstance(raw, dict) else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._write("tokens", tokens.model_dump(mode="json", exclude_none=True))

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = self._read().get("client_info")
        return OAuthClientInformationFull.model_validate(raw) if isinstance(raw, dict) else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._write("client_info", client_info.model_dump(mode="json", exclude_none=True))


class OAuthHook:
    """Bridges the SDK's redirect/callback handlers and the server's `/oauth/callback` route.

    The SDK generates `state` itself and only exposes it inside the authorization URL passed to the
    redirect handler, so `handlers()` returns closures sharing one pending slot: the redirect handler
    parses `state` from the URL, registers an `anyio.Event` for it and opens the browser; the callback
    handler (no arguments) awaits that event and returns the `AuthorizationCodeResult`.
    """

    def __init__(
        self,
        redirect_uri: str,
        open_browser: Callable[[str], bool] = webbrowser.open,
        wait_timeout: float = 300.0,
    ) -> None:
        self.redirect_uri = redirect_uri
        self.open_browser = open_browser
        self.wait_timeout = wait_timeout
        self._pending: dict[str, tuple[anyio.Event, list[AuthorizationCodeResult | str]]] = {}

    def handlers(
        self,
    ) -> tuple[Callable[[str], Awaitable[None]], Callable[[], Awaitable[AuthorizationCodeResult]]]:
        slot: list[str] = []  # state of this closure pair's latest authorization request

        async def redirect(url: str) -> None:
            state = (parse_qs(urlparse(url).query).get("state") or [""])[0]
            if not state:
                raise ValueError("authorization URL carries no state")
            self._pending[state] = (anyio.Event(), [])
            slot[:] = [state]
            self.open_browser(url)

        async def callback() -> AuthorizationCodeResult:
            if not slot:
                raise RuntimeError("callback awaited before the redirect handler ran")
            state = slot[0]
            event, result = self._pending[state]
            try:
                with anyio.fail_after(self.wait_timeout):
                    await event.wait()
            except TimeoutError as exc:
                raise OperationTimeout("OAuth authorization was not completed in time") from exc
            finally:
                self._pending.pop(state, None)
            outcome = result[0]
            if isinstance(outcome, str):
                raise ConnectFailed(f"Sign-in was refused by the identity provider: {outcome}")
            return outcome

        return redirect, callback

    def complete(self, code: str, state: str, iss: str | None = None) -> bool:
        """Called by the server route. False (-> HTTP 400) when `state` is unknown."""
        pending = self._pending.get(state)
        if pending is None or pending[0].is_set():
            return False
        pending[1].append(AuthorizationCodeResult(code=code, state=state, iss=iss))
        pending[0].set()
        return True

    def fail(self, state: str, reason: str) -> bool:
        """Called by the server route when the identity provider answers with `error`: the pending wait
        raises `ConnectFailed` at once instead of timing out. False when `state` is unknown."""
        pending = self._pending.get(state)
        if pending is None or pending[0].is_set():
            return False
        pending[1].append(reason[:300])
        pending[0].set()
        return True


class NoBrowserHook(OAuthHook):
    """Never opens a browser: any sign-in the server asks for raises `AuthRequired` (used by scans)."""

    REDIRECT = "http://127.0.0.1:8765/oauth/callback"

    def handlers(
        self,
    ) -> tuple[Callable[[str], Awaitable[None]], Callable[[], Awaitable[AuthorizationCodeResult]]]:
        async def redirect(_url: str) -> None:
            raise AuthRequired("sign-in required")

        async def callback() -> AuthorizationCodeResult:
            raise AuthRequired("sign-in required")

        return redirect, callback


def make_provider(
    server_url: str,
    hook: OAuthHook,
    storage: TokenStorage,
    *,
    scope: str | None = None,
    client_name: str = "mcp-browser",
) -> OAuthClientProvider:
    """An SDK provider (an `httpx2.Auth`) whose browser round trip goes through `hook`."""
    metadata = OAuthClientMetadata(
        redirect_uris=[AnyUrl(hook.redirect_uri)], client_name=client_name, scope=scope
    )
    redirect, callback = hook.handlers()
    return OAuthClientProvider(
        server_url,
        metadata,
        storage,
        redirect_handler=redirect,
        callback_handler=callback,
    )
