"""Browsers request /favicon.ico unasked; it needs the token, so the console showed a 401."""

from __future__ import annotations

from starlette.testclient import TestClient


def test_favicon_path_needs_the_token(anon: TestClient) -> None:
    assert anon.get("/favicon.ico").status_code == 401


def test_index_declares_an_inline_icon_so_no_favicon_request_is_made(anon: TestClient) -> None:
    html = anon.get("/").text
    assert '<link rel="icon" href="data:,">' in html
