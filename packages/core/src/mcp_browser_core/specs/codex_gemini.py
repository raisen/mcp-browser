"""Codex, Gemini CLI and Antigravity."""

from __future__ import annotations

from ..models import Capabilities
from .base import ClientSpec, PathRule

CODEX = ClientSpec(
    id="codex",
    display_name="Codex",
    dialect="codex",
    format="toml",
    user_paths=(PathRule("{codex_home}/config.toml"),),
    project_paths=(".codex/config.toml",),
    root_key="mcp_servers",
    capabilities=Capabilities(sse=False, project_scope=True),
)

GEMINI = ClientSpec(
    id="gemini",
    display_name="Gemini CLI",
    dialect="gemini",
    format="jsonc",  # settings.json may carry comments; the file is shared, so they are never rewritten
    user_paths=(PathRule("{home}/.gemini/settings.json"),),
    project_paths=(".gemini/settings.json",),
    root_key="mcpServers",
    capabilities=Capabilities(project_scope=True),
    dedicated_file=False,
)

ANTIGRAVITY = ClientSpec(
    id="antigravity",
    display_name="Antigravity",
    dialect="mcpservers_json",
    format="json",
    user_paths=(
        PathRule("{home}/.gemini/config/mcp_config.json"),
        PathRule("{home}/.gemini/antigravity/mcp_config.json"),
    ),
    project_paths=(),
    root_key="mcpServers",
    capabilities=Capabilities(sse=False, project_scope=False),
    url_key="serverUrl",
)

SPECS = (CODEX, GEMINI, ANTIGRAVITY)
