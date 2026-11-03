"""Add, update, delete. Every write rediscovers afterwards so the cache never goes stale."""

from __future__ import annotations

from mcp_browser_core import mutate
from mcp_browser_core.errors import InvalidArguments
from mcp_browser_core.secrets import contains_mask
from starlette.requests import Request
from starlette.responses import Response

from ..api_models import AddRequest, UpdateRequest
from ..deps import blocking, catalog, discovery, read_model, respond, settings
from ..redact import mask_report, mask_result

MASKED = "a masked value cannot be saved; enter the real value"


async def add_server(request: Request) -> Response:
    req = await read_model(request, AddRequest)
    if contains_mask(req):
        raise InvalidArguments(MASKED)
    results = await blocking(
        mutate.add,
        req.to_new_entry(),
        req.targets,
        paths=settings(request).paths,
        allow_comment_loss=req.allow_comment_loss,
    )
    await discovery(request, refresh=True)
    return respond([mask_result(r) for r in results])


async def update_server(request: Request) -> Response:
    """`name` renames in the same write; a supplied `extra` replaces the whole object."""
    entry_id = request.path_params["id"]
    req = await read_model(request, UpdateRequest)
    if contains_mask(req):
        raise InvalidArguments(MASKED)
    report = await blocking(
        mutate.update,
        entry_id,
        req.to_patch(),
        paths=settings(request).paths,
        allow_comment_loss=req.allow_comment_loss,
    )
    catalog(request).drop(entry_id)
    await discovery(request, refresh=True)
    return respond(mask_report(report))


async def delete_server(request: Request) -> Response:
    entry_id = request.path_params["id"]
    allow = request.query_params.get("allow_comment_loss", "").lower() in ("1", "true")
    report = await blocking(mutate.delete, entry_id, paths=settings(request).paths, allow_comment_loss=allow)
    catalog(request).drop(entry_id)
    await discovery(request, refresh=True)
    return respond(mask_report(report))
