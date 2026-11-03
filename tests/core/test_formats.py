"""Formats: indent/newline detection, comment scanning, TOML comment preservation."""

from __future__ import annotations

import pytest
from mcp_browser_core.formats import detect_indent, dump, has_comments, indent_unit, load, plain


@pytest.mark.parametrize(
    ("text", "width"),
    [('{\n  "a": 1\n}', 2), ('{\n    "a": 1\n}', 4), ('{"a": 1}', 2), ('{\n\t"a": 1\n}', 2), ("", 2)],
)
def test_detect_indent(text: str, width: int) -> None:
    assert detect_indent(text) == width


def test_indent_unit_tab() -> None:
    assert indent_unit('{\n\t"a": 1\n}') == "\t"
    assert indent_unit('{\n   "a": 1\n}') == 3


@pytest.mark.parametrize("newline", [True, False])
def test_json_roundtrip_keeps_order_indent_and_newline(newline: bool) -> None:
    text = '{\n    "z": 1,\n    "a": {"é": [1, 2]}\n}' + ("\n" if newline else "")
    doc = load(text, "json")
    out = dump(doc, "json", indent=detect_indent(text), newline=newline)
    assert list(load(out, "json")) == ["z", "a"]
    assert out.endswith("\n") == newline
    assert '    "z"' in out
    assert "é" in out


def test_empty_json_text_is_empty_object() -> None:
    assert load("", "json") == {}
    assert load("  \n", "jsonc") == {}


def test_jsonc_reads_comments_and_trailing_commas() -> None:
    doc = load('{\n // c\n "a": [1, 2,],\n /* b */ "b": "x//y",\n}', "jsonc")
    assert doc == {"a": [1, 2], "b": "x//y"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"url": "https://example.test/a//b"}', False),
        ('{"s": "say \\"// hi\\" /* not */"}', False),
        ('{"s": "back\\\\"} // real', True),
        ('{"a": 1} // trailing', True),
        ('{\n  // line\n  "a": 1\n}', True),
        ('{"a": /* inline */ 1}', True),
        ('{"a": "x"}', False),
        ("{'a': 'http://x'}", False),
        ("", False),
    ],
)
def test_has_comments_jsonc(text: str, expected: bool) -> None:
    assert has_comments(text, "jsonc") is expected


def test_has_comments_other_formats_are_false() -> None:
    assert has_comments('{"a": 1} // x', "json") is False
    assert has_comments("# c\na = 1\n", "toml") is False


def test_toml_preserves_comments_and_order() -> None:
    text = '# top\nb = 1  # tail\n\n[t]\n# inner\na = "x"\n'
    doc = load(text, "toml")
    doc["t"]["c"] = 2
    out = dump(doc, "toml")
    assert out.startswith("# top\nb = 1  # tail\n")
    assert '# inner\na = "x"' in out
    assert plain(load(out, "toml")) == {"b": 1, "t": {"a": "x", "c": 2}}


def test_plain_unwraps_tomlkit_and_passes_builtins() -> None:
    doc = load("a = [1, 2]\n[t]\nb = 'x'\n", "toml")
    assert type(plain(doc["t"])) is dict
    assert plain({"a": 1}) == {"a": 1}
