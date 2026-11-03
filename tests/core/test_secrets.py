"""Masking rules and the masked-value guard."""

from __future__ import annotations

from typing import Any

from mcp_browser_core.models import EntryPatch, HttpTransport, NewEntry, ServerEntry, StdioTransport
from mcp_browser_core.secrets import MASK, contains_mask, mask_args, mask_entry, mask_url


def _entry(transport: StdioTransport | HttpTransport, extra: dict[str, Any] | None = None) -> ServerEntry:
    return ServerEntry(
        id="i",
        name="n",
        client_id="c",
        scope="user",
        config_path="/p",
        transport=transport,
        extra=extra or {},
    )


def test_env_and_headers_values_masked_keys_kept() -> None:
    out = mask_entry(_entry(StdioTransport(command="x", env={"A": "1", "B": ""})))
    assert isinstance(out.transport, StdioTransport)
    assert out.transport.env == {"A": MASK, "B": MASK}
    http = mask_entry(_entry(HttpTransport(url="https://h.test/m", headers={"Authorization": "Bearer s"})))
    assert isinstance(http.transport, HttpTransport)
    assert http.transport.headers == {"Authorization": MASK}


def test_original_entry_is_not_modified() -> None:
    original = _entry(StdioTransport(command="x", env={"A": "1"}))
    mask_entry(original)
    assert isinstance(original.transport, StdioTransport)
    assert original.transport.env == {"A": "1"}


def test_url_userinfo_and_secret_query_values() -> None:
    assert mask_url("https://user:pw@h.test/p") == f"https://{MASK}@h.test/p"
    assert mask_url("https://h.test/p?api_key=abc&mode=ro&Token=z") == (
        f"https://h.test/p?api_key={MASK}&mode=ro&Token={MASK}"
    )
    assert mask_url("https://h.test/p?mode=ro") == "https://h.test/p?mode=ro"
    assert mask_url("https://h.test/a//b") == "https://h.test/a//b"


def test_args_flags() -> None:
    args = ["-y", "pkg", "--api-key", "abc", "--token=xyz", "--verbose", "--password", "--next", "ok"]
    assert mask_args(args) == [
        "-y",
        "pkg",
        "--api-key",
        MASK,
        f"--token={MASK}",
        "--verbose",
        "--password",
        "--next",
        "ok",
    ]


def test_secret_extra_keys() -> None:
    extra = {
        "bearer_token_env_var": "MY_VAR",
        "env_http_headers": {"X-A": "VAR"},
        "oauth": {"clientId": "id", "scopes": ["a", "b"], "nested": {"k": "v"}},
        "startup_timeout_sec": 20,
    }
    out = mask_entry(_entry(StdioTransport(command="x"), extra)).extra
    assert out["bearer_token_env_var"] == MASK
    assert out["env_http_headers"] == {"X-A": MASK}
    assert out["oauth"] == {"clientId": MASK, "scopes": [MASK, MASK], "nested": {"k": MASK}}
    assert out["startup_timeout_sec"] == 20


def test_http_oauth_masked() -> None:
    t = HttpTransport(url="https://h.test", oauth={"client_secret": "s"})
    out = mask_entry(_entry(t))
    assert isinstance(out.transport, HttpTransport)
    assert out.transport.oauth == {"client_secret": MASK}


def test_contains_mask() -> None:
    assert contains_mask(NewEntry(name="a", transport=StdioTransport(command="x", env={"K": MASK})))
    assert contains_mask(EntryPatch(extra={"deep": [{"v": MASK}]}))
    assert contains_mask(NewEntry(name="a", transport=HttpTransport(url=f"https://{MASK}@h.test")))
    assert contains_mask(NewEntry(name="a", transport=StdioTransport(command="x", args=[f"--t={MASK}"])))
    assert not contains_mask(NewEntry(name="a", transport=StdioTransport(command="x", env={"K": "v"})))
    assert not contains_mask(EntryPatch())
    assert contains_mask(MASK) and contains_mask({MASK: 1}) and not contains_mask(None)


def test_key_value_and_env_flag_args_are_masked() -> None:
    assert mask_args(["run", "-e", "GITHUB_TOKEN=abc", "-e", "DEBUG=1", "--env=API_KEY=zzz"]) == [
        "run",
        "-e",
        f"GITHUB_TOKEN={MASK}",
        "-e",
        "DEBUG=1",
        f"--env=API_KEY={MASK}",
    ]
    assert mask_args(["MY_SECRET=x", "NAME=v"]) == [f"MY_SECRET={MASK}", "NAME=v"]


def test_header_args_keep_the_name_readable() -> None:
    out = mask_args(["-H", "Authorization: Bearer abc123", "--header", "X-Api-Key: k", "-H", "Accept: json"])
    assert out == [
        "-H",
        f"Authorization: Bearer {MASK}",
        "--header",
        f"X-Api-Key: {MASK}",
        "-H",
        "Accept: json",
    ]


def test_token_like_url_path_segments_are_masked() -> None:
    token = "aB3dE5gH7jK9mN1pQ3rS5tU7"
    assert mask_url(f"https://h.test/v1/{token}/mcp") == f"https://h.test/v1/{MASK}/mcp"
    assert mask_url("https://h.test/api/v1/servers/documentation-endpoint") == (
        "https://h.test/api/v1/servers/documentation-endpoint"
    )
