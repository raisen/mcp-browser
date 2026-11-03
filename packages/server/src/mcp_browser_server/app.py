"""Application factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import anyio
from mcp_browser_core.catalog import Catalog
from mcp_browser_core.errors import McpBrowserError
from mcp_browser_core.oauth import OAuthHook
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware

from .auth import SecurityMiddleware
from .error_handlers import CatchAllMiddleware, on_app_error, on_http_error
from .routes import build_routes
from .settings import ServerSettings


def create_app(settings: ServerSettings) -> Starlette:
    """Shared state on `app.state`: settings, paths, catalog, oauth_hook, limiter, discovery_cache."""

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncGenerator[None]:
        app.state.limiter = anyio.CapacityLimiter(settings.max_concurrency)  # needs the running loop
        yield

    app = Starlette(
        routes=build_routes(),
        middleware=[Middleware(SecurityMiddleware, settings=settings), Middleware(CatchAllMiddleware)],
        exception_handlers={McpBrowserError: on_app_error, HTTPException: on_http_error},
        lifespan=lifespan,
    )
    catalog = Catalog(settings.paths.catalog_file)
    catalog.load()
    app.state.settings = settings
    app.state.paths = settings.paths
    app.state.catalog = catalog
    app.state.oauth_hook = OAuthHook(settings.redirect_uri)
    app.state.discovery_cache = None
    return app
