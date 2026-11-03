"""Comprehensive test suite for the mcpbrowser.weydson.com static site."""

import functools
import http.server
import re
import socket
import threading
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent.parent / "site"


def run_tests():
    # 1. Find a free port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"
    print(f"Testing server running at {base_url} serving {SITE_DIR}")

    assets_to_test = [
        ("/", 200, "text/html"),
        ("/index.html", 200, "text/html"),
        ("/index.md", 200, "text/markdown"),
        ("/llms.txt", 200, "text/plain"),
        ("/llms-full.txt", 200, "text/plain"),
        ("/CNAME", 200, None),
        ("/robots.txt", 200, "text/plain"),
        ("/sitemap.xml", 200, None),
        ("/favicon.svg", 200, "image/svg+xml"),
        ("/css/pico.min.css", 200, "text/css"),
        ("/css/custom.css", 200, "text/css"),
        ("/js/main.js", 200, None),
        ("/images/screenshots/server-list.png", 200, "image/png"),
        ("/images/screenshots/server-list-dark.png", 200, "image/png"),
        ("/images/screenshots/server-detail.png", 200, "image/png"),
        ("/images/screenshots/server-detail-dark.png", 200, "image/png"),
        ("/images/screenshots/add-server.png", 200, "image/png"),
        ("/images/logo.png", 200, "image/png"),
    ]

    for path, expected_status, content_type_substr in assets_to_test:
        url = base_url + path
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()
            assert status == expected_status, f"Expected {expected_status} for {path}, got {status}"
            if content_type_substr:
                assert content_type_substr in content_type, (
                    f"Expected {content_type_substr} in {content_type} for {path}"
                )
            assert len(data) > 0, f"Empty response for {path}"
            print(f"✓ {path}: {status} ({len(data)} bytes, {content_type})")

    # 2. Check CNAME content
    cname_content = (SITE_DIR / "CNAME").read_text().strip()
    assert cname_content == "mcpbrowser.weydson.com", f"Unexpected CNAME: {cname_content}"
    print(f"✓ CNAME content matches: {cname_content}")

    # 3. Check robots.txt
    robots_content = (SITE_DIR / "robots.txt").read_text()
    assert "Sitemap: https://mcpbrowser.weydson.com/sitemap.xml" in robots_content
    print("✓ robots.txt points to sitemap")

    # 4. Check sitemap.xml
    sitemap_content = (SITE_DIR / "sitemap.xml").read_text()
    root = ET.fromstring(sitemap_content)
    urls = [elem.text for elem in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert "https://mcpbrowser.weydson.com/" in urls
    assert "https://mcpbrowser.weydson.com/index.md" in urls
    assert "https://mcpbrowser.weydson.com/llms.txt" in urls
    assert "https://mcpbrowser.weydson.com/llms-full.txt" in urls
    print(f"✓ sitemap.xml valid with {len(urls)} URLs")

    # 5. Check index.html requirements
    html = (SITE_DIR / "index.html").read_text()

    # Canonical URL
    assert '<link rel="canonical" href="https://mcpbrowser.weydson.com/">' in html, "Missing canonical link"
    print("✓ Canonical URL present")

    # Strict SEO: zero social media
    assert "og:" not in html, "Found og: OpenGraph tags! STRICT SEO requires zero social media tags."
    assert "twitter:" not in html, "Found twitter: tags! STRICT SEO requires zero social media tags."
    print("✓ Strict SEO verified: zero social media tags found")

    # Meta tags
    assert '<meta name="author" content="Weydson">' in html
    assert '<meta name="robots" content="index, follow">' in html
    assert "MCP Browser" in html
    print("✓ Author, robots, and title verified")

    # Schema.org JSON-LD
    assert "application/ld+json" in html
    assert "SoftwareApplication" in html
    assert "WebSite" in html
    print("✓ Schema.org JSON-LD markup verified")

    # LLM alternate tags
    assert '<link rel="alternate" type="text/markdown" href="/llms.txt"' in html
    assert '<link rel="alternate" type="text/markdown" href="/index.md"' in html
    assert '<script type="text/markdown">' in html
    print("✓ LLM alternate links and embedded markdown script tag verified")

    # Analytics: Umami
    assert 'src="https://insights.raisenllc.com/script.js"' in html
    assert 'data-website-id="c3f46a00-e114-472e-a2af-8d8b6492650d"' in html
    assert 'data-domains="mcpbrowser.weydson.com"' in html
    print("✓ Umami analytics script and website ID verified")

    # Section comment headers
    expected_headers = [
        "<!-- Header & Navigation -->",
        "<!-- Hero -->",
        "<!-- Key Highlights -->",
        "<!-- Screenshots Gallery -->",
        "<!-- Terminal Installation -->",
        "<!-- Standalone Downloads -->",
        "<!-- Supported Clients -->",
        "<!-- Security & Safety Architecture -->",
        "<!-- CLI Reference -->",
        "<!-- Lightbox Modal -->",
        "<!-- Footer -->",
        "<!-- Embedded LLM-Friendly Markdown -->",
    ]
    for header in expected_headers:
        assert header in html, f"Missing expected section header: {header}"
    print("✓ All clean section comment headers present")

    # Direct links to binaries
    binaries = [
        "https://github.com/raisen/mcp-browser/releases/latest/download/mcp-browser-0.1.0-macos-arm64.dmg",
        "https://github.com/raisen/mcp-browser/releases/latest/download/mcp-browser-0.1.0-macos-arm64.zip",
        "https://github.com/raisen/mcp-browser/releases/latest/download/mcp-browser-0.1.0-macos-x86_64.dmg",
        "https://github.com/raisen/mcp-browser/releases/latest/download/mcp-browser-0.1.0-macos-x86_64.zip",
        "https://github.com/raisen/mcp-browser/releases/latest/download/mcp-browser-0.1.0-windows-x86_64.zip",
        "https://github.com/raisen/mcp-browser/releases/latest/download/mcp-browser-0.1.0-linux-x86_64.zip",
        "https://github.com/raisen/mcp-browser/releases/latest/download/SHA256SUMS.txt",
        "https://github.com/raisen/mcp-browser/releases",
        "https://pypi.org/project/mcp-browser/",
    ]
    for bin_url in binaries:
        assert bin_url in html, f"Missing binary/release link: {bin_url}"
    print("✓ All 7 binary/app links and release/PyPI URLs verified")

    # Terminal commands
    commands = [
        "uv tool install mcp-browser && mcp-browser",
        "pip install mcp-browser && mcp-browser",
        (  # git clone snippet
            "git clone https://github.com/raisen/mcp-browser && "
            "cd mcp-browser && uv sync --all-packages && uv run mcp-browser"
        ),
    ]
    for cmd in commands:
        # Check both text or encoded ampersand
        cmd_encoded = cmd.replace("&", "&amp;")
        assert cmd in html or cmd_encoded in html, f"Missing command: {cmd}"
    print("✓ All terminal copy snippets verified")

    # Check all internal link targets exist
    src_and_href = re.findall(r'(?:src|href)=["\']([^"\']+)["\']', html)
    for target in src_and_href:
        if target.startswith("http") or target.startswith("#") or target.startswith("data:"):
            continue
        cleaned = target.lstrip("/")
        local_file = SITE_DIR / cleaned
        assert local_file.exists(), f"Broken internal link/src in index.html: {target} -> {local_file}"
    print("✓ All internal references (CSS, JS, images, links) exist on disk")

    # Check interactive gallery cards and theme toggles
    gallery_card_count = html.count('class="gallery-card"')
    assert gallery_card_count == 3, f"Expected 3 gallery cards, found {gallery_card_count}"
    assert "Server Discovery Dashboard" in html
    assert "Interactive Tool Runner &amp; Playground" in html
    assert "Multi-Client Configuration" in html
    assert 'class="card-theme-toggle"' in html
    assert 'data-theme="light"' in html
    assert 'data-theme="dark"' in html
    assert "style=" not in html, "Found inline style attribute! Strict CSS separation required."
    print("✓ Unified interactive screenshot cards and theme toggles verified")

    # Check llms.txt & llms-full.txt
    llms_txt = (SITE_DIR / "llms.txt").read_text()
    assert llms_txt.startswith("# MCP Browser")
    assert "> A local web page" in llms_txt
    print("✓ llms.txt format adheres to https://llmstxt.org specification")

    llms_full = (SITE_DIR / "llms-full.txt").read_text()
    assert len(llms_full) > 2000
    print(f"✓ llms-full.txt comprehensive guide verified ({len(llms_full)} bytes)")

    index_md = (SITE_DIR / "index.md").read_text()
    assert len(index_md) > 1000
    print(f"✓ index.md markdown mirror verified ({len(index_md)} bytes)")

    server.shutdown()
    print("\n🎉 ALL STATIC SITE VERIFICATION TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_tests()
