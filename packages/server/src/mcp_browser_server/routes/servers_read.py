"""List, get and reveal. Nothing here ever connects or runs anything."""

from __future__ import annotations

from mcp_browser_core.secrets import mask_entry
from starlette.requests import Request
from starlette.responses import Response

from ..api_models import ServerDetail, ServersResponse
from ..deps import catalog, discovery, find_entry, respond, safe_catalog


async def list_servers(request: Request) -> Response:
    found = await discovery(request)
    return respond(
        ServersResponse(
            entries=[mask_entry(e) for e in found.entries],
            catalog=await safe_catalog(request, catalog(request).all()),
            warnings=found.warnings,
        )
    )


async def get_server(request: Request) -> Response:
    entry = await find_entry(request, request.path_params["id"])
    cached = [c for c in catalog(request).all() if c.entry_id == entry.id]
    shown = (await safe_catalog(request, cached))[:1]
    return respond(ServerDetail(entry=mask_entry(entry), catalog=shown[0] if shown else None))


async def reveal_server(request: Request) -> Response:
    """The only route that returns real env, header and URL values."""
    return respond(await find_entry(request, request.path_params["id"]))
