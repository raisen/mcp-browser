"""Typed access to app state, discovery cache, request parsing and response helpers."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar, cast

import anyio
import anyio.to_thread
from mcp_browser_core.catalog import Catalog
from mcp_browser_core.catalog_models import CatalogEntry
from mcp_browser_core.connect import ConnectOptions
from mcp_browser_core.discovery import discover
from mcp_browser_core.errors import ConfirmationRequired, InvalidArguments, NotFound
from mcp_browser_core.models import DiscoveryResult, HttpTransport, ServerEntry, SseTransport
from mcp_browser_core.oauth import OAuthHook
from mcp_browser_core.trust import confirmation_detail
from pydantic import BaseModel, ValidationError
from pydantic_core import to_jsonable_python
from starlette.requests import Request
from starlette.responses import JSONResponse

from .error_handlers import io_failure, validation_error
from .redact import scrub_catalog
from .settings import ServerSettings

M = TypeVar("M", bound=BaseModel)
T = TypeVar("T")
OAUTH_CONNECT_TIMEOUT = 360.0  # the browser sign-in happens inside the connect deadline
MAX_TIMEOUT = 3600.0


def settings(request: Request) -> ServerSettings:
    return cast("ServerSettings", request.app.state.settings)


def catalog(request: Request) -> Catalog:
    return cast("Catalog", request.app.state.catalog)


def oauth_hook(request: Request) -> OAuthHook:
    return cast("OAuthHook", request.app.state.oauth_hook)


def limiter(request: Request) -> anyio.CapacityLimiter:
    return cast("anyio.CapacityLimiter", request.app.state.limiter)


async def blocking(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run blocking file work off the event loop; I/O failures become a clean `io_error`."""
    try:
        return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs))
    except OSError as exc:
        raise io_failure(exc) from None


async def discovery(request: Request, refresh: bool = False) -> DiscoveryResult:
    """Cached discovery; recomputed on `refresh`, `?refresh=1` and after every write."""
    state = request.app.state
    if refresh or request.query_params.get("refresh") == "1" or state.discovery_cache is None:
        state.discovery_cache = await blocking(discover, settings(request).paths)
    return cast("DiscoveryResult", state.discovery_cache)


async def find_entry(request: Request, entry_id: str) -> ServerEntry:
    for refresh in (False, True):
        found = next((e for e in (await discovery(request, refresh)).entries if e.id == entry_id), None)
        if found is not None:
            return found
    raise NotFound(f"no server entry with id {entry_id!r}")


async def read_model(request: Request, model: type[M], *, empty_ok: bool = False) -> M:
    raw = await request.body()
    if not raw.strip() and empty_ok:
        return model()
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise validation_error(exc) from None


def respond(payload: object, status: int = 200) -> JSONResponse:
    return JSONResponse(to_jsonable_python(payload), status)


async def safe_catalog(request: Request, items: list[CatalogEntry]) -> list[CatalogEntry]:
    by_id = {e.id: e for e in (await discovery(request)).entries}
    return [scrub_catalog(c, by_id.get(c.entry_id)) for c in items]


def _timeout(value: float | None, default: float) -> float:
    if value is None:
        return default
    if not 0 < value <= MAX_TIMEOUT:
        raise InvalidArguments(f"a timeout must be between 0 and {MAX_TIMEOUT:g} seconds")
    return value


def may_need_oauth(entry: ServerEntry) -> bool:
    t = entry.transport
    if not isinstance(t, (HttpTransport, SseTransport)):
        return False
    has_auth = any(k.lower() == "authorization" for k in t.headers) or "bearer_token_env_var" in entry.extra
    return not has_auth


def options(
    request: Request, entry: ServerEntry, connect: float | None = None, call: float | None = None
) -> ConnectOptions:
    """stdio keeps the short connect deadline; a server that may need OAuth gets time for sign-in."""
    s = settings(request)
    default = max(s.connect_timeout, OAUTH_CONNECT_TIMEOUT) if may_need_oauth(entry) else s.connect_timeout
    return ConnectOptions(_timeout(connect, default), _timeout(call, s.call_timeout))


def require_confirmation(entries: list[ServerEntry], confirmed: bool) -> None:
    """409 `confirmation_required` for repo-provided (untrusted) entries unless this very request
    says `confirm_untrusted: true`. Nothing is remembered between requests."""
    risky = [e for e in entries if e.untrusted]
    if confirmed or not risky:
        return
    details = [confirmation_detail(e) for e in risky]
    raise ConfirmationRequired(
        "this server comes from a project config file; confirm before it runs or is contacted",
        **details[0],
        entries=details,
    )
