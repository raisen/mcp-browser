"""State-dir helpers shared by the foreground server and the background daemon."""

from __future__ import annotations

import json
import os
import secrets
import socket
import sys
import urllib.request
from dataclasses import dataclass
from typing import Any, cast

from mcp_browser_core.paths import Paths

HOST = "127.0.0.1"
DEFAULT_PORT = 8765


@dataclass(frozen=True)
class PidInfo:
    pid: int
    port: int


def url(port: int, token: str | None = None) -> str:
    base = f"http://{HOST}:{port}/"
    return f"{base}#token={token}" if token else base


def load_token(paths: Paths) -> str:
    """Read the bearer token, creating it (mode 0600) on first use."""
    try:
        text = paths.token_file.read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    if text:
        return text
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    fd = os.open(paths.token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token)
    return token


def read_pid(paths: Paths) -> PidInfo | None:
    try:
        raw = cast("dict[str, Any]", json.loads(paths.pid_file.read_text(encoding="utf-8")))
        return PidInfo(pid=int(raw["pid"]), port=int(raw["port"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_pid(paths: Paths, info: PidInfo) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.pid_file.write_text(json.dumps({"pid": info.pid, "port": info.port}), encoding="utf-8")


def clear_pid(paths: Paths) -> None:
    paths.pid_file.unlink(missing_ok=True)


def probe(port: int, timeout: float = 1.0) -> dict[str, Any] | None:
    """GET /healthz on loopback; returns the body only for an mcp-browser server."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://{HOST}:{port}/healthz", timeout=timeout) as resp:
            body = cast("dict[str, Any]", json.loads(resp.read().decode("utf-8")))
    except (OSError, ValueError):
        return None
    if body.get("ok") is True and isinstance(body.get("pid"), int):
        return body
    return None


def pid_alive(pid: int) -> bool:
    """True if a process with this pid exists (never signals it)."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel = ctypes.windll.kernel32  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownVariableType]
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        kernel.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # exists but belongs to someone else
    return True


def find_running(paths: Paths, port: int) -> PidInfo | None:
    """Our server: the pid file's pid is alive AND /healthz on its port reports that same pid.
    Anything else listening on a port is never trusted (it could be squatting to steal the token).
    Stale pid files are cleaned. `port` is unused on purpose: only the pid file identifies us."""
    info = read_pid(paths)
    if info is None:
        return None
    if pid_alive(info.pid):
        health = probe(info.port)
        if health is not None and health["pid"] == info.pid:
            return info
    clear_pid(paths)
    return None


def taken_message(port: int) -> str:
    return (
        f"Port {port} is taken by something other than mcp-browser; nothing was sent to it. "
        "Free the port or pick another one with --port N."
    )


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sys.platform != "win32":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((HOST, port))
        except OSError:
            return False
    return True
