"""Modal confirmation dialog for untrusted workspace MCP servers."""

from __future__ import annotations

from typing import Any, ClassVar

from mcp_browser_core.models import ServerEntry
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmModal(ModalScreen[bool]):
    """Prompts the user to confirm executing an untrusted repo-provided server."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(self, entry: ServerEntry, detail: dict[str, Any]) -> None:
        super().__init__()
        self.entry = entry
        self.detail = detail

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static("⚠️  Untrusted Server Confirmation", id="confirm-title")
            with Vertical(id="confirm-body"):
                yield Static(
                    f"[bold]Server:[/] {self.entry.name} ({self.entry.client_id} / {self.entry.scope})\n"
                    f"[bold]Config:[/] {self.entry.config_path}"
                )
                kind = str(self.detail.get("kind", "unknown"))
                if kind == "stdio":
                    cmd = str(self.detail.get("command", ""))
                    args = " ".join(str(a) for a in self.detail.get("args", []))
                    full_cmd = f"{cmd} {args}".strip()
                    cwd = self.detail.get("cwd") or "(current directory)"
                    yield Static(
                        f"\n[bold]Command:[/] [cyan]{full_cmd}[/]\n"
                        f"[bold]Working Directory:[/] {cwd}\n"
                        "[bold yellow]⚠️  Warning:[/] Runs local process inheriting environment."
                    )
                else:
                    url = str(self.detail.get("url", ""))
                    host = str(self.detail.get("host") or "unknown")
                    yield Static(
                        f"\n[bold]Transport:[/] {kind.upper()}\n"
                        f"[bold]URL:[/] [cyan]{url}[/]\n"
                        f"[bold]Target Host:[/] {host}"
                    )

                env_vars = self.detail.get("env_vars", [])
                if env_vars:
                    env_list = ", ".join(f"[bold]{v}[/]" for v in env_vars)
                    yield Static(f"\n[bold]Environment variables queried:[/] {env_list}")

            with Horizontal(id="confirm-buttons"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button("Trust & Connect", variant="warning", id="btn-confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-confirm")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)
