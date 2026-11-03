"""Open, list and call per operation. Hides every `mcp` type behind the models."""

from __future__ import annotations

import math
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any, TypeVar, cast

import anyio
from mcp import Client, MCPError
from mcp.types import ListPromptsResult, ListResourcesResult, ListToolsResult

from .bounds import collect_pages, fit, fit_list
from .catalog_models import CallResult, PromptInfo, ResourceInfo, ToolInfo
from .errors import (
    ConnectFailed,
    McpBrowserError,
    OperationTimeout,
)
from .models import ServerEntry, StdioTransport
from .oauth import OAuthHook
from .paths import Paths
from .scrub import Scrubber
from .transports import StderrCapture, choose_auth, open_streams, prepare

_T = TypeVar("_T")


@dataclass(frozen=True)
class ConnectOptions:
    connect_timeout: float = 30.0
    call_timeout: float = 300.0
    interactive: bool = True  # False (scans): never open a browser; a needed sign-in is AuthRequired


def flatten(exc: BaseException) -> list[BaseException]:
    """Leaves of (nested) exception groups."""
    if isinstance(exc, BaseExceptionGroup):
        group = cast("BaseExceptionGroup[BaseException]", exc)
        return [leaf for sub in group.exceptions for leaf in flatten(sub)]
    return [exc]


def describe(leaf: BaseException, command: str | None) -> str:
    if isinstance(leaf, FileNotFoundError) and command:
        return f"command not found: {command}"
    if isinstance(leaf, MCPError):
        return leaf.message or str(leaf)
    return str(leaf) or type(leaf).__name__


def clean_error(exc: McpBrowserError, scrubber: Scrubber | None) -> McpBrowserError:
    """Remove the entry's real secret values from an error's message and stderr tail."""
    if scrubber is not None:
        exc.message = scrubber.str(exc.message) or exc.code
        if isinstance(exc.detail.get("stderr_tail"), str):
            exc.detail["stderr_tail"] = scrubber.str(exc.detail["stderr_tail"])
    return exc


def map_error(
    exc: BaseException, tail: str, command: str | None, scrubber: Scrubber | None = None
) -> BaseException:
    """The McpBrowserError for `exc` (groups flattened, secrets scrubbed); cancellation is untouched."""
    leaves = flatten(exc)
    if any(isinstance(leaf, anyio.get_cancelled_exc_class()) for leaf in leaves):
        return exc
    for leaf in leaves:
        if isinstance(leaf, McpBrowserError):
            return clean_error(leaf, scrubber)
    if any(isinstance(leaf, TimeoutError) for leaf in leaves):
        return OperationTimeout("timed out")
    messages = list(dict.fromkeys(describe(leaf, command) for leaf in leaves))
    return clean_error(ConnectFailed("; ".join(messages), stderr_tail=tail), scrubber)


