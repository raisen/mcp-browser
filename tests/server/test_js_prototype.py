"""A hostile server's tool/prompt names must never reach Object.prototype (runs the real JS with node)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import mcp_browser_server
import pytest

JS = Path(mcp_browser_server.__file__).parent / "static" / "js"
SCRIPT = """
import { buildForm, toArgs } from "%(js)s/schema_form.js";
import { detailActions } from "%(js)s/detail_actions.js";

const schema = JSON.parse(`{"type": "object", "properties": {
  "__proto__": {"type": "object", "properties": {"polluted": {"type": "string"}}},
  "constructor": {"type": "string"}}}`);
const form = buildForm(schema, JSON.parse('{"__proto__": {"polluted": "yes"}, "constructor": "c"}'));
form.fields[0].children[0].value = "yes";
const args = toArgs(form);
if (Object.getPrototypeOf(args) !== null) throw new Error("args has a prototype");
if (!Object.hasOwn(args, "__proto__")) throw new Error("the __proto__ key was dropped");

const ctx = { promptArgs: detailActions.promptArgs, ...detailActions };
ctx.initArgs("__proto__");
ctx.promptArgs["__proto__"]["polluted"] = "yes";
ctx.initArgs("toString");
if ({}.polluted !== undefined || Object.prototype.polluted !== undefined) throw new Error("polluted");
console.log("ok");
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_hostile_names_do_not_pollute_object_prototype() -> None:
    run = subprocess.run(
        ["node", "--input-type=module", "-e", SCRIPT % {"js": JS.as_uri()}],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert run.returncode == 0 and "ok" in run.stdout, run.stderr


def test_templates_no_longer_index_prompt_args_with_a_plain_object() -> None:
    assert "promptArgs[p.name] ??= {}" not in (JS / "views" / "detail.js").read_text(encoding="utf-8")
