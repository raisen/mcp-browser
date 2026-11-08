"""Tests for ResourcesWidget, PromptsWidget, and app resource/prompt execution."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from mcp_browser.tui.app import McpBrowserApp
from mcp_browser.tui.models import GetPromptRequested, ReadResourceRequested
from mcp_browser.tui.widgets.resource_prompts import PromptsWidget, ResourcesWidget
from mcp_browser_core.catalog_models import PromptInfo, ResourceInfo
from mcp_browser_core.models import ServerEntry, StdioTransport
from mcp_browser_core.paths import Paths
from textual.widgets import Button


def test_resources_widget_empty_and_populated() -> None:
    widget = ResourcesWidget()
    widget.set_resources([])
    assert widget.selected_resource is None
    assert "No resources exposed" in str(widget.meta_view.content)

    r1 = ResourceInfo(
        uri="res://docs/guide", name="Guide", mime_type="text/markdown", description="Main docs"
    )
    r2 = ResourceInfo(uri="res://data/stats", name="Stats", mime_type="application/json")
    widget.set_resources([r1, r2])
    assert widget.selected_resource == r1
    assert "res://docs/guide" in str(widget.meta_view.content)
    assert "Guide" in str(widget.meta_view.content)
    assert "text/markdown" in str(widget.meta_view.content)


def test_resources_widget_read_and_formatting() -> None:
    widget = ResourcesWidget()
    r1 = ResourceInfo(uri="res://item/1", name="Item 1")
    widget.set_resources([r1])

    # Test read button posts event
    messages: list[ReadResourceRequested] = []
    widget.post_message = lambda m: messages.append(m) if isinstance(m, ReadResourceRequested) else None  # type: ignore[method-assign]
    btn = Button("Read", id="btn-read-resource")
    widget.on_button_pressed(Button.Pressed(btn))
    assert len(messages) == 1
    assert messages[0].uri == "res://item/1"

    # Test set_result
    widget.set_result([{"text": "file contents", "blob": "data"}])
    assert "Success" in str(widget.output_view.content)
    assert "file contents" in str(widget.output_view.content)

    # Test set_error
    widget.set_error("404 Not Found")
    assert "Read Failed:" in str(widget.output_view.content)
    assert "404 Not Found" in str(widget.output_view.content)


def test_prompts_widget_empty_and_populated() -> None:
    widget = PromptsWidget()
    widget.set_prompts([])
    assert widget.selected_prompt is None
    assert "No prompt templates exposed" in str(widget.meta_view.content)

    p1 = PromptInfo(
        name="code_review",
        description="Review code snippet",
        arguments=[
            {"name": "code", "description": "Snippet to review", "required": True},
            {"name": "language", "description": "Language name"},
        ],
    )
    widget.set_prompts([p1])
    assert widget.selected_prompt == p1
    assert "code_review" in str(widget.meta_view.content)
    assert "Snippet to review" in str(widget.meta_view.content)
    parsed = json.loads(widget.args_input.text)
    assert "code" in parsed and "language" in parsed


def test_prompts_widget_actions_and_formatting() -> None:
    widget = PromptsWidget()
    p1 = PromptInfo(name="summarize", description="summarize", arguments=[])
    widget.set_prompts([p1])

    btn = Button("Get", id="btn-get-prompt")

    # Invalid JSON
    widget.args_input.text = "{invalid json"
    widget.on_button_pressed(Button.Pressed(btn))
    assert "Invalid JSON arguments" in str(widget.output_view.content)

    # Valid JSON
    messages: list[GetPromptRequested] = []
    widget.post_message = lambda m: messages.append(m) if isinstance(m, GetPromptRequested) else None  # type: ignore[method-assign]
    widget.args_input.text = '{"topic": "ai", "count": 5}'
    widget.on_button_pressed(Button.Pressed(btn))
    assert len(messages) == 1
    assert messages[0].prompt_name == "summarize"
    assert messages[0].args == {"topic": "ai", "count": "5"}

    # Output formatting
    widget.set_result({"description": "ok", "messages": [{"role": "user", "content": "hi"}]})
    assert "Rendered Prompt" in str(widget.output_view.content)

    widget.set_error("Prompt not found")
    assert "Prompt Error:" in str(widget.output_view.content)
    assert "Prompt not found" in str(widget.output_view.content)


@pytest.mark.anyio
async def test_app_resource_and_prompt_execution(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    app = McpBrowserApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.pause()
        entry = ServerEntry(
            id="srv-1",
            name="test-server",
            client_id="vscode",
            scope="user",
            config_path="/dummy/path",
            transport=StdioTransport(command="echo"),
        )
        app.selected_entry = entry

        # Resource read success and error
        res_mock = AsyncMock(return_value=[{"text": "mock resource output"}])
        monkeypatch.setattr(app.backend, "read_resource", res_mock)

        app.post_message(ReadResourceRequested("res://demo"))
        await pilot.pause()
        res_mock.assert_awaited_once_with(entry, "res://demo")
        res_widget = app.query_one(ResourcesWidget)
        assert "mock resource output" in str(res_widget.output_view.content)

        res_mock.side_effect = RuntimeError("Resource unavailable")
        app.post_message(ReadResourceRequested("res://err"))
        await pilot.pause()
        assert "Resource unavailable" in str(res_widget.output_view.content)

        # Prompt get success and error
        prompt_mock = AsyncMock(return_value={"result": "mock prompt response"})
        monkeypatch.setattr(app.backend, "get_prompt", prompt_mock)

        app.post_message(GetPromptRequested("test_prompt", {"k": "v"}))
        await pilot.pause()
        prompt_mock.assert_awaited_once_with(entry, "test_prompt", {"k": "v"})
        prompts_widget = app.query_one(PromptsWidget)
        assert "mock prompt response" in str(prompts_widget.output_view.content)

        prompt_mock.side_effect = RuntimeError("Prompt failed")
        app.post_message(GetPromptRequested("err_prompt", {}))
        await pilot.pause()
        assert "Prompt failed" in str(prompts_widget.output_view.content)
