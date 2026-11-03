"""Fixtures for the HTTP API tests: a real app over an isolated HOME, plus a raw ASGI caller."""

from __future__ import annotations

import json
import sys
from collections.abc import Awaitable, Callable, Iterator, MutableMapping
from pathlib import Path
from typing import Any

import pytest
from mcp_browser_core.paths import Paths
from mcp_browser_server.app import create_app
from mcp_browser_server.settings import ServerSettings
from starlette.applications import Starlette
from starlette.testclient import TestClient

TOKEN = "test-token-" + "a1b2c3d4" * 4
PORT = 8765
HOST = f"127.0.0.1:{PORT}"
FIXTURE = str(Path(__file__).parents[1] / "fixtures" / "fixture_server.py")
SECRETS = ("SECRET_ENV_VALUE", "SECRET_HEADER_TOKEN", "SECRET_QUERY_VALUE", "SECRET_ARG_VALUE")

AsgiCall = Callable[..., Awaitable[tuple[int, dict[str, str], str]]]


def write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def cursor_file(paths: Paths) -> Path:
    return paths.home / ".cursor" / "mcp.json"


def fixture_entry(**extra: Any) -> dict[str, Any]:
    return {"command": sys.executable, "args": [FIXTURE], **extra}


@pytest.fixture
def settings(paths: Paths) -> ServerSettings:
    return ServerSettings(paths=paths, token=TOKEN, port=PORT)


@pytest.fixture
def app(settings: ServerSettings) -> Starlette:
    built = create_app(settings)
    built.state.oauth_hook.open_browser = lambda _url: True  # pyright: ignore[reportUnknownLambdaType]  # never open a real browser
    return built


@pytest.fixture
def secret_config(paths: Paths) -> Path:
    return write_json(
        cursor_file(paths),
        {
            "mcpServers": {
                "alpha": {
                    "command": "alpha-cmd",
                    "args": ["--api-key", "SECRET_ARG_VALUE", "run"],
                    "env": {"API_KEY": "SECRET_ENV_VALUE"},
                },
                "beta": {
                    "url": "https://example.invalid/mcp?api_key=SECRET_QUERY_VALUE",
                    "headers": {"Authorization": "Bearer SECRET_HEADER_TOKEN"},
                },
            }
        },
    )


@pytest.fixture
def client(app: Starlette) -> Iterator[TestClient]:
    with TestClient(
        app,
        base_url=f"http://{HOST}",
        headers={"Authorization": f"Bearer {TOKEN}"},
        raise_server_exceptions=False,
    ) as c:
        yield c


@pytest.fixture
def anon(app: Starlette) -> Iterator[TestClient]:
    with TestClient(app, base_url=f"http://{HOST}", raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def asgi(app: Starlette) -> AsgiCall:
    """Call the app with an exact path and exact headers (HTTP clients normalise `..` and Host)."""

    async def call(
        path: str,
        headers: dict[str, str] | None = None,
        *,
        method: str = "GET",
        query: str = "",
        host: str | None = HOST,
    ) -> tuple[int, dict[str, str], str]:
        sent: list[MutableMapping[str, Any]] = []
        raw = {k.lower(): v for k, v in (headers or {}).items()}
        if host is not None:
            raw["host"] = host

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: MutableMapping[str, Any]) -> None:
            sent.append(message)

        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "headers": [(k.encode(), v.encode()) for k, v in raw.items()],
            "server": ("127.0.0.1", PORT),
            "client": ("127.0.0.1", 50000),
        }
        await app(scope, receive, send)
        start = next(m for m in sent if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        out = {k.decode().lower(): v.decode() for k, v in start["headers"]}
        return int(start["status"]), out, body.decode("utf-8", "replace")

    return call


def entry_id(client: TestClient, name: str) -> str:
    entries = client.get("/api/servers", params={"refresh": "1"}).json()["entries"]
    return next(e["id"] for e in entries if e["name"] == name)
