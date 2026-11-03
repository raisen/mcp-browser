"""Every fixture: parse each entry, render it onto the original raw, expect no change at all."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, cast

import pytest
from mcp_browser_core.dialects import get_dialect
from mcp_browser_core.formats import load, plain
from mcp_browser_core.models import ServerEntry
from mcp_browser_core.specs import REGISTRY

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "configs"
CASES = [
    ("claude-code", "claude-code.json"),
    ("claude-desktop", "claude-desktop.json"),
    ("codex", "codex.toml"),
    ("gemini", "gemini.json"),
    ("antigravity", "antigravity.json"),
    ("cursor", "cursor.json"),
    ("vscode", "vscode.jsonc"),
    ("windsurf", "windsurf.json"),
    ("zed", "zed.jsonc"),
    ("cline", "cline.json"),
]


def _entry(spec_id: str, name: str, raw: dict[str, Any]) -> ServerEntry:
    spec = REGISTRY[spec_id]
    transport, error, enabled, extra = get_dialect(spec.dialect).parse(name, raw, spec)
    return ServerEntry(
        id="x",
        name=name,
        client_id=spec_id,
        scope="user",
        config_path="/p",
        transport=transport,
        error=error,
        enabled=enabled,
        extra=extra,
    )


@pytest.mark.parametrize(("spec_id", "fixture"), CASES)
def test_render_onto_original_changes_nothing(spec_id: str, fixture: str) -> None:
    spec = REGISTRY[spec_id]
    dialect = get_dialect(spec.dialect)
    doc = load((FIXTURES / fixture).read_text(encoding="utf-8"), spec.format)
    root = dialect.root(doc, spec, "user", None, False)
    assert root
    for name, live in list(root.items()):
        before = copy.deepcopy(plain(live))
        entry = _entry(spec_id, str(name), cast("dict[str, Any]", plain(live)))
        out = dialect.render(entry, live, spec)
        assert plain(out) == before, name
        assert list(plain(out)) == list(before), f"{name}: key order changed"


@pytest.mark.parametrize(("spec_id", "fixture"), CASES)
def test_fresh_render_parses_back_to_same_entry(spec_id: str, fixture: str) -> None:
    spec = REGISTRY[spec_id]
    dialect = get_dialect(spec.dialect)
    doc = load((FIXTURES / fixture).read_text(encoding="utf-8"), spec.format)
    root = dialect.root(doc, spec, "user", None, False)
    assert root
    for name, live in root.items():
        entry = _entry(spec_id, str(name), cast("dict[str, Any]", plain(live)))
        if entry.transport is None:
            continue
        fresh = dialect.render(entry, None, spec)
        again = _entry(spec_id, str(name), fresh)
        assert again.transport == entry.transport, name
        assert again.enabled == entry.enabled, name


def test_get_dialect_unknown_name() -> None:
    with pytest.raises(KeyError):
        get_dialect("nope")
