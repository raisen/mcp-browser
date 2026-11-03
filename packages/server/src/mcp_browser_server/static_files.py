"""Static UI files read through importlib.resources, with explicit content types.

Types are set here rather than guessed: on Windows the registry can map .js to text/plain,
which breaks ES modules."""

from __future__ import annotations

from importlib.resources import files
from importlib.resources.abc import Traversable

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


def _root() -> Traversable:
    return files("mcp_browser_server") / "static"


def serve(relative: str) -> Response:
    """`relative` uses forward slashes; anything that could leave the static tree is a 404."""
    parts = relative.split("/")
    if any(p in ("", ".", "..") or "\\" in p or ":" in p or "\x00" in p for p in parts):
        raise HTTPException(404)
    node = _root()
    for part in parts:
        node = node / part
    if not node.is_file():
        raise HTTPException(404)
    suffix = "." + relative.rsplit(".", 1)[-1].lower() if "." in parts[-1] else ""
    media = TYPES.get(suffix, "application/octet-stream")
    return Response(node.read_bytes(), media_type=media, headers={"Cache-Control": "no-cache"})


async def index(_request: Request) -> Response:
    return serve("index.html")


async def static(request: Request) -> Response:
    return serve(str(request.path_params["path"]))
