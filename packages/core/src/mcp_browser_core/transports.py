"""Build the SDK transport from an expanded Transport (may import `mcp`, like connect/oauth)."""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import threading
from collections.abc import AsyncGenerator, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, TextIO, cast

import httpx2
from mcp import StdioServerParameters
from mcp.client._transport import TransportStreams
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from pydantic import ValidationError

from .errors import AuthRequired, UnresolvedPlaceholders, UnsupportedTransport
from .expand import expand_transport
from .models import HttpTransport, ServerEntry, SseTransport, StdioTransport, Transport
from .oauth import FileTokenStorage, NoBrowserHook, OAuthHook, make_provider
from .paths import Paths

STDERR_TAIL_BYTES = 4096


class StderrCapture:
    """Bounded stderr of a stdio server: the child writes into a pipe, a daemon thread drains it and
    keeps only the last 4 KB, so a server that floods stderr costs neither disk nor memory."""

    def __init__(self) -> None:
        read_fd, write_fd = os.pipe()
        self._writer = os.fdopen(write_fd, "w")  # only its fileno() is used (by the child)
        self._buf = b""
        self._last = ""
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._pump, args=(read_fd,), daemon=True)
        self._thread.start()

    def _pump(self, read_fd: int) -> None:
        try:
            while chunk := os.read(read_fd, 65536):
                with self._lock:
                    self._buf = (self._buf + chunk)[-STDERR_TAIL_BYTES:]
        except OSError:
            pass
        finally:
            os.close(read_fd)

    @property
    def stream(self) -> TextIO:
        return self._writer

    def tail(self) -> str:
        if self._writer.closed:
            return self._last
        with self._lock:
            return self._buf.decode(errors="replace")[-STDERR_TAIL_BYTES:]

    def close(self) -> None:
        if self._writer.closed:
            return
        self._writer.close()  # the child's copy is the only write end left: EOF once it exits
        self._thread.join(1.0)
        with self._lock:
            self._last = self._buf.decode(errors="replace")[-STDERR_TAIL_BYTES:]


class _QuietParseErrors(logging.Filter):
    """The SDK logs a full pydantic traceback for every non-JSON stdout line; keep one short line."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.getMessage().startswith("Failed to parse JSONRPC message"):
            exc = record.exc_info[1] if record.exc_info else None
            raw = ""
            if isinstance(exc, ValidationError) and exc.errors():
                raw = str(exc.errors()[0].get("input", ""))
            record.msg = f"server wrote non-JSON to stdout: {raw[:80]!r}"
            record.args = None
            record.exc_info = record.exc_text = None
        return True


class _QuietAuthRequired(logging.Filter):
    """A scan hitting a sign-in is expected; drop the SDK's traceback for it."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and isinstance(record.exc_info[1], AuthRequired):
            record.exc_info = record.exc_text = None
            record.msg = "sign-in required (scan is non-interactive)"
            record.args = None
        return True


logging.getLogger("mcp.client.stdio").addFilter(_QuietParseErrors())
logging.getLogger("mcp.client.auth.oauth2").addFilter(_QuietAuthRequired())


def open_streams(
    t: Transport,
    *,
    env: Mapping[str, str],
    errlog: TextIO | None,
    auth: httpx2.Auth | None,
    connect_timeout: float,
    call_timeout: float,
) -> AbstractAsyncContextManager[TransportStreams]:
    """Async context manager yielding the SDK `(read, write)` streams for `t` (already expanded)."""
    return _open(t, env, errlog, auth, connect_timeout, call_timeout)


@asynccontextmanager
async def _open(
    t: Transport,
    env: Mapping[str, str],
    errlog: TextIO | None,
    auth: httpx2.Auth | None,
    connect_timeout: float,
    call_timeout: float,
) -> AsyncGenerator[TransportStreams, None]:
    if isinstance(t, StdioTransport):
        params = StdioServerParameters(command=t.command, args=list(t.args), env=dict(env), cwd=t.cwd)
        async with stdio_client(params, errlog=errlog or sys.stderr) as streams:
            yield streams
    elif isinstance(t, HttpTransport):
        timeout = httpx2.Timeout(connect_timeout, read=call_timeout)
        async with (
            httpx2.AsyncClient(headers=t.headers, timeout=timeout, auth=auth) as client,
            streamable_http_client(t.url, http_client=client) as streams,
        ):
            yield streams
    else:
        async with sse_client(
            t.url, headers=dict(t.headers), timeout=connect_timeout, sse_read_timeout=call_timeout, auth=auth
        ) as streams:
            yield streams


def codex_headers(entry: ServerEntry, headers: dict[str, str]) -> dict[str, str]:
    """Honor Codex `bearer_token_env_var` and `env_http_headers` (skipped if unset)."""
    out = dict(headers)
    bearer = entry.extra.get("bearer_token_env_var")
    if isinstance(bearer, str) and bearer:
        out["Authorization"] = f"Bearer ${{{bearer}}}"  # resolved (or reported) by expand
    mapped = entry.extra.get("env_http_headers")
    if isinstance(mapped, dict):
        for header, var in cast("dict[str, Any]", mapped).items():
            if isinstance(var, str) and var in os.environ:
                out[str(header)] = os.environ[var]
    return out


def prepare(entry: ServerEntry, paths: Paths) -> tuple[Transport, dict[str, str]]:
    """Expanded transport plus the full stdio environment (this process's, minus `MCP_BROWSER_*`,
    which already carries Codex `env_vars` passthrough names, with the entry env on top).
    Raises UnsupportedTransport or UnresolvedPlaceholders."""
    t = entry.transport
    if t is None:
        raise UnsupportedTransport(entry.error or "this entry has no usable transport")
    env = {k: v for k, v in os.environ.items() if not k.startswith("MCP_BROWSER_")}
    if isinstance(t, (HttpTransport, SseTransport)):
        t = t.model_copy(update={"headers": codex_headers(entry, t.headers)})
    expanded, missing = expand_transport(t, env, project=entry.project, home=paths.home)
    if missing:
        hint = ""
        if any(m.startswith("input:") for m in missing):
            hint = " VS Code ${input:...} variables cannot be resolved here; put the value in the entry."
        raise UnresolvedPlaceholders(
            f"unresolved placeholders: {', '.join(missing)}.{hint}", placeholders=missing
        )
    if isinstance(expanded, StdioTransport):
        env.update(expanded.env)
    return expanded, env


def choose_auth(
    t: Transport, paths: Paths, oauth: OAuthHook | None, *, interactive: bool = True
) -> httpx2.Auth | None:
    """OAuth provider for http/sse, unless there is no hook or a static Authorization header.
    Non-interactive (scans): stored tokens are used, but a needed sign-in raises AuthRequired."""
    if isinstance(t, StdioTransport) or (oauth is None and interactive):
        return None
    hook = oauth if interactive else NoBrowserHook(oauth.redirect_uri if oauth else NoBrowserHook.REDIRECT)
    assert hook is not None
    if any(k.lower() == "authorization" for k in t.headers):
        return None
    scope = (t.oauth or {}).get("scope")
    digest = hashlib.blake2b(t.url.encode(), digest_size=8).hexdigest()
    storage = FileTokenStorage(paths.oauth_dir / f"{digest}.json")
    return make_provider(t.url, hook, storage, scope=scope if isinstance(scope, str) else None)
