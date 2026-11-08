"""Tests for ToolRunnerWidget and tool execution flow."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from mcp_browser.tui.app import McpBrowserApp
from mcp_browser.tui.models import RunToolRequested
from mcp_browser.tui.widgets.tool_runner import ToolRunnerWidget, generate_skeleton
from mcp_browser_core.catalog_models import CallResult, ToolInfo
from mcp_browser_core.models import ServerEntry, StdioTransport
from mcp_browser_core.paths import Paths
from textual.widgets import Button


def test_skeleton_generation_various_types() -> None:
    assert generate_skeleton({}) == "{\n}\n"
    assert generate_skeleton({"properties": {}}) == "{\n}\n"

    schema = {
        "properties": {
            "str_param": {"type": "string"},
            "int_param": {"type": "integer"},
            "num_param": {"type": "number"},
            "bool_param": {"type": "boolean"},
            "arr_param": {"type": "array"},
            "obj_param": {"type": "object"},
            "def_param": {"type": "string", "default": "preset"},
            "raw_param": "not-a-dict",
        }
    }
    parsed = json.loads(generate_skeleton(schema))
    assert parsed["str_param"] == ""
    assert parsed["int_param"] == 0
    assert parsed["num_param"] == 0
    assert parsed["bool_param"] is False
    assert parsed["arr_param"] == []
    assert parsed["obj_param"] == {}
    assert parsed["def_param"] == "preset"
    assert parsed["raw_param"] == ""


def test_tool_runner_empty_and_populated() -> None:
    runner = ToolRunnerWidget()
    runner.set_tools([])
    assert runner.selected_tool is None
    assert runner.args_text == "{\n}\n"

    t1 = ToolInfo(
        name="tool_one",
        description="First tool",
        input_schema={
            "type": "object",
            "properties": {"req": {"type": "string"}, "opt": {"type": "integer"}},
            "required": ["req"],
        },
    )
    t2 = ToolInfo(name="tool_two", description="Second tool", input_schema={})
    runner.set_tools([t1, t2])
    assert runner.selected_tool == t1
    assert "tool_one" in str(runner.schema_view.content)
    assert "req" in str(runner.schema_view.content)


def test_tool_runner_argument_validation() -> None:
    runner = ToolRunnerWidget()
    # No tool selected
    runner.action_run_selected_tool()
    assert "Please select a tool first" in str(runner.output_view.content)

    t1 = ToolInfo(name="test_tool", description="A tool", input_schema={})
    runner.set_tools([t1])

    # Malformed JSON
    runner.args_text = "{invalid:"
    runner.action_run_selected_tool()
    assert "Invalid JSON arguments" in runner.last_output

    # Non-dictionary JSON
    runner.args_text = '["list", "not", "dict"]'
    runner.action_run_selected_tool()
    assert "must be a JSON object" in runner.last_output

    runner.args_text = '"string"'
    runner.action_run_selected_tool()
    assert "must be a JSON object" in runner.last_output

    # Valid JSON
    messages: list[RunToolRequested] = []
    runner.post_message = lambda m: messages.append(m) if isinstance(m, RunToolRequested) else None  # type: ignore[method-assign]
    runner.args_text = '{"key": "value", "count": 3}'
    runner.action_run_selected_tool()
    assert len(messages) == 1
    assert messages[0].tool_name == "test_tool"
    assert messages[0].args == {"key": "value", "count": 3}


def test_tool_runner_output_formatting() -> None:
    runner = ToolRunnerWidget()

    # Success formatting
    success_res = CallResult(
        is_error=False,
        duration_ms=45,
        content=[{"type": "text", "text": "result content"}],
        structured={"answer": 42},
    )
    runner.set_result(success_res)
    assert runner.has_output
    assert "Status: SUCCESS" in str(runner.output_view.content)
    assert '"answer": 42' in runner.last_output

    # Error formatting with stderr
    err_res = CallResult(
        is_error=True,
        duration_ms=120,
        content=[{"type": "text", "text": "tool failed"}],
        stderr_tail="Traceback error details",
    )
    runner.set_result(err_res)
    assert "Status: ERROR" in str(runner.output_view.content)
    assert "Traceback error details" in runner.last_output

    # Hostile markup content (URLs, square brackets, tags)
    hostile_res = CallResult(
        is_error=False,
        duration_ms=88,
        content=[{"text": "https://example.com/item?foo=1&bar=2 [FLATRATE, HD]"}],
        structured={"items": ["bracket [1]", "url &tag=abc"]},
    )
    runner.set_result(hostile_res)
    assert "[FLATRATE, HD]" in str(runner.output_view.content)

    # Test toggle format to Raw JSON
    runner.action_toggle_format()
    assert not runner.pretty_mode
    assert '"duration_ms": 88' in runner.last_output

    # Test toggle format back to Pretty
    runner.action_toggle_format()
    assert runner.pretty_mode
    assert "[FLATRATE, HD]" in runner.last_output

    # Exception error formatting
    runner.set_error("Connection timed out with [hostile] tag")
    assert "Execution Failed:" in str(runner.output_view.content)
    assert "[hostile]" in str(runner.output_view.content)


@pytest.mark.anyio
async def test_tool_runner_widget_in_app(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    app = McpBrowserApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.pause()
        entry = ServerEntry(
            id="s1",
            name="test-server",
            client_id="claude-desktop",
            scope="user",
            config_path="/dummy/path",
            transport=StdioTransport(command="echo"),
        )
        tool = ToolInfo(name="math_add", description="add nums", input_schema={})
        app.selected_entry = entry
        app.action_tab_tools()
        runner = app.query_one(ToolRunnerWidget)
        runner.set_tools([tool])
        await pilot.pause()
        runner.args_text = '{"a": 1}'

        mock_call = AsyncMock(
            return_value=CallResult(
                is_error=False,
                duration_ms=15,
                content=[{"text": "sum is 3"}],
                structured={"sum": 3},
            )
        )
        monkeypatch.setattr(app.backend, "call_tool", mock_call)

        # Trigger run via button
        btn = runner.query_one("#btn-run-tool", Button)
        btn.press()
        await pilot.pause()

        mock_call.assert_awaited_once_with(entry, "math_add", {"a": 1})
        assert "Status: SUCCESS" in str(runner.output_view.content)

        # Test format toggle via 'f' and scroll
        assert runner.pretty_mode
        await pilot.press("f")
        await pilot.pause()
        assert not runner.pretty_mode
        assert '"duration_ms": 15' in runner.last_output
        await pilot.press("f")
        await pilot.pause()
        assert runner.pretty_mode

        scroll_box = runner.query_one("#tool-output-scroll")
        scroll_box.focus()
        await pilot.press("pagedown")
        await pilot.pause()

        # Test maximize and restore via 'm' and button
        assert not runner.maximized
        await pilot.press("m")
        await pilot.pause()
        assert runner.maximized
        assert runner.has_class("output-maximized")

        await pilot.press("m")
        await pilot.pause()
        assert not runner.maximized
        assert not runner.has_class("output-maximized")

        runner.query_one("#btn-toggle-maximize", Button).press()
        await pilot.pause()
        assert runner.maximized

        runner.action_restore_output()
        assert not runner.maximized

        # Trigger run via app action_run_tool
        mock_call.reset_mock()
        app.action_run_tool()
        await pilot.pause()
        mock_call.assert_awaited_once_with(entry, "math_add", {"a": 1})

        # Test backend exception
        mock_call.side_effect = RuntimeError("Process crashed")
        app.action_run_tool()
        await pilot.pause()
        assert "Process crashed" in str(runner.output_view.content)
