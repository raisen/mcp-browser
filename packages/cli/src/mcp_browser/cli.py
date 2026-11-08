"""Command line: serve (default), start, stop, status, open. Loopback only."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from collections.abc import Sequence
from dataclasses import dataclass

from mcp_browser_core import __version__
from mcp_browser_core.paths import Paths, default_paths

from . import daemon, launcher, runtime
from .runtime import DEFAULT_PORT, PidInfo

COMMANDS = ("serve", "start", "stop", "status", "open", "tui")


@dataclass(frozen=True)
class Options:
    command: str
    port: int
    no_open: bool
    detached: bool
    project: str | None = None
    filter: str | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-browser",
        description="Browse, search, run and edit every MCP server configured on this machine.",
    )
    parser.add_argument("--version", action="version", version=f"mcp-browser {__version__}")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default {DEFAULT_PORT})")
    parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    parser.add_argument("--detached", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--project", type=str, default=None, help="project directory to inspect")
    parser.add_argument("--filter", type=str, default=None, help="pre-filter server or tool")
    sub = parser.add_subparsers(dest="command", metavar="{serve,start,stop,status,open,tui}")
    helps = {
        "serve": "run the server in the foreground (default)",
        "start": "run the server in the background",
        "stop": "stop the background server",
        "status": "show whether the server is running",
        "open": "open the UI of the running server",
        "tui": "launch the terminal user interface",
    }
    for name in COMMANDS:
        child = sub.add_parser(name, help=helps[name])
        child.add_argument("--port", type=int, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        child.add_argument(
            "--no-open", action="store_true", default=argparse.SUPPRESS, help="do not open a browser"
        )
        child.add_argument(
            "--detached", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS
        )
        if name == "tui":
            child.add_argument(
                "--project", type=str, default=argparse.SUPPRESS, help="project directory to inspect"
            )
            child.add_argument(
                "--filter", type=str, default=argparse.SUPPRESS, help="pre-filter server or tool"
            )
    return parser


def parse_options(argv: Sequence[str] | None) -> Options:
    ns = build_parser().parse_args(argv)
    return Options(
        command=str(ns.command or "serve"),
        port=int(ns.port),
        no_open=bool(ns.no_open),
        detached=bool(ns.detached),
        project=getattr(ns, "project", None),
        filter=getattr(ns, "filter", None),
    )


def _open_browser(paths: Paths, address: str) -> None:
    launcher.open_url(paths, address)


def _announce_running(paths: Paths, info: PidInfo, opts: Options) -> int:
    address = runtime.url(info.port, runtime.load_token(paths))
    print(f"mcp-browser is already running (pid {info.pid}).")
    print(address)
    if not opts.no_open:
        _open_browser(paths, address)
    return 0


def _port_busy(port: int) -> int:
    print(runtime.taken_message(port), file=sys.stderr)
    return 1


def cmd_serve(paths: Paths, opts: Options) -> int:
    existing = runtime.find_running(paths, opts.port)
    if existing is not None:
        return _announce_running(paths, existing, opts)
    if not runtime.port_free(opts.port):
        return _port_busy(opts.port)
    import uvicorn
    from mcp_browser_server.app import create_app
    from mcp_browser_server.settings import HOST, ServerSettings

    token = runtime.load_token(paths)
    app = create_app(ServerSettings(paths=paths, token=token, port=opts.port))
    address = runtime.url(opts.port, token)
    if not opts.detached:  # the detached server logs to server.log, which must never hold the token
        print(f"mcp-browser {__version__} serving at {address}")
        print("Press Ctrl+C to stop.")
    if not opts.no_open:
        threading.Timer(0.8, _open_browser, args=(paths, address)).start()
    launcher.remove_launcher(paths)
    runtime.write_pid(paths, PidInfo(os.getpid(), opts.port))
    # uvicorn restores this handler and re-raises SIGTERM after a graceful stop; exiting through
    # SystemExit lets the `finally` below remove the pid file.
    signal.signal(signal.SIGTERM, lambda _sig, _frame: sys.exit(0))
    try:
        uvicorn.run(app, host=HOST, port=opts.port, log_level="info", access_log=False)
    finally:
        info = runtime.read_pid(paths)
        if info is not None and info.pid == os.getpid():
            runtime.clear_pid(paths)
    return 0


def cmd_start(paths: Paths, opts: Options) -> int:
    existing = runtime.find_running(paths, opts.port)
    if existing is not None:
        return _announce_running(paths, existing, opts)
    if not runtime.port_free(opts.port):
        return _port_busy(opts.port)
    info = daemon.start(paths, opts.port)
    if info is None:
        print(f"The server did not start. See {paths.log_file}", file=sys.stderr)
        return 1
    address = runtime.url(info.port, runtime.load_token(paths))
    print(f"mcp-browser started in the background (pid {info.pid}).")
    print(address)
    if not opts.no_open:
        _open_browser(paths, address)
    return 0


def cmd_stop(paths: Paths, _opts: Options) -> int:
    message = daemon.stop(paths)
    print(message)
    return 1 if message.startswith(("could not", "pid ")) else 0


def cmd_status(paths: Paths, opts: Options) -> int:
    info = runtime.find_running(paths, opts.port)
    if info is None:
        print("mcp-browser is stopped.")
        if not runtime.port_free(opts.port):
            print(runtime.taken_message(opts.port))
        return 1
    print(f"mcp-browser is running (pid {info.pid}) at {runtime.url(info.port)}")
    return 0


def cmd_open(paths: Paths, opts: Options) -> int:
    info = runtime.find_running(paths, opts.port)
    if info is None:
        print("mcp-browser is not running. Start it with: mcp-browser start", file=sys.stderr)
        if not runtime.port_free(opts.port):
            print(runtime.taken_message(opts.port), file=sys.stderr)
        return 1
    address = runtime.url(info.port, runtime.load_token(paths))
    print(address)
    _open_browser(paths, address)
    return 0


def cmd_tui(paths: Paths, opts: Options) -> int:
    from .tui.app import run_tui

    return run_tui(paths, opts)


def run(argv: Sequence[str] | None = None, paths: Paths | None = None) -> int:
    opts = parse_options(argv)
    resolved = paths or default_paths()
    handlers = {
        "serve": cmd_serve,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "open": cmd_open,
        "tui": cmd_tui,
    }
    try:
        return handlers[opts.command](resolved, opts)
    except KeyboardInterrupt:
        return 0


def main() -> None:
    sys.exit(run())
