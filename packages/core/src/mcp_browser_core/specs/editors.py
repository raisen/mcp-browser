"""Cursor, VS Code, Windsurf, Zed and Cline."""

from __future__ import annotations

from ..models import Capabilities
from .base import ClientSpec, PathRule

CURSOR = ClientSpec(
    id="cursor",
    display_name="Cursor",
    dialect="mcpservers_json",
    format="jsonc",
    user_paths=(PathRule("{home}/.cursor/mcp.json"),),
    project_paths=(".cursor/mcp.json",),
    root_key="mcpServers",
    capabilities=Capabilities(project_scope=True),
    type_style="std",
)

VSCODE = ClientSpec(
    id="vscode",
    display_name="VS Code",
    dialect="vscode",
    format="jsonc",
    user_paths=(PathRule("{code_user}/mcp.json"),),
    project_paths=(".vscode/mcp.json",),
    root_key="servers",
    capabilities=Capabilities(project_scope=True),
)

WINDSURF = ClientSpec(
    id="windsurf",
    display_name="Windsurf",
    dialect="mcpservers_json",
    format="json",
    user_paths=(PathRule("{home}/.codeium/windsurf/mcp_config.json"),),
    project_paths=(),
    root_key="mcpServers",
    capabilities=Capabilities(sse=False, project_scope=False),
    url_key="serverUrl",
)

ZED = ClientSpec(
    id="zed",
    display_name="Zed",
    dialect="zed",
    format="jsonc",
    user_paths=(
        PathRule("{home}/.config/zed/settings.json", platforms=("darwin", "linux")),
        PathRule("{appdata}/Zed/settings.json", platforms=("win32",)),
    ),
    project_paths=(".zed/settings.json",),
    root_key="context_servers",
    capabilities=Capabilities(sse=False, project_scope=True),
    dedicated_file=False,
    stdio_cwd=False,
)

CLINE = ClientSpec(
    id="cline",
    display_name="Cline",
    dialect="mcpservers_json",
    format="json",
    user_paths=(
        PathRule("{code_user}/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json"),
        PathRule("{home}/.cline/data/settings/cline_mcp_settings.json"),
    ),
    project_paths=(),
    root_key="mcpServers",
    capabilities=Capabilities(project_scope=False),
    type_style="cline",
)

SPECS = (CURSOR, VSCODE, WINDSURF, ZED, CLINE)
