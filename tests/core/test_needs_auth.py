"""A scan never opens a browser: a server that wants sign-in is recorded as `needs_auth`."""

from __future__ import annotations

import json
import threading
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import anyio
import pytest
from mcp_browser_core.catalog import scan_one
from mcp_browser_core.connect import ConnectOptions
from mcp_browser_core.models import HttpTransport, ServerEntry
from mcp_browser_core.oauth import OAuthHook
from mcp_browser_core.paths import Paths


@contextmanager
def oauth_server() -> Generator[str]:
    PORT: list[int] = []

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> None:
            raw = json.dumps(body).encode()
            self.send_response(status)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _handle(self) -> None:
            base = f"http://127.0.0.1:{PORT[0]}"
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            if self.path == "/mcp":
                meta = f'Bearer resource_metadata="{base}/.well-known/oauth-protected-resource/mcp"'
                self._send(401, {}, {"WWW-Authenticate": meta})
            elif self.path.startswith("/.well-known/oauth-protected-resource"):
                self._send(200, {"resource": f"{base}/mcp", "authorization_servers": [base]})
            elif self.path.startswith("/.well-known/"):
                self._send(
                    200,
                    {
                        "issuer": base,
                        "authorization_endpoint": f"{base}/authorize",
                        "token_endpoint": f"{base}/token",
                        "registration_endpoint": f"{base}/register",
                        "response_types_supported": ["code"],
                        "code_challenge_methods_supported": ["S256"],
                    },
                )
            elif self.path == "/register":
                self._send(201, {"client_id": "cid", "redirect_uris": json.loads(body)["redirect_uris"]})
            else:
                self._send(404, {})

        do_GET = do_POST = _handle

        def log_message(self, format: str, *args: Any) -> None:
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    PORT.append(httpd.server_address[1])
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{PORT[0]}/mcp"
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.mark.anyio
async def test_scan_records_needs_auth_and_never_opens_a_browser(
    paths: Paths, caplog: pytest.LogCaptureFixture
) -> None:
    opened: list[str] = []
    hook = OAuthHook("http://127.0.0.1:8765/oauth/callback", open_browser=lambda u: opened.append(u) or True)
    with oauth_server() as url:
        entry = ServerEntry(
            id="o",
            name="o",
            client_id="x",
            scope="user",
            config_path="/x",
            transport=HttpTransport(url=url),
        )
        opts = ConnectOptions(connect_timeout=15, call_timeout=15)
        with anyio.fail_after(30):
            found = await scan_one(entry, paths, opts, anyio.CapacityLimiter(2), hook)
    assert found.status == "needs_auth" and found.error == "sign-in required"
    assert not [r for r in caplog.records if r.exc_info]
    assert opened == []
