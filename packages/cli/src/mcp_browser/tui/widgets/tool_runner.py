"""Interactive tool runner with schema inspection and JSON argument editor."""

from __future__ import annotations

import json
from typing import Any, ClassVar, cast

from mcp_browser_core.catalog_models import CallResult, ToolInfo
from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widget import Widget
from textual.widgets import Button, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from ..models import RunToolRequested


def generate_skeleton(schema: dict[str, Any]) -> str:
    props_raw: Any = schema.get("properties")
    props = cast("dict[str, Any]", props_raw) if isinstance(props_raw, dict) else {}
    if not props:
        return "{\n}\n"
    type_defs: dict[str, Any] = {"integer": 0, "number": 0, "boolean": False, "array": [], "object": {}}
    skeleton: dict[str, Any] = {}
    for k, v in props.items():
        if isinstance(v, dict):
            v_dict = cast("dict[str, Any]", v)
            skeleton[str(k)] = v_dict.get("default", type_defs.get(str(v_dict.get("type", "string")), ""))
        else:
            skeleton[str(k)] = ""
    return json.dumps(skeleton, indent=2) + "\n"


_generate_skeleton = generate_skeleton


class ToolRunnerWidget(Widget):
    """Tool browser, schema inspector, and interactive executor."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+enter", "run_selected_tool", "Run Tool", show=False),
        Binding("f", "toggle_format", "Toggle Format", show=False),
        Binding("m", "toggle_maximize", "Maximize", show=False),
        Binding("escape", "restore_output", "Restore", show=False),
    ]

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self.tools: list[ToolInfo] = []
        self.selected_tool: ToolInfo | None = None
        self.pretty_mode: bool = True
        self.maximized: bool = False
        self.last_result: CallResult | None = None
        self._tool_list = OptionList(id="tool-list")
        self._schema_view = Static("Select a tool from the list.", id="tool-schema")
        self._args_input = TextArea(language="json", id="tool-args-input")
        self._format_btn = Button("Format: Pretty (f)", id="btn-toggle-format")
        self._max_btn = Button("Maximize (m)", id="btn-toggle-maximize")
        self._output_view = Static("Execution output will appear here.", id="tool-output")
        self.tool_list, self.schema_view = self._tool_list, self._schema_view
        self.args_input, self.output_view = self._args_input, self._output_view
        self.has_output: bool = False
        self.last_output: str = ""

    @property
    def args_text(self) -> str:
        """Raw JSON text in the arguments input area."""
        return self._args_input.text

    @args_text.setter
    def args_text(self, value: str) -> None:
        self._args_input.text = value

    def compose(self) -> ComposeResult:
        with Horizontal(id="tool-runner-container"):
            yield self._tool_list
            with Vertical(id="tool-detail"):
                yield self._schema_view
                yield Static("[bold]Arguments (JSON):[/]", id="args-label")
                yield self._args_input
                with Horizontal(id="tool-actions"):
                    yield Button("Run Tool (Ctrl+Enter)", variant="primary", id="btn-run-tool")
                with Horizontal(id="output-header-bar"):
                    yield Static("[bold]Output:[/] [dim](click/tab to scroll)[/]", id="output-label")
                    yield self._format_btn
                    yield self._max_btn
                with VerticalScroll(id="tool-output-scroll", can_focus=True):
                    yield self._output_view

    def set_tools(self, tools: list[ToolInfo]) -> None:
        """Update available tools list and reset form."""
        self.tools = list(tools)
        self.selected_tool = None
        self._tool_list.clear_options()
        for t in self.tools:
            self._tool_list.add_option(Option(t.name, id=t.name))
        if self.tools:
            self._select_tool(self.tools[0])
            self._tool_list.highlighted = 0
        else:
            self._schema_view.update("[dim]No tools exposed by this server.[/]")
            self._args_input.text = "{\n}\n"
            self._output_view.update("[dim]No output.[/]")

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if 0 <= event.option_index < len(self.tools):
            self._select_tool(self.tools[event.option_index])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if 0 <= event.option_index < len(self.tools):
            self._select_tool(self.tools[event.option_index])

    def _select_tool(self, tool: ToolInfo) -> None:
        self.selected_tool = tool
        desc = escape(tool.description or "(no description provided)")
        props_raw: Any = tool.input_schema.get("properties")
        props = cast("dict[str, Any]", props_raw) if isinstance(props_raw, dict) else {}
        req_raw: Any = tool.input_schema.get("required")
        req_list = cast("list[Any]", req_raw) if isinstance(req_raw, list) else []
        req: set[str] = {str(item) for item in req_list}

        text_lines = [f"[bold cyan]Tool:[/] {escape(tool.name)}", f"[bold]Description:[/] {desc}"]
        if props:
            text_lines.append("\n[bold]Parameters:[/]")
            for name, p_info in props.items():
                p_dict = cast("dict[str, Any]", p_info) if isinstance(p_info, dict) else {}
                p_type = escape(str(p_dict.get("type", "any")))
                p_desc = escape(str(p_dict.get("description", "")))
                r_mark = " [red]*[/]" if str(name) in req else ""
                desc_str = f" - {p_desc}" if p_desc else ""
                text_lines.append(f"  • [bold]{escape(str(name))}[/]{r_mark} ({p_type}){desc_str}")
        else:
            text_lines.append("\n[dim]No parameters required.[/]")

        self._schema_view.update("\n".join(text_lines))
        self._args_input.text = generate_skeleton(tool.input_schema)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run-tool":
            self.action_run_selected_tool()
        elif event.button.id == "btn-toggle-format":
            self.action_toggle_format()
        elif event.button.id == "btn-toggle-maximize":
            self.action_toggle_maximize()

    def action_toggle_maximize(self) -> None:
        """Toggle maximizing the output window."""
        self.maximized = not self.maximized
        self.toggle_class("output-maximized")
        self._max_btn.label = "Restore (m)" if self.maximized else "Maximize (m)"
        self._max_btn.variant = "warning" if self.maximized else "default"

    def action_restore_output(self) -> None:
        if self.maximized:
            self.action_toggle_maximize()

    def action_toggle_format(self) -> None:
        """Toggle output display between pretty text and raw JSON response."""
        self.pretty_mode = not self.pretty_mode
        self._format_btn.label = "Format: Pretty (f)" if self.pretty_mode else "Format: Raw JSON (f)"
        if self.last_result is not None:
            self._render_result(self.last_result)

    def action_run_selected_tool(self) -> None:
        """Validate JSON arguments and request tool execution."""
        if self.selected_tool is None:
            self._output_view.update("[yellow]Please select a tool first.[/]")
            return
        raw = self._args_input.text.strip()
        try:
            parsed_raw: Any = json.loads(raw) if raw else {}
            if not isinstance(parsed_raw, dict):
                msg = "[red]Error: Tool arguments must be a JSON object ({...}).[/]"
                self.last_output = msg
                self._output_view.update(msg)
                return
            parsed: dict[str, Any] = {str(k): v for k, v in cast("dict[Any, Any]", parsed_raw).items()}
        except json.JSONDecodeError as exc:
            err_msg = f"[red]Invalid JSON arguments: {exc}[/]"
            self.last_output = err_msg
            header = Content.from_markup("[red]Invalid JSON arguments:[/] ")
            self._output_view.update(header + Content(str(exc)))
            return

        self._output_view.update(f"[cyan]Executing {escape(self.selected_tool.name)}...[/]")
        self.post_message(RunToolRequested(self.selected_tool.name, parsed))

    def set_result(self, result: CallResult) -> None:
        """Display formatted execution response."""
        self.has_output = True
        self.last_result = result
        self._render_result(result)

    def _render_result(self, result: CallResult) -> None:
        status_style = "red" if result.is_error else "green"
        status_label = "ERROR" if result.is_error else "SUCCESS"
        hdr = f"[{status_style} bold]Status: {status_label}[/] ({result.duration_ms}ms)\n\n"
        if self.pretty_mode:
            body = self._format_pretty(result)
        else:
            out_data: dict[str, Any] = {
                "is_error": result.is_error,
                "duration_ms": result.duration_ms,
                "content": result.content,
            }
            if result.structured is not None:
                out_data["structured"] = result.structured
            if result.stderr_tail:
                out_data["stderr_tail"] = result.stderr_tail
            body = json.dumps(out_data, indent=2)

        self.last_output = body
        self._output_view.update(Content.from_markup(hdr) + Content(body))

    def _format_pretty(self, res: CallResult) -> str:
        parts: list[str] = []
        if res.content:
            for item in res.content:
                if item.get("type") == "text" and "text" in item:
                    text_val = str(item["text"])
                    s = text_val.strip()
                    if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
                        try:
                            parts.append(json.dumps(json.loads(s), indent=2))
                            continue
                        except Exception:
                            pass
                    parts.append(text_val)
                elif item.get("type") == "image":
                    parts.append(f"[Image: mimeType={item.get('mimeType', 'unknown')}]")
                else:
                    parts.append(json.dumps(item, indent=2))
        if res.structured is not None:
            parts.append("Structured Output:\n" + json.dumps(res.structured, indent=2))
        if res.stderr_tail:
            parts.append("Stderr Log:\n" + res.stderr_tail.strip())
        return "\n\n".join(parts) if parts else "(empty content)"

    def set_error(self, err_text: str) -> None:
        """Display error during execution."""
        self.has_output, self.last_output = True, err_text
        self._output_view.update(Content.from_markup("[red bold]Execution Failed:[/] ") + Content(err_text))
