"""Route table. `/api/servers/scan` is declared before the `{id}` routes so it can never be read as an id."""

from __future__ import annotations

from starlette.routing import BaseRoute, Route

from .. import static_files
from . import connect, meta, servers_read, servers_write

API = "/api/servers"


def build_routes() -> list[BaseRoute]:
    return [
        Route("/healthz", meta.healthz),
        Route("/oauth/callback", meta.oauth_callback),
        Route("/", static_files.index),
        Route("/static/{path:path}", static_files.static),
        Route("/api/clients", meta.clients),
        Route("/api/projects", meta.projects),
        Route(f"{API}/scan", connect.scan_servers, methods=["POST"]),
        Route(API, servers_read.list_servers),
        Route(API, servers_write.add_server, methods=["POST"]),
        Route(f"{API}/{{id}}", servers_read.get_server),
        Route(f"{API}/{{id}}", servers_write.update_server, methods=["PUT"]),
        Route(f"{API}/{{id}}", servers_write.delete_server, methods=["DELETE"]),
        Route(f"{API}/{{id}}/reveal", servers_read.reveal_server),
        Route(f"{API}/{{id}}/connect", connect.connect_server, methods=["POST"]),
        Route(f"{API}/{{id}}/tools/{{tool}}/call", connect.call_tool, methods=["POST"]),
        Route(f"{API}/{{id}}/resources/read", connect.read_resource, methods=["POST"]),
        Route(f"{API}/{{id}}/prompts/{{name}}", connect.get_prompt, methods=["POST"]),
    ]
