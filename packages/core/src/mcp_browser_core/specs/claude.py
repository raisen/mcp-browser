"""Claude Code, Claude Desktop, and the read-only plugin and extension sources."""

from __future__ import annotations

from ..models import Capabilities
from .base import ClientSpec, PathRule

CLAUDE_CODE = ClientSpec(
    id="claude-code",
    display_name="Claude Code",
    dialect="mcpservers_json",
    format="json",
    user_paths=(PathRule("{claude_json_dir}/.claude.json"),),
    project_paths=(".mcp.json",),
    root_key="mcpServers",
    capabilities=Capabilities(project_scope=True),
    local_projects_key="projects",
    type_style="std",
)

CLAUDE_DESKTOP = ClientSpec(
    id="claude-desktop",
    display_name="Claude Desktop",
    dialect="mcpservers_json",
    format="json",
    user_paths=(PathRule("{claude_desktop_dir}/claude_desktop_config.json"),),
    project_paths=(),
    root_key="mcpServers",
    capabilities=Capabilities(http=False, sse=False, project_scope=False),
    needs_restart=True,
)

CLAUDE_PLUGINS = ClientSpec(
    id="claude-code-plugins",
    display_name="Claude Code plugins",
    dialect="readonly",
    format="json",
    user_paths=(PathRule("{claude_dir}/plugins/installed_plugins.json", scope="plugin"),),
    project_paths=(),
    root_key="",
    capabilities=Capabilities(project_scope=False, editable=False),
    editable=False,
    read_only_reason="installed by plugin; edit the plugin",
)

CLAUDE_EXTENSIONS = ClientSpec(
    id="claude-desktop-ext",
    display_name="Claude Desktop extensions",
    dialect="readonly",
    format="json",
    user_paths=(PathRule("{claude_desktop_dir}/Claude Extensions/*/manifest.json", scope="extension"),),
    project_paths=(),
    root_key="",
    capabilities=Capabilities(project_scope=False, editable=False),
    editable=False,
    read_only_reason="managed by Claude Desktop",
)

SPECS = (CLAUDE_CODE, CLAUDE_DESKTOP, CLAUDE_PLUGINS, CLAUDE_EXTENSIONS)
