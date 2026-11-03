"""healthz, clients, projects and the OAuth callback."""

from __future__ import annotations

import html
import os

from mcp_browser_core import __version__
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from ..api_models import HealthResponse
from ..deps import discovery, oauth_hook, respond

PAGE = (
    '<!doctype html><html lang="en"><meta charset="utf-8"><title>mcp-browser</title>'
    '<body style="font-family:system-ui;max-width:32rem;margin:4rem auto"><h1>{title}</h1><p>{text}</p>'
)


def page(title: str, text: str, status: int) -> HTMLResponse:
    return HTMLResponse(PAGE.format(title=html.escape(title), text=html.escape(text)), status)


async def healthz(_request: Request) -> Response:
    return respond(HealthResponse(version=__version__, pid=os.getpid()))


async def clients(request: Request) -> Response:
    return respond((await discovery(request)).clients)


async def projects(request: Request) -> Response:
    return respond((await discovery(request)).projects)


async def oauth_callback(request: Request) -> Response:
    """Token-free by design: the identity provider's redirect cannot carry our bearer token.
    It only completes a sign-in this process started (unknown `state` is rejected).
    Runs on the event loop of the pending session, which `OAuthHook.complete` requires."""
    q = request.query_params
    if q.get("error"):
        shown = f"{q.get('error')}: {q.get('error_description', '')}"[:300]
        if state := q.get("state"):
            oauth_hook(request).fail(state, shown)
        return page("Sign-in failed", shown, 400)
    code, state = q.get("code"), q.get("state")
    if not code or not state or not oauth_hook(request).complete(code, state, q.get("iss")):
        return page("Sign-in not recognised", "Unknown or expired sign-in request. Start it again.", 400)
    return page("Signed in", "You can close this tab and return to mcp-browser.", 200)