class Session:
    """Wraps `mcp.Client`; list_* walk pages within bounds; errors, stderr and listings are scrubbed."""

    def __init__(
        self,
        client: Client,
        capture: StderrCapture | None,
        default_timeout: float,
        scrubber: Scrubber | None = None,
    ) -> None:
        self._client = client
        self._capture = capture
        self._default_timeout = default_timeout
        self._scrub = scrubber or Scrubber()

    @property
    def stderr_tail(self) -> str:
        """Last 4 KB the stdio server wrote to stderr ('' for http/sse)."""
        return self._scrub.str(self._capture.tail()) if self._capture else ""

    async def _run(self, op: Awaitable[_T], timeout: float | None = None) -> _T:
        try:
            with anyio.fail_after(timeout or self._default_timeout):
                return await op
        except TimeoutError as exc:
            raise OperationTimeout("operation timed out") from exc
        except MCPError as exc:
            raise ConnectFailed(self._scrub.str(describe(exc, None)), stderr_tail=self.stderr_tail) from exc

    async def _list(
        self, fetch: Callable[[str | None], Awaitable[Any]], pick: Callable[[Any], list[_T]]
    ) -> list[_T]:
        """One deadline for the whole listing."""
        try:
            with anyio.fail_after(self._default_timeout):
                return await collect_pages(lambda c: self._run(fetch(c)), pick)
        except TimeoutError as exc:
            raise OperationTimeout("listing timed out") from exc

    async def list_tools(self) -> list[ToolInfo]:
        if not self._client.server_capabilities.tools:
            return []

        def pick(page: ListToolsResult) -> list[ToolInfo]:
            return [
                ToolInfo(
                    name=t.name,
                    description=t.description,
                    input_schema=self._scrub.obj(dict(t.input_schema)),
                )
                for t in page.tools
            ]

        return await self._list(lambda c: self._client.list_tools(cursor=c), pick)

    async def list_resources(self) -> list[ResourceInfo]:
        if not self._client.server_capabilities.resources:
            return []

        def pick(page: ListResourcesResult) -> list[ResourceInfo]:
            return [
                ResourceInfo(uri=str(r.uri), name=r.name, mime_type=r.mime_type, description=r.description)
                for r in page.resources
            ]

        return await self._list(lambda c: self._client.list_resources(cursor=c), pick)

    async def list_prompts(self) -> list[PromptInfo]:
        if not self._client.server_capabilities.prompts:
            return []

        def pick(page: ListPromptsResult) -> list[PromptInfo]:
            return [
                PromptInfo(
                    name=p.name,
                    description=p.description,
                    arguments=[a.model_dump(mode="json", exclude_none=True) for a in p.arguments or []],
                )
                for p in page.prompts
            ]

        return await self._list(lambda c: self._client.list_prompts(cursor=c), pick)

    async def call_tool(self, name: str, args: dict[str, Any], timeout: float) -> CallResult:
        started = time.monotonic()
        result = await self._run(self._client.call_tool(name, args), timeout)
        body, truncated = fit(
            {
                "content": [b.model_dump(mode="json", exclude_none=True) for b in result.content],
                "structured": result.structured_content,
            }
        )
        return CallResult(
            content=body["content"],
            structured=body["structured"],
            is_error=result.is_error,
            duration_ms=int((time.monotonic() - started) * 1000),
            stderr_tail=self.stderr_tail or None,
            truncated=truncated,
        )

    async def read_resource(self, uri: str) -> list[dict[str, Any]]:
        result = await self._run(self._client.read_resource(uri))
        return fit_list([c.model_dump(mode="json", exclude_none=True) for c in result.contents])

    async def get_prompt(self, name: str, args: dict[str, str]) -> dict[str, Any]:
        result = await self._run(self._client.get_prompt(name, args))
        body, truncated = fit(result.model_dump(mode="json", exclude_none=True))
        return {**body, "truncated": True} if truncated else body


def session(
    entry: ServerEntry,
    paths: Paths,
    opts: ConnectOptions,
    oauth: OAuthHook | None,
    *,
    limiter: anyio.CapacityLimiter,
) -> AbstractAsyncContextManager[Session]:
    """`async with session(...) as s:` expands the transport (UnresolvedPlaceholders), holds one slot of
    `limiter` for its whole lifetime, connects within `opts.connect_timeout` and maps errors:
    TimeoutError -> OperationTimeout, any other (flattened ExceptionGroup) -> ConnectFailed(stderr_tail)."""
    return _session(entry, paths, opts, oauth, limiter)


@asynccontextmanager
async def _session(
    entry: ServerEntry,
    paths: Paths,
    opts: ConnectOptions,
    oauth: OAuthHook | None,
    limiter: anyio.CapacityLimiter,
) -> AsyncGenerator[Session, None]:
    t, env = prepare(entry, paths)
    scrubber = Scrubber.build(entry, t, env, paths.home)
    command = t.command if isinstance(t, StdioTransport) else None
    capture = StderrCapture() if command else None
    connected = False
    async with limiter:
        # The deadline covers the handshake only; it is lifted once connected, so the scope
        # still nests correctly around the SDK's own task groups.
        scope = anyio.CancelScope(deadline=anyio.current_time() + opts.connect_timeout)
        try:
            with scope:
                async with AsyncExitStack() as stack:
                    streams = open_streams(
                        t,
                        env=env,
                        errlog=capture.stream if capture else None,
                        auth=choose_auth(t, paths, oauth, interactive=opts.interactive),
                        connect_timeout=opts.connect_timeout,
                        call_timeout=opts.call_timeout,
                    )
                    client = await stack.enter_async_context(Client(streams, cache=None))
                    connected, scope.deadline = True, math.inf
                    yield Session(client, capture, opts.call_timeout, scrubber)
        except BaseException as exc:
            if connected and not isinstance(exc, BaseExceptionGroup):
                raise
            tail = scrubber.str(capture.tail()) if capture else ""
            mapped = map_error(cast("BaseException", exc), tail, command, scrubber)
            if mapped is exc:
                raise
            raise mapped from None
        finally:
            if capture:
                capture.close()
        if scope.cancelled_caught:
            raise OperationTimeout(
                "connect timed out", stderr_tail=scrubber.str(capture.tail()) if capture else ""
            )
