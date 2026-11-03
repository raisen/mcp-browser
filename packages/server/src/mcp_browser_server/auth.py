"""Security middleware: Host check, Origin check, bearer token. Pure ASGI so it runs before routing."""

from __future__ import annotations

import hmac

from mcp_browser_core.errors import McpBrowserError, Unauthorized
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .settings import ServerSettings

CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)
OPEN_PATHS = frozenset({"/healthz", "/oauth/callback", "/"})


class BadHost(McpBrowserError):
    code, status = "bad_host", 400


class BadOrigin(McpBrowserError):
    code, status = "bad_origin", 403


def needs_token(path: str) -> bool:
    """Default deny: only the literal allowlist is token-free; `..` segments never reach /static/."""
    if path in OPEN_PATHS:
        return False
    if path.startswith("/static/"):
        parts = path.split("/")
        return any(p in ("..", ".") for p in parts) or "\\" in path or "%" in path
    return True


def _bearer_ok(header: str | None, token: str) -> bool:
    scheme, _, value = (header or "").partition(" ")
    if scheme.lower() != "bearer" or not value:
        return False
    return hmac.compare_digest(value.strip().encode(), token.encode())


class SecurityMiddleware:
    def __init__(self, app: ASGIApp, settings: ServerSettings) -> None:
        self.app = app
        self.token = settings.token
        self.hosts = frozenset(h.lower() for h in settings.allowed_hosts)
        self.origins = frozenset(f"{scheme}://{h}" for h in self.hosts for scheme in ("http", "https"))

    def _check(self, scope: Scope) -> McpBrowserError | None:
        headers = Headers(scope=scope)
        hosts = headers.getlist("host")
        if len(hosts) != 1 or hosts[0].lower() not in self.hosts:
            return BadHost("unexpected Host header")
        origin = headers.get("origin")
        if origin is not None and origin.lower() not in self.origins:
            return BadOrigin("unexpected Origin header")
        if needs_token(scope["path"]) and not _bearer_ok(headers.get("authorization"), self.token):
            return Unauthorized("missing or wrong token")
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":  # no websocket endpoints exist
            await send({"type": "websocket.close", "code": 1008})
            return
        error = self._check(scope)

        async def send_safe(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Content-Security-Policy"] = CSP
                if "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        if error is not None:
            extra = {"WWW-Authenticate": "Bearer"} if error.status == 401 else None
            response = JSONResponse(error.to_body(), error.status, headers=extra)
            await response(scope, receive, send_safe)
            return
        await self.app(scope, receive, send_safe)
