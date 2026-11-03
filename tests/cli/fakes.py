"""Typed stand-ins for the network, port and signal helpers (keeps pyright strict happy)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp_browser.runtime import PidInfo
from mcp_browser_core.paths import Paths

Probe = Callable[[int, float], dict[str, Any] | None]


def probe_none(port: int, timeout: float = 1.0) -> dict[str, Any] | None:
    return None


def probe_pid(pid: int, port: int = 8765) -> Probe:
    def fake(p: int, timeout: float = 1.0) -> dict[str, Any] | None:
        return {"ok": True, "version": "0", "pid": pid} if p == port else None

    return fake


def port_free(port: int) -> bool:
    return True


def port_busy(port: int) -> bool:
    return False


def no_sleep(seconds: float) -> None:
    return None


def no_kill(pid: int, sig: int) -> None:
    raise AssertionError("must not signal")


def kill_noop(pid: int, sig: int) -> None:
    return None


def alive(pid: int) -> bool:
    return True


def dead(pid: int) -> bool:
    return False


def pid_file(pid: int, port: int) -> Callable[[Paths], PidInfo | None]:
    def read(paths: Paths) -> PidInfo | None:
        return PidInfo(pid, port)

    return read
