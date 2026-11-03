"""All filesystem location logic. Nothing else in the repo reads HOME, APPDATA or similar."""

from __future__ import annotations

import glob
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from .models import Platform
from .specs.base import PathRule

_GLOB_CHARS = "*?["


def current_platform() -> Platform:
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform == "win32":
        return "win32"
    return "linux"


class Paths:
    """Resolves every location for one (environment, platform) pair, so any OS can be simulated."""

    def __init__(self, environ: Mapping[str, str], platform: Platform, cwd: Path) -> None:
        self.environ: dict[str, str] = dict(environ)
        self.platform: Platform = platform
        self.cwd = cwd
        home_var = "USERPROFILE" if platform == "win32" else "HOME"
        self.home = Path(self.environ.get(home_var) or str(Path.home()))

    # --- base directories -------------------------------------------------
    @property
    def appdata(self) -> Path:
        return Path(self.environ.get("APPDATA") or str(self.home / "AppData" / "Roaming"))

    @property
    def localappdata(self) -> Path:
        return Path(self.environ.get("LOCALAPPDATA") or str(self.home / "AppData" / "Local"))

    @property
    def xdg_config(self) -> Path:
        return Path(self.environ.get("XDG_CONFIG_HOME") or str(self.home / ".config"))

    @property
    def state_dir(self) -> Path:
        override = self.environ.get("MCP_BROWSER_STATE_DIR")
        if override:
            return Path(override)
        if self.platform == "darwin":
            return self.home / "Library" / "Application Support" / "mcp-browser"
        if self.platform == "win32":
            return self.localappdata / "mcp-browser"
        base = self.environ.get("XDG_STATE_HOME") or str(self.home / ".local" / "state")
        return Path(base) / "mcp-browser"

    # --- state layout -----------------------------------------------------
    @property
    def token_file(self) -> Path:
        return self.state_dir / "token"

    @property
    def pid_file(self) -> Path:
        return self.state_dir / "server.pid"

    @property
    def log_file(self) -> Path:
        return self.state_dir / "server.log"

    @property
    def catalog_file(self) -> Path:
        return self.state_dir / "catalog.json"

    @property
    def backups_dir(self) -> Path:
        return self.state_dir / "backups"

    @property
    def locks_dir(self) -> Path:
        return self.state_dir / "locks"

    @property
    def oauth_dir(self) -> Path:
        return self.state_dir / "oauth"

    @property
    def paths_file(self) -> Path:
        return self.state_dir / "paths.json"

    # --- client directories -----------------------------------------------
    def expand_home(self, p: str) -> Path:
        if p == "~":
            return self.home
        if p.startswith(("~/", "~\\")):
            return self.home / p[2:]
        return Path(p)

    def claude_dir(self) -> Path:
        """`$CLAUDE_CONFIG_DIR` or `~/.claude`; holds plugins."""
        return Path(self.environ.get("CLAUDE_CONFIG_DIR") or str(self.home / ".claude"))

    def claude_json_dir(self) -> Path:
        """Directory holding `.claude.json`: `$CLAUDE_CONFIG_DIR` or the home directory."""
        return Path(self.environ.get("CLAUDE_CONFIG_DIR") or str(self.home))

    def claude_desktop_dir(self) -> Path:
        if self.platform == "darwin":
            return self.home / "Library" / "Application Support" / "Claude"
        if self.platform == "win32":
            for found in sorted(self.localappdata.glob("Packages/Claude_*/LocalCache/Roaming/Claude")):
                if found.exists():
                    return found
            return self.appdata / "Claude"
        return self.xdg_config / "Claude"

    def codex_home(self) -> Path:
        return Path(self.environ.get("CODEX_HOME") or str(self.home / ".codex"))

    def code_user_dir(self) -> Path:
        """VS Code's `User` directory."""
        if self.platform == "darwin":
            return self.home / "Library" / "Application Support" / "Code" / "User"
        if self.platform == "win32":
            return self.appdata / "Code" / "User"
        return self.xdg_config / "Code" / "User"

    # --- templates --------------------------------------------------------
    def tokens(self, project: Path | None = None) -> dict[str, str]:
        tokens = {
            "home": str(self.home),
            "appdata": str(self.appdata),
            "localappdata": str(self.localappdata),
            "xdg_config": str(self.xdg_config),
            "claude_dir": str(self.claude_dir()),
            "claude_json_dir": str(self.claude_json_dir()),
            "claude_desktop_dir": str(self.claude_desktop_dir()),
            "codex_home": str(self.codex_home()),
            "code_user": str(self.code_user_dir()),
        }
        if project is not None:
            tokens["project"] = str(project)
        return tokens

    def candidates(self, rule: PathRule, project: Path | None = None) -> list[Path]:
        """Expand a rule; existing paths first (globs yield only existing matches).

        Returns [] when the rule does not apply to this platform.
        """
        if self.platform not in rule.platforms:
            return []
        template = rule.template
        tokens = self.tokens(project)

        def fill(text: str, escape: bool) -> str:
            for key, value in tokens.items():
                text = text.replace("{" + key + "}", glob.escape(value) if escape else value)
            return text

        hits = [template.find(c) for c in _GLOB_CHARS if c in template]
        if not hits:
            return [Path(fill(template, False))]
        # only the glob characters the template itself declares expand; token values (the home
        # directory, a project path) are literal even when they contain `[`, `?` or `*`
        cut = template.rfind("/", 0, min(hits))
        base = Path(fill(template[:cut], False)) if cut > 0 else Path("/" if cut == 0 else ".")
        pattern = fill(template[cut + 1 :], True)
        return sorted(base.glob(pattern)) if base.exists() else []

    def existing(self, rule: PathRule, project: Path | None = None) -> list[Path]:
        return [p for p in self.candidates(rule, project) if p.exists()]

    def override_paths(self) -> dict[str, list[str]]:
        """`<state>/paths.json` mapping client id to extra config paths; {} when absent or invalid."""
        try:
            raw: Any = json.loads(self.paths_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        out: dict[str, list[str]] = {}
        for key, value in cast("dict[str, Any]", raw).items():
            if isinstance(value, list):
                out[key] = [str(v) for v in cast("list[Any]", value)]
        return out


def default_paths() -> Paths:
    return Paths(os.environ, current_platform(), Path.cwd())
