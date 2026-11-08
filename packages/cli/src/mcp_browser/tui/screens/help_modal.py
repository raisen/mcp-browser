"""Modal dialog displaying keyboard shortcuts and navigation help."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

HELP_TEXT = """
[bold cyan]Global Navigation[/]
  [bold yellow]?[/]             Toggle this Help dialog
  [bold yellow]q[/] / [bold yellow]Ctrl+C[/]    Quit MCP Browser
  [bold yellow]/[/]             Focus search / filter bar
  [bold yellow]Tab[/]           Cycle focus between panes
  [bold yellow]Esc[/]           Close modal / defocus search

[bold cyan]Server Management[/]
  [bold yellow]↑[/] / [bold yellow]↓[/]          Navigate servers in list
  [bold yellow]Enter[/]         Select and inspect server
  [bold yellow]c[/]             Connect & scan selected server
  [bold yellow]r[/]             Re-discover configs & refresh catalog

[bold cyan]Tabs & Tool Execution[/]
  [bold yellow]1, 2, 3, 4[/]    Switch tab (Overview, Tools, Resources, Prompts)
  [bold yellow][ / ][/]         Cycle previous / next tab
  [bold yellow]Ctrl+Enter[/]    Run selected tool with arguments
  [bold yellow]f[/]             Toggle output format (Pretty / Raw JSON)
  [bold yellow]m[/]             Maximize / restore output window
  [bold yellow]↑ / ↓ / PgUp[/] Scroll focused output window
"""


class HelpModal(ModalScreen[None]):
    """Modal displaying keyboard shortcuts."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close"),
        Binding("enter", "close", "Close"),
        Binding("?", "close", "Close"),
        Binding("q", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static("⌨️  Keyboard Shortcuts", id="help-title")
            with Vertical(id="help-body"):
                yield Static(HELP_TEXT.strip())
            with Vertical(id="help-buttons"):
                yield Button("Close", variant="primary", id="btn-close-help")

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
