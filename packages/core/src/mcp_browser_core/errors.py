"""API-visible errors. Every subclass carries a stable `code` and HTTP `status`."""

from __future__ import annotations

from typing import Any


class McpBrowserError(Exception):
    code: str = "internal_error"
    status: int = 500

    def __init__(self, message: str = "", **detail: Any) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        self.detail: dict[str, Any] = dict(detail)

    def to_body(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message, "detail": self.detail}


class NotFound(McpBrowserError):
    code, status = "not_found", 404


class ReadOnly(McpBrowserError):
    code, status = "read_only", 403


class UnsupportedTransport(McpBrowserError):
    code, status = "unsupported_transport", 422


class InvalidArguments(McpBrowserError):
    code, status = "invalid_arguments", 400


class UnresolvedPlaceholders(McpBrowserError):
    """detail.placeholders lists the names that could not be expanded."""

    code, status = "unresolved_placeholders", 400

    def __init__(self, message: str = "", *, placeholders: list[str], **detail: Any) -> None:
        super().__init__(message, placeholders=placeholders, **detail)


class FileChanged(McpBrowserError):
    code, status = "file_changed", 409


class CommentsWouldBeLost(McpBrowserError):
    """detail.can_override is False for non-dedicated files (Zed) and True otherwise."""

    code, status = "comments_would_be_lost", 409

    def __init__(self, message: str = "", *, can_override: bool, **detail: Any) -> None:
        super().__init__(message, can_override=can_override, **detail)


class ConnectFailed(McpBrowserError):
    """detail.stderr_tail holds the last captured stderr of a stdio server."""

    code, status = "connect_failed", 502

    def __init__(self, message: str = "", *, stderr_tail: str = "", **detail: Any) -> None:
        super().__init__(message, stderr_tail=stderr_tail, **detail)


class OperationTimeout(McpBrowserError):
    code, status = "timeout", 504


class Unauthorized(McpBrowserError):
    code, status = "unauthorized", 401


class Conflict(McpBrowserError):
    code, status = "name_exists", 409


class ConfirmationRequired(McpBrowserError):
    """Untrusted (project-scope) entry; detail holds `command`/`args` or `url`, `host`, `env_vars`."""

    code, status = "confirmation_required", 409


class AuthRequired(McpBrowserError):
    """Sign-in needed but the operation is non-interactive (scan); the UI offers an explicit Connect."""

    code, status = "needs_auth", 409
