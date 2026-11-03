"""Server configuration. Loopback only: the bind host is a constant, never a setting."""

from __future__ import annotations

from dataclasses import dataclass

from mcp_browser_core.paths import Paths

HOST = "127.0.0.1"


@dataclass(frozen=True)
class ServerSettings:
    paths: Paths
    token: str
    port: int = 8765
    max_concurrency: int = 8
    connect_timeout: float = 30.0
    call_timeout: float = 300.0

    @property
    def allowed_hosts(self) -> frozenset[str]:
        return frozenset({f"{HOST}:{self.port}", f"localhost:{self.port}"})

    @property
    def redirect_uri(self) -> str:
        """OAuth redirect URI handed to `OAuthHook`; core never guesses the port."""
        return f"http://{HOST}:{self.port}/oauth/callback"
