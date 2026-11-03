"""Background server: detach with Popen, track by pid file, stop only a confirmed pid."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import Any

from mcp_browser_core.paths import Paths

from . import runtime
from .runtime import PidInfo

START_TIMEOUT = 10.0
STOP_TIMEOUT = 5.0


def serve_command(port: int) -> list[str]:
    """Frozen (PyInstaller) builds re-run themselves; otherwise run the package."""
    tail = ["serve", "--no-open", "--detached", "--port", str(port)]
    if getattr(sys, "frozen", False):
        return [sys.executable, *tail]
    return [sys.executable, "-m", "mcp_browser", *tail]


def _detach_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )
    else:
        kwargs["start_new_session"] = True
    return kwargs


def start(paths: Paths, port: int) -> PidInfo | None:
    """Spawn the detached server and wait for /healthz. Returns None on failure."""
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    with open(paths.log_file, "ab") as log:
        proc = subprocess.Popen(
            serve_command(port),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            **_detach_kwargs(),
        )
    runtime.write_pid(paths, PidInfo(proc.pid, port))
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        health = runtime.probe(port)
        if health is not None and int(health["pid"]) == proc.pid:
            info = PidInfo(pid=int(health["pid"]), port=port)
            runtime.write_pid(paths, info)
            return info
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    runtime.clear_pid(paths)
    return None


def stop(paths: Paths) -> str:
    """Stop the tracked server. Returns a human message; the pid is signalled only if /healthz confirms it."""
    info = runtime.read_pid(paths)
    if info is None:
        return "not running"
    health = runtime.probe(info.port)
    if health is None or health["pid"] != info.pid:
        runtime.clear_pid(paths)
        return "not running (cleared a stale pid file)"
    try:
        os.kill(info.pid, signal.SIGTERM)  # TerminateProcess on Windows
    except OSError as exc:
        return f"could not stop pid {info.pid}: {exc}"
    deadline = time.monotonic() + STOP_TIMEOUT
    while time.monotonic() < deadline:
        if runtime.probe(info.port) is None:
            runtime.clear_pid(paths)
            return f"stopped pid {info.pid}"
        time.sleep(0.2)
    return f"pid {info.pid} did not exit within {STOP_TIMEOUT:.0f}s"
