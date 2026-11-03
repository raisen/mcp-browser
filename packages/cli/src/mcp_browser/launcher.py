"""Open the tokenized URL without putting the token in a browser's argv (visible to `ps` on Linux)."""

from __future__ import annotations

import html
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path

from mcp_browser_core.paths import Paths

LAUNCHER_NAME = "launch.html"
REMOVE_AFTER = 5.0


def remove_launcher(paths: Paths) -> None:
    (paths.state_dir / LAUNCHER_NAME).unlink(missing_ok=True)


def write_launcher(paths: Paths, address: str) -> Path:
    """A 0600 HTML page that redirects to `address`; replaces any earlier one."""
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    target = paths.state_dir / LAUNCHER_NAME
    remove_launcher(paths)
    literal = json.dumps(address).replace("<", "\\u003c")
    page = (
        '<!doctype html><meta charset="utf-8"><title>mcp-browser</title>'
        f"<script>location.replace({literal});</script>"
        f'<a href="{html.escape(address)}">Continue to mcp-browser</a>'
    )
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(page)
    return target


def open_url(paths: Paths, address: str) -> None:
    """Linux: open a short-lived launcher file instead of the URL. Other systems: open the URL."""
    try:
        if sys.platform.startswith("linux"):
            page = write_launcher(paths, address)
            webbrowser.open(page.as_uri())
            timer = threading.Timer(REMOVE_AFTER, remove_launcher, args=(paths,))
            timer.daemon = True
            timer.start()
        else:
            webbrowser.open(address)
    except (webbrowser.Error, OSError) as exc:
        print(f"Could not open a browser ({exc}); open the URL yourself.", file=sys.stderr)
