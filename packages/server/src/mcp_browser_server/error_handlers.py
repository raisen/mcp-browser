"""Error body shape for every failure; nothing internal ever reaches a client or a log."""

from __future__ import annotations

import logging
from typing import Any

from mcp_browser_core.errors import InvalidArguments, McpBrowserError
from pydantic import ValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("mcp_browser_server")


class IoFailure(McpBrowserError):
    code, status = "io_error", 500


def error_response(exc: McpBrowserError) -> JSONResponse:
    return JSONResponse(exc.to_body(), exc.status)


def validation_error(exc: ValidationError) -> McpBrowserError:
    """Field paths and messages only: pydantic's `input` would echo submitted secrets."""
    errors = [
        {"path": "/".join(str(p) for p in e["loc"]), "message": e["msg"], "type": e["type"]}
        for e in exc.errors(include_input=False, include_url=False, include_context=False)
    ]
    return InvalidArguments("the request body is not valid", errors=errors)


def io_failure(exc: OSError) -> IoFailure:
    return IoFailure(f"could not read or write the config file: {exc.strerror or type(exc).__name__}")


async def on_app_error(_request: Request, exc: Exception) -> Response:
    assert isinstance(exc, McpBrowserError)
    return error_response(exc)


async def on_http_error(_request: Request, exc: Exception) -> Response:
    assert isinstance(exc, HTTPException)
    code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
    body: dict[str, Any] = {
        "error": code,
        "message": "no such resource" if exc.status_code == 404 else code,
        "detail": {},
    }
    return JSONResponse(body, exc.status_code)


class CatchAllMiddleware:
    """Turns any unexpected exception into the error body. Logs the exception type only."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def watch(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, watch)
        except Exception as exc:
            log.error("unhandled %s on %s %s", type(exc).__name__, scope["method"], scope["path"])
            if started:
                return
            body: dict[str, Any] = {"error": "internal_error", "message": "internal error", "detail": {}}
            await JSONResponse(body, 500)(scope, receive, send)
