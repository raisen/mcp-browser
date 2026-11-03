"""What the confirmation dialog shows: names of variables, never values."""

from __future__ import annotations

from mcp_browser_core.models import HttpTransport, ServerEntry, StdioTransport, Transport
from mcp_browser_core.trust import confirmation_detail


def entry(t: Transport, **extra: object) -> ServerEntry:
    return ServerEntry(
        id="i",
        name="n",
        client_id="codex",
        scope="project",
        config_path="/p",
        transport=t,
        extra=dict(extra),
        untrusted=True,
    )


def test_remote_lists_codex_variable_names_and_host() -> None:
    t = HttpTransport(url="https://user:pw@h.example.invalid:8443/x", headers={"X": "${HDR_VAR}"})
    d = confirmation_detail(
        entry(t, bearer_token_env_var="BEARER_VAR", env_http_headers={"X-Key": "MAPPED_VAR"})
    )
    assert d["host"] == "h.example.invalid:8443"
    assert d["env_vars"] == ["HDR_VAR", "BEARER_VAR", "MAPPED_VAR"]


def test_stdio_lists_references_in_args_env_cwd_and_passthrough() -> None:
    t = StdioTransport(
        command="run", args=["--k", "$ARG_VAR"], env={"E": "${env:ENV_VAR}"}, cwd="%CWD_VAR%/x"
    )
    d = confirmation_detail(entry(t, env_vars=["PASS_ONE", {"name": "PASS_TWO"}]))
    assert d["command"] == "run" and d["args"] == ["--k", "$ARG_VAR"] and d["host"] is None
    assert d["env_vars"] == ["ARG_VAR", "ENV_VAR", "CWD_VAR", "PASS_ONE", "PASS_TWO"]
