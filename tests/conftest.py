"""Shared fixtures: every test runs against an isolated HOME and state dir under tmp_path."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from mcp_browser_core.models import Platform
from mcp_browser_core.paths import Paths, current_platform

ENV_KEYS = (
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "CLAUDE_CONFIG_DIR",
    "CODEX_HOME",
    "MCP_BROWSER_STATE_DIR",
)


def build_environ(root: Path) -> dict[str, str]:
    """A self-contained environment rooted at `root`; callers add per-test keys on top."""
    home = root / "home"
    home.mkdir(parents=True, exist_ok=True)
    return {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APPDATA": str(home / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_STATE_HOME": str(home / ".local" / "state"),
        "MCP_BROWSER_STATE_DIR": str(root / "state"),
    }


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Paths:
    """Point every relevant variable at tmp_path and yield `Paths` built from that environment."""
    environ = build_environ(tmp_path)
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in environ.items():
        monkeypatch.setenv(key, value)
    return Paths(environ, current_platform(), tmp_path)


@pytest.fixture
def paths(isolated_env: Paths) -> Paths:
    return isolated_env


@pytest.fixture
def paths_for(tmp_path: Path) -> Callable[[Platform], Paths]:
    """Factory simulating darwin, win32 or linux on any host OS (separate root per platform)."""

    def factory(platform: Platform) -> Paths:
        root = tmp_path / f"sim-{platform}"
        return Paths(build_environ(root), platform, root)

    return factory
