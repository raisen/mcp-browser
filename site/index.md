# MCP Browser

> Browse, test, and manage every Model Context Protocol (MCP) server across all your AI coding assistants.

A local, private web interface that discovers servers configured in Claude Code, Claude Desktop, Cursor, VS Code, Windsurf, Zed, Codex, Gemini CLI, Antigravity, and Cline. Connect to stdio and SSE servers, execute tools through dynamically generated JSON Schema forms, and update configuration files atomically with automatic backups.

- **Canonical URL**: https://mcpbrowser.weydson.com/
- **GitHub**: https://github.com/raisen/mcp-browser
- **Releases**: https://github.com/raisen/mcp-browser/releases
- **PyPI**: https://pypi.org/project/mcp-browser/
- **LLM Index**: https://mcpbrowser.weydson.com/llms.txt
- **LLM Technical Reference**: https://mcpbrowser.weydson.com/llms-full.txt

---

## Quick Installation

### Astral uv (Recommended)

```sh
uv tool install mcp-browser && mcp-browser
```

### Python pip

```sh
pip install mcp-browser && mcp-browser
```

### From Source

```sh
git clone https://github.com/raisen/mcp-browser && cd mcp-browser && uv sync --all-packages && uv run mcp-browser
```

---

## Standalone Prebuilt Binaries (v0.1.0)

Prebuilt binaries require no Python installation.

| Platform | Architecture | Package Archive |
|---|---|---|
| macOS | Apple Silicon (arm64) | [mcp-browser-0.1.0-macos-arm64.zip](https://github.com/raisen/mcp-browser/releases/latest/download/mcp-browser-0.1.0-macos-arm64.zip) |
| macOS | Intel (x86_64) | [mcp-browser-0.1.0-macos-x86_64.zip](https://github.com/raisen/mcp-browser/releases/latest/download/mcp-browser-0.1.0-macos-x86_64.zip) |
| Windows | x86_64 | [mcp-browser-0.1.0-windows-x86_64.zip](https://github.com/raisen/mcp-browser/releases/latest/download/mcp-browser-0.1.0-windows-x86_64.zip) |
| Linux | x86_64 | [mcp-browser-0.1.0-linux-x86_64.zip](https://github.com/raisen/mcp-browser/releases/latest/download/mcp-browser-0.1.0-linux-x86_64.zip) |
| All | Checksums | [SHA256SUMS.txt](https://github.com/raisen/mcp-browser/releases/latest/download/SHA256SUMS.txt) |

### macOS Gatekeeper Note

PyInstaller binaries are not Apple-signed. Run this command after unzipping:

```sh
xattr -dr com.apple.quarantine mcp-browser
```

Or navigate to System Settings -> Privacy & Security -> Click "Open Anyway".

### Windows SmartScreen Note

To unblock the executable in PowerShell:

```powershell
Unblock-File -Path .\mcp-browser\mcp-browser.exe
```

---

## Core Features

1. **Unified Server Discovery**: Automatically discovers MCP servers from user configurations and local repository configurations across 10+ AI tools.
2. **Interactive Playground**: Inspect tools, prompts, and resources. Automatically generates schema-validated HTML input forms to test tool calls directly in the browser.
3. **Atomic Multi-Client Writes**: Configure an MCP server once and apply it to multiple client configurations simultaneously. Creates timestamped backups (retaining the 20 most recent copies per file) before every write.
4. **Hardened Local Security**: Binds exclusively to loopback (`127.0.0.1`), passes bearer tokens in URL hash fragments (`#token=...`), rejects foreign `Host` and `Origin` headers to prevent DNS rebinding, and protects against untrusted repository configs.
5. **Zero Telemetry & Private Secrets**: Masks sensitive keys and tokens (`•••`), scrubs stdout/stderr logs, and transmits no analytics or data to external servers.

---

## Screenshots

- **Server Discovery (Light Mode)**: Overview of all discovered servers and their transport status (`images/screenshots/server-list.png`)
- **Server Discovery (Dark Mode)**: Dark theme overview with filtering and client chips (`images/screenshots/server-list-dark.png`)
- **Server Detail & Tool Execution (Light Mode)**: Interactive schema form and live tool response (`images/screenshots/server-detail.png`)
- **Server Detail & Tool Execution (Dark Mode)**: Dark theme interactive tool playground (`images/screenshots/server-detail-dark.png`)
- **Add Server to Multiple Clients**: Multi-target selection and safe atomic writer (`images/screenshots/add-server.png`)

---

## Supported AI Coding Clients

| Client | Config Location | Project Config | Transports |
|---|---|---|---|
| Claude Code | `~/.claude.json` | `.mcp.json` | stdio, SSE |
| Claude Desktop | `claude_desktop_config.json` | None | stdio |
| Cursor | `~/.cursor/mcp.json` | `.cursor/mcp.json` | stdio, SSE |
| VS Code | `Code/User/mcp.json` | `.vscode/mcp.json` | stdio, SSE |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | None | stdio, SSE |
| Zed | `settings.json` | `.zed/settings.json` | stdio, SSE |
| Codex | `~/.codex/config.toml` | `.codex/config.toml` | stdio |
| Gemini CLI | `~/.gemini/settings.json` | `.gemini/settings.json` | stdio, SSE |
| Antigravity | `mcp_config.json` | None | stdio, SSE |
| Cline | `cline_mcp_settings.json` | None | stdio, SSE |
| Claude Code Plugins | `installed_plugins.json` (read-only) | None | stdio, SSE |
| Claude Desktop Extensions | `manifest.json` (read-only) | None | stdio |

---

## CLI Reference

| Command | Action |
|---|---|
| `mcp-browser` | Launch foreground server and open default browser |
| `mcp-browser serve` | Explicit foreground server command |
| `mcp-browser start` | Run server in background as a daemon |
| `mcp-browser stop` | Gracefully stop the verified running daemon |
| `mcp-browser status` | Print daemon status (exit code 0 if running) |
| `mcp-browser open` | Open browser to the running instance with token |

Flags:
- `--port <N>`: Set loopback port (default: `8765`)
- `--no-open`: Suppress automatic browser launch

---

## License

MIT License. Copyright (c) Weydson.
