"""Client spec dataclasses. A new client is one `ClientSpec` row plus (rarely) a dialect."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..models import Capabilities, Format, Scope

ALL_PLATFORMS: tuple[str, ...] = ("darwin", "win32", "linux")


@dataclass(frozen=True)
class PathRule:
    """A path template. Tokens: {home} {appdata} {localappdata} {xdg_config} {claude_dir}
    {claude_json_dir} {claude_desktop_dir} {codex_home} {code_user} {project}. Globs allowed."""

    template: str
    platforms: tuple[str, ...] = ALL_PLATFORMS
    scope: Scope = "user"


@dataclass(frozen=True)
class ClientSpec:
    id: str
    display_name: str
    dialect: str
    format: Format
    user_paths: tuple[PathRule, ...]
    project_paths: tuple[str, ...]  # project-relative, e.g. ".cursor/mcp.json"
    root_key: str  # "mcpServers" | "servers" | "context_servers" | "mcp_servers"
    capabilities: Capabilities
    needs_restart: bool = False
    editable: bool = True
    read_only_reason: str | None = None
    dedicated_file: bool = True  # False for Zed: the file is the whole editor settings
    local_projects_key: str | None = None  # "projects" for Claude Code (local scope in .claude.json)
    type_style: Literal["none", "std", "cline"] = "none"  # mcpservers_json `type` writing
    url_key: Literal["url", "serverUrl"] = "url"  # mcpservers_json url field name
    stdio_cwd: bool = True  # False when the client has no working-directory field (Zed)
