"""Inspectors and viewers for MCP resources and prompt templates."""

from __future__ import annotations

import json
from typing import Any, cast

from mcp_browser_core.catalog_models import PromptInfo, ResourceInfo
from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widget import Widget
from textual.widgets import Button, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from ..models import GetPromptRequested, ReadResourceRequested


class ResourcesWidget(Widget):
    """Browser and content viewer for MCP server resources."""

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self.resources: list[ResourceInfo] = []
        self.selected_resource: ResourceInfo | None = None
        self._list = OptionList(id="resource-list")
        self._meta = Static("Select a resource to inspect.", id="resource-meta")
        self._output = Static("Content will appear here.", id="resource-output")
        self.list_view = self._list
        self.meta_view = self._meta
        self.output_view = self._output

    def compose(self) -> ComposeResult:
        with Horizontal(id="resource-container"):
            yield self._list
            with Vertical(id="resource-detail"):
                yield self._meta
                with Horizontal():
                    yield Button("Read Resource", variant="primary", id="btn-read-resource")
                yield Static("[bold]Resource Content:[/] [dim](click/tab to scroll)[/]")
                with VerticalScroll(id="resource-output-scroll", can_focus=True):
                    yield self._output

    def set_resources(self, resources: list[ResourceInfo]) -> None:
        self.resources = list(resources)
        self.selected_resource = None
        self._list.clear_options()
        for r in self.resources:
            title = r.name or r.uri
            self._list.add_option(Option(title, id=r.uri))
        if self.resources:
            self._select_resource(self.resources[0])
            self._list.highlighted = 0
        else:
            self._meta.update("[dim]No resources exposed by this server.[/]")
            self._output.update("[dim]No content.[/]")

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        idx = event.option_index
        if 0 <= idx < len(self.resources):
            self._select_resource(self.resources[idx])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if 0 <= idx < len(self.resources):
            self._select_resource(self.resources[idx])

    def _select_resource(self, r: ResourceInfo) -> None:
        self.selected_resource = r
        lines = [
            f"[bold cyan]URI:[/] {escape(r.uri)}",
            f"[bold]Name:[/] {escape(r.name or '(none)')}",
            f"[bold]MIME Type:[/] {escape(r.mime_type or 'unknown')}",
            f"[bold]Description:[/] {escape(r.description or '(none)')}",
        ]
        self._meta.update("\n".join(lines))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-read-resource" and self.selected_resource:
            self._output.update(f"[cyan]Reading {escape(self.selected_resource.uri)}...[/]")
            self.post_message(ReadResourceRequested(self.selected_resource.uri))

    def set_result(self, content: list[dict[str, Any]]) -> None:
        dumped = json.dumps(content, indent=2)
        header = Content.from_markup("[green bold]Success[/]\n\n")
        self._output.update(header + Content(dumped))

    def set_error(self, err_text: str) -> None:
        header = Content.from_markup("[red bold]Read Failed:[/] ")
        self._output.update(header + Content(err_text))


class PromptsWidget(Widget):
    """Browser and executor for MCP server prompts."""

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self.prompts: list[PromptInfo] = []
        self.selected_prompt: PromptInfo | None = None
        self._list = OptionList(id="prompt-list")
        self._meta = Static("Select a prompt template to inspect.", id="prompt-meta")
        self._args_input = TextArea(language="json", id="prompt-args-input")
        self._output = Static("Prompt response will appear here.", id="prompt-output")
        self.list_view = self._list
        self.meta_view = self._meta
        self.args_input = self._args_input
        self.output_view = self._output

    def compose(self) -> ComposeResult:
        with Horizontal(id="prompt-container"):
            yield self._list
            with Vertical(id="prompt-detail"):
                yield self._meta
                yield Static("[bold]Arguments (JSON key-value):[/]")
                yield self._args_input
                with Horizontal():
                    yield Button("Get Prompt", variant="primary", id="btn-get-prompt")
                yield Static("[bold]Rendered Prompt Output:[/] [dim](click/tab to scroll)[/]")
                with VerticalScroll(id="prompt-output-scroll", can_focus=True):
                    yield self._output

    def set_prompts(self, prompts: list[PromptInfo]) -> None:
        self.prompts = list(prompts)
        self.selected_prompt = None
        self._list.clear_options()
        for p in self.prompts:
            self._list.add_option(Option(p.name, id=p.name))
        if self.prompts:
            self._select_prompt(self.prompts[0])
            self._list.highlighted = 0
        else:
            self._meta.update("[dim]No prompt templates exposed by this server.[/]")
            self._args_input.text = "{\n}\n"
            self._output.update("[dim]No output.[/]")

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        idx = event.option_index
        if 0 <= idx < len(self.prompts):
            self._select_prompt(self.prompts[idx])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if 0 <= idx < len(self.prompts):
            self._select_prompt(self.prompts[idx])

    def _select_prompt(self, p: PromptInfo) -> None:
        self.selected_prompt = p
        lines = [
            f"[bold cyan]Prompt:[/] {escape(p.name)}",
            f"[bold]Description:[/] {escape(p.description or '(none)')}",
        ]
        args_skeleton: dict[str, str] = {}
        if p.arguments:
            lines.append("\n[bold]Arguments:[/]")
            for a in p.arguments:
                aname = escape(str(a.get("name", "")))
                adesc = escape(str(a.get("description", "")))
                areq = " [red]*[/]" if a.get("required") else ""
                lines.append(f"  • [bold]{aname}[/]{areq}: {adesc}")
                args_skeleton[str(a.get("name", ""))] = ""
        else:
            lines.append("\n[dim]No arguments required.[/]")

        self._meta.update("\n".join(lines))
        self._args_input.text = json.dumps(args_skeleton, indent=2) + "\n"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-get-prompt" and self.selected_prompt:
            raw = self._args_input.text.strip()
            try:
                parsed_raw: Any = json.loads(raw) if raw else {}
                str_args: dict[str, str] = {}
                if isinstance(parsed_raw, dict):
                    parsed_dict = cast("dict[str, Any]", parsed_raw)
                    for k, v in parsed_dict.items():
                        str_args[str(k)] = str(v)
            except Exception as exc:
                header = Content.from_markup("[red]Invalid JSON arguments:[/] ")
                self._output.update(header + Content(str(exc)))
                return
            self._output.update(f"[cyan]Rendering prompt {escape(self.selected_prompt.name)}...[/]")
            self.post_message(GetPromptRequested(self.selected_prompt.name, str_args))

    def set_result(self, data: dict[str, Any]) -> None:
        dumped = json.dumps(data, indent=2)
        header = Content.from_markup("[green bold]Rendered Prompt[/]\n\n")
        self._output.update(header + Content(dumped))

    def set_error(self, err_text: str) -> None:
        header = Content.from_markup("[red bold]Prompt Error:[/] ")
        self._output.update(header + Content(err_text))
