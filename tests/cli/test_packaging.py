"""Release gate and build recipe sanity (no PyInstaller run here)."""

from __future__ import annotations

import importlib.util
import itertools
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest
from mcp_browser_core import __version__

ROOT = Path(__file__).resolve().parents[2]


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "packaging" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def make_repo(root: Path, versions: dict[str, str], pin: str) -> None:
    for name, version in versions.items():
        folder = root / "packages" / name
        folder.mkdir(parents=True)
        deps = f'["mcp-browser-core=={pin}"]' if name != "core" else "[]"
        text = f'[project]\nname = "mcp-browser-{name}"\nversion = "{version}"\ndependencies = {deps}\n'
        (folder / "pyproject.toml").write_text(text, encoding="utf-8")


def test_repo_versions_match_package_version() -> None:
    assert load("check_version").problems(f"v{__version__}") == []


def test_mismatched_tag_is_reported() -> None:
    found = load("check_version").problems("v9.9.9")
    assert len(found) >= 3


def test_mismatched_package_or_pin_is_reported(tmp_path: Path) -> None:
    make_repo(tmp_path, {"core": "1.0.0", "server": "1.0.1", "cli": "1.0.0"}, pin="0.9.0")
    found = load("check_version").problems("v1.0.0", tmp_path)
    assert any("server is 1.0.1" in line for line in found)
    assert any("pins" in line for line in found)


def test_matching_tree_passes(tmp_path: Path) -> None:
    make_repo(tmp_path, {"core": "1.0.0", "server": "1.0.0", "cli": "1.0.0"}, pin="1.0.0")
    assert load("check_version").problems("v1.0.0", tmp_path) == []


def test_pyinstaller_flags_follow_the_plan(tmp_path: Path) -> None:
    args = load("build").pyinstaller_args(tmp_path / "dist", tmp_path / "work")
    assert "--onedir" in args
    pairs = list(itertools.pairwise(args))
    assert ("--collect-data", "mcp_browser_server") in pairs
    assert ("--collect-submodules", "uvicorn") in pairs
    assert ("--collect-all", "pydantic_core") in pairs
    assert args[-1].endswith("pyinstaller_entry.py")
    assert str(ROOT) not in args[args.index("--workpath") + 1]  # build files stay out of the repo


@pytest.mark.parametrize("workflow", ["ci.yml", "release.yml"])
def test_workflows_pin_verified_action_versions(workflow: str) -> None:
    text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    uses = re.findall(r"uses: (\S+)@(\S+)(?: # (v\S+))?", text)
    assert {name for name, _, _ in uses} == {"actions/checkout", "astral-sh/setup-uv"}
    for _, ref, comment in uses:
        assert re.fullmatch(r"[0-9a-f]{40}", ref), "actions must be pinned to a full commit SHA"
        assert comment, "keep the version as a comment"
    assert "# v7.0.1" in text
    assert "# v10.3.3" in text
    for match in re.findall(r"--with (pyinstaller\S*)", text):
        assert re.fullmatch(r"pyinstaller==\d+(\.\d+)+", match)


def test_sse_starlette_is_not_bundled() -> None:
    assert "sse_starlette" not in load("build").HIDDEN_IMPORTS
