from __future__ import annotations

import os
from pathlib import Path

from mcp_browser_core.expand import expand, expand_transport, parse_env_file, placeholder_names
from mcp_browser_core.models import HttpTransport, StdioTransport

HOME = Path("/h")
ENV = {"A": "1", "EMPTY": "", "TOKEN": "tok"}


def ex(text: str, project: str | None = "/proj") -> tuple[str, list[str]]:
    return expand(text, ENV, project=project, home=HOME)


def test_forms() -> None:
    assert ex("${A}-$A-${env:A}-%TOKEN%") == ("1-1-1-tok", [])
    assert ex("${MISSING:-dflt}") == ("dflt", [])
    assert ex("${EMPTY:-dflt}") == ("dflt", [])
    assert ex("${EMPTY}") == ("", [])
    assert ex("${userHome}${pathSeparator}x") == (f"{HOME}{os.sep}x", [])
    assert ex("${workspaceFolder}/s") == ("/proj/s", [])


def test_unresolved_stay_verbatim_and_are_listed() -> None:
    text, bad = ex("${NOPE} $ALSO ${env:THIRD} ${NOPE}")
    assert text == "${NOPE} $ALSO ${env:THIRD} ${NOPE}"
    assert bad == ["NOPE", "ALSO", "THIRD"]
    assert ex("${workspaceFolder}", project=None)[1] == ["workspaceFolder"]
    assert ex("${input:api-key}")[1] == ["input:api-key"]


def test_percent_and_urls_are_not_false_positives() -> None:
    assert ex("http://x/a%20b%2Fc") == ("http://x/a%20b%2Fc", [])
    assert ex("%unknown%") == ("%unknown%", [])


def test_stdio_transport_expands_everything_and_loads_env_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("# c\nexport K1=v1\nK2='v 2'\nA=fromfile\n\nbad line\n", encoding="utf-8")
    t = StdioTransport(
        command="${A}run",
        args=["--t", "${TOKEN}"],
        env={"A": "${TOKEN}", "X": "$A"},
        cwd="${workspaceFolder}",
        env_file=".env",
    )
    out, bad = expand_transport(t, ENV, project=str(tmp_path), home=HOME)
    assert bad == []
    assert isinstance(out, StdioTransport)
    assert (out.command, out.args, out.cwd, out.env_file) == ("1run", ["--t", "tok"], str(tmp_path), None)
    assert out.env == {"K1": "v1", "K2": "v 2", "A": "tok", "X": "1"}  # entry env wins over the file


def test_missing_env_file_is_reported(tmp_path: Path) -> None:
    t = StdioTransport(command="c", env_file=str(tmp_path / "nope.env"))
    assert expand_transport(t, ENV, project=None, home=HOME)[1] == ["envFile:nope.env"]


def test_http_transport() -> None:
    t = HttpTransport(url="https://h/${A}", headers={"Authorization": "Bearer ${TOKEN}", "X": "${GONE}"})
    out, bad = expand_transport(t, ENV, project=None, home=HOME)
    assert isinstance(out, HttpTransport)
    assert out.url == "https://h/1" and out.headers["Authorization"] == "Bearer tok"
    assert bad == ["GONE"]


def test_parse_env_file() -> None:
    assert parse_env_file('A=1\n#c\nB="x=y"\n') == {"A": "1", "B": "x=y"}


def test_placeholder_names_lists_variables_only() -> None:
    text = "${A} $B ${env:C:-d} %D% ${userHome} ${workspaceFolder} ${input:x}"
    assert placeholder_names(text) == ["A", "B", "C", "D"]
