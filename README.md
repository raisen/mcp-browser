# MCP Browser

[![Website](https://img.shields.io/badge/website-mcpbrowser.weydson.com-blue?style=flat-square)](https://mcpbrowser.weydson.com)
[![GitHub Release](https://img.shields.io/github/v/release/raisen/mcp-browser?style=flat-square)](https://github.com/raisen/mcp-browser/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/raisen/mcp-browser/ci.yml?branch=main&label=CI&style=flat-square)](https://github.com/raisen/mcp-browser/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](https://github.com/raisen/mcp-browser/blob/main/LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)

A local web dashboard and native macOS app to browse, search, test, and safely configure Model Context Protocol (MCP) servers across all your AI coding assistants.

![MCP Browser](docs/screenshots/server-list.png)

- **See everything in one place:** Discovers MCP servers across Claude Code, Claude Desktop, Cursor, VS Code, Windsurf, Zed, Codex, Gemini CLI, Antigravity, and Cline.
- **Connect and test:** Inspect tools, resources, and prompts live in the browser using dynamically generated JSON Schema forms.
- **Safe atomic editing:** Configure servers across multiple clients simultaneously with atomic file swaps, automatic timestamped backups before every write, comment preservation, and secret masking (`•••`).
- **Private and local:** Binds strictly to `127.0.0.1`, protected by random token authentication, with zero external network requests or telemetry.

---

## Quick start

Python 3.11+ is required for terminal installation via `uv` or `pip`. The native macOS `.dmg` and standalone binaries require zero runtime dependencies or Python setup.

### macOS Native App (.dmg)
Download the latest disk image from [Releases](https://github.com/raisen/mcp-browser/releases) (`macos-arm64` for Apple Silicon or `macos-x86_64` for Intel). Open the `.dmg`, drag `MCP Browser.app` to `/Applications`, and run it.
- Menu bar controls (status icon, one-click start/stop, log viewer)
- Auto-updates on launch and on demand
- Signed with Apple Developer ID, notarized by Apple, and ticket stapled

### With Astral uv (Recommended for CLI)
```sh
uv tool install mcp-browser
mcp-browser
```

### With Standard pip
```sh
pip install mcp-browser
mcp-browser
```

### Prebuilt Standalone Binaries (No Python Needed)
Self-contained zip archives for macOS, Windows, and Linux are available on the [Releases](https://github.com/raisen/mcp-browser/releases) page. For Windows SmartScreen notes and SHA-256 verification, see [Binary Integrity & Checksums](docs/security.md#binary-integrity-and-verification).

---

## Commands

| Command | What it does |
| :--- | :--- |
| `mcp-browser` or `mcp-browser serve` | Run in the foreground, print the URL, and open your browser (`Ctrl+C` to stop) |
| `mcp-browser start` | Run in the background as a daemon and open your browser |
| `mcp-browser stop` | Stop the verified background server process |
| `mcp-browser status` | Print running or stopped status (exit code 0 or 1) |
| `mcp-browser open` | Open the web dashboard of the running server |

Options: `--port N` (default `8765`) and `--no-open`.

👉 *For background daemon mechanics, port conflict detection, state folder locations, and environment variables, see [CLI & Daemon Reference](docs/cli.md).*

---

## Supported Clients

MCP Browser resolves user-level and project-level configuration files across:

- **Claude Code** (`~/.claude.json`, `.mcp.json`)
- **Claude Desktop** (`claude_desktop_config.json`)
- **Cursor** (`~/.cursor/mcp.json`, `.cursor/mcp.json`)
- **VS Code** (`mcp.json`, `.vscode/mcp.json`)
- **Windsurf** (`mcp_config.json`)
- **Zed** (`settings.json`, `.zed/settings.json`)
- **Codex** (`~/.codex/config.toml`, `.codex/config.toml`)
- **Gemini CLI** (`settings.json`)
- **Antigravity** (`mcp_config.json`)
- **Cline** (`cline_mcp_settings.json`)
- Claude Code plugins and Claude Desktop extensions *(read-only)*

👉 *For complete OS paths, transport support, custom path overrides (`paths.json`), and atomic write mechanics, see [Supported Clients & Safe Editing](docs/clients.md).*

---

## Security at a Glance

- **Loopback only:** Binds strictly to `127.0.0.1`. Rejects foreign `Host` and `Origin` headers to block DNS rebinding.
- **Bearer token:** Ephemeral authentication token stored with mode `0600` and passed via the URL hash fragment (`#token=...`), never transmitted in HTTP requests or logged.
- **Untrusted workspace safeguards:** Project-level server configs (`.mcp.json`, etc.) require explicit confirmation before connecting or reading.
- **Zero telemetry:** Secrets are masked in UI and scrubbed from stderr; nothing leaves your machine.

👉 *For the comprehensive threat model, untrusted workspace isolation, and binary integrity details, see [Security Architecture](docs/security.md).*

---

## Documentation

- 📖 **[Supported Clients & Safe Editing](docs/clients.md)** — Config file paths across macOS/Linux/Windows, atomic write engine, backup rotation, and comment preservation.
- 🛡️ **[Security Architecture & Integrity](docs/security.md)** — Local-only threat model, untrusted workspace isolation, Apple notarization, and checksum verification.
- 💻 **[CLI & Daemon Reference](docs/cli.md)** — Background services, state directories, port squatting protection, and headless usage.
- 🛠️ **[Developer Guide & Contributing](docs/development.md)** — Devcontainer, Makefile targets, testing, code standards, and how to add a client.

---

## Development

```sh
git clone https://github.com/raisen/mcp-browser && cd mcp-browser
uv sync --all-packages
make check   # runs lint, format check, pyright, pytest, and line limits
```

👉 *For devcontainer workflows, package architecture, and contributing guidelines, see the [Developer Guide](docs/development.md).*

---

## License

MIT. See [LICENSE](LICENSE).
