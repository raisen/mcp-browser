"""Routes that start a server or contact a URL. Each holds a slot of the shared limiter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import anyio
import jsonschema
from jsonschema.validators import validator_for
from mcp_browser_core.catalog import Catalog
from mcp_browser_core.catalog_models import CatalogEntry, ToolInfo
from mcp_browser_core.connect import session
from mcp_browser_core.errors import InvalidArguments, McpBrowserError, NotFound
from mcp_browser_core.models import ServerEntry, StdioTransport, fingerprint
from starlette.requests import Request
from starlette.responses import Response

from ..api_models import CallRequest, ConnectRequest, GetPromptRequest, ReadResourceRequest, ScanRequest
from ..deps import (
    catalog,
    discovery,
    find_entry,
    limiter,
    oauth_hook,
    options,
    read_model,
    require_confirmation,
    respond,
    safe_catalog,
    settings,
)
from ..redact import scrub, scrub_catalog


def _open(request: Request, entry: ServerEntry, **timeouts: float | None) -> Any:
    return session(
        entry,
        settings(request).paths,
        options(request, entry, **timeouts),
        oauth_hook(request),
        limiter=limiter(request),
    )


def _clean(exc: McpBrowserError, entry: ServerEntry) -> McpBrowserError:
    """Remove the entry's own secrets from an error before it is sent to the browser."""
    exc.message = scrub(exc.message, entry) or exc.message
    if isinstance(exc.detail.get("stderr_tail"), str):
        exc.detail["stderr_tail"] = scrub(exc.detail["stderr_tail"], entry)
    return exc


async def connect_server(request: Request) -> Response:
    entry = await find_entry(request, request.path_params["id"])
    req = await read_model(request, ConnectRequest, empty_ok=True)
    require_confirmation([entry], req.confirm_untrusted)
    started = datetime.now(UTC)
    try:
        async with _open(request, entry, connect=req.connect_timeout) as s:
            item = CatalogEntry(
                entry_id=entry.id,
                fingerprint=fingerprint(entry.transport),
                scanned_at=started,
                status="ok",
                tools=await s.list_tools(),
                resources=await s.list_resources(),
                prompts=await s.list_prompts(),
                stderr_tail=s.stderr_tail or None,
            )
    except McpBrowserError as exc:
        raise _clean(exc, entry) from None
    catalog(request).put(item)
    return respond(scrub_catalog(item, entry))


async def scan_servers(request: Request) -> Response:
    """Explicit request only. Without ids: every usable entry except untrusted (project) ones, whose
    count comes back in the `X-Skipped-Untrusted` header. Listed untrusted ids need `confirm_untrusted`."""
    req = await read_model(request, ScanRequest, empty_ok=True)
    found = (await discovery(request)).entries
    wanted = None if req.ids is None else set(req.ids)
    chosen = [e for e in found if e.transport is not None and (wanted is None or e.id in wanted)]
    skipped = 0
    if wanted is None:
        skipped = sum(e.untrusted for e in chosen)
        chosen = [e for e in chosen if not e.untrusted]
    else:
        require_confirmation(chosen, req.confirm_untrusted)
    cat: Catalog = catalog(request)
    stdio = [e for e in chosen if isinstance(e.transport, StdioTransport)]
    remote = [e for e in chosen if e not in stdio]
    done: list[CatalogEntry] = []

    async def run(entries: list[ServerEntry]) -> None:
        if not entries:
            return
        # remote servers get the long deadline so a browser sign-in can finish
        opts = options(request, entries[0])
        done.extend(
            await cat.scan(
                entries, settings(request).paths, opts, limiter=limiter(request), oauth=oauth_hook(request)
            )
        )

    async with anyio.create_task_group() as tg:
        tg.start_soon(run, stdio)
        for entry in remote:
            tg.start_soon(run, [entry])
    response = respond(await safe_catalog(request, done))
    response.headers["X-Skipped-Untrusted"] = str(skipped)
    return response


def validate(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
    """JSON Schema (draft 2020-12 by default) check; a broken schema is not the caller's fault."""
    cls = validator_for(schema, default=jsonschema.Draft202012Validator)
    try:
        cls.check_schema(schema)
    except jsonschema.SchemaError:
        return
    errors = [
        {"path": "/" + "/".join(str(p) for p in e.absolute_path), "message": e.message}
        for e in cls(schema).iter_errors(arguments)
    ]
    if errors:
        raise InvalidArguments("the arguments do not match the tool's input schema", errors=errors)


def _cached_tool(request: Request, entry: ServerEntry, name: str) -> ToolInfo | None:
    cached = catalog(request).get(entry.id, fingerprint(entry.transport))
    return next((t for t in cached.tools if t.name == name), None) if cached else None


async def call_tool(request: Request) -> Response:
    entry = await find_entry(request, request.path_params["id"])
    name = request.path_params["tool"]
    req = await read_model(request, CallRequest, empty_ok=True)
    require_confirmation([entry], req.confirm_untrusted)
    known = _cached_tool(request, entry, name)
    if known is not None:
        validate(known.input_schema, req.arguments)  # rejected before anything is started
    try:
        async with _open(request, entry, call=req.call_timeout) as s:
            if known is None:
                known = next((t for t in await s.list_tools() if t.name == name), None)
                if known is None:
                    raise NotFound(f"the server has no tool named {name!r}")
                validate(known.input_schema, req.arguments)
            result = await s.call_tool(
                name, req.arguments, req.call_timeout or settings(request).call_timeout
            )
    except McpBrowserError as exc:
        raise _clean(exc, entry) from None
    result.stderr_tail = scrub(result.stderr_tail, entry)
    return respond(result)


async def read_resource(request: Request) -> Response:
    entry = await find_entry(request, request.path_params["id"])
    req = await read_model(request, ReadResourceRequest)
    require_confirmation([entry], req.confirm_untrusted)
    try:
        async with _open(request, entry) as s:
            return respond(await s.read_resource(req.uri))
    except McpBrowserError as exc:
        raise _clean(exc, entry) from None


async def get_prompt(request: Request) -> Response:
    entry = await find_entry(request, request.path_params["id"])
    req = await read_model(request, GetPromptRequest, empty_ok=True)
    require_confirmation([entry], req.confirm_untrusted)
    try:
        async with _open(request, entry) as s:
            return respond(await s.get_prompt(request.path_params["name"], req.arguments))
    except McpBrowserError as exc:
        raise _clean(exc, entry) from None
