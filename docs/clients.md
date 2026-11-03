# Supported Clients & Safe Editing Engine

[← Back to README](../README.md)

MCP Browser discovers, inspects, and safely edits Model Context Protocol (MCP) server configurations across major AI coding assistants and editors.

---

## Supported Clients & Config Paths

Configuration files are resolved across your operating system (`~` is your home directory, `%USERPROFILE%` on Windows). The first existing user config file is used. Project files are discovered in the current working directory and across all workspaces known to Claude Code.

| Client | User Config (macOS / Linux / Windows) | Project Config | Transports Supported |
| :--- | :--- | :--- | :--- |
| **Claude Code** | `~/.claude.json` (or `$CLAUDE_CONFIG_DIR/.claude.json`) | `.mcp.json` | `stdio`, `sse` |
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json`<br>`~/.config/Claude/claude_desktop_config.json`<br>`%APPDATA%\Claude\claude_desktop_config.json` | *None* | `stdio` only |
| **Cursor** | `~/.cursor/mcp.json` | `.cursor/mcp.json` | `stdio`, `sse` |
| **VS Code** | `~/Library/Application Support/Code/User/mcp.json`<br>`~/.config/Code/User/mcp.json`<br>`%APPDATA%\Code\User\mcp.json` | `.vscode/mcp.json` | `stdio`, `sse` |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` | *None* | `stdio`, `sse` |
| **Zed** | `~/.config/zed/settings.json`<br>(Windows: `%APPDATA%\Zed\settings.json`) | `.zed/settings.json` | `stdio`, `sse` |
| **Codex** | `~/.codex/config.toml` (or `$CODEX_HOME`) | `.codex/config.toml` | `stdio` only |
| **Gemini CLI** | `~/.gemini/settings.json` | `.gemini/settings.json` | `stdio`, `sse` |
| **Antigravity** | `~/.gemini/config/mcp_config.json` or `~/.gemini/antigravity/mcp_config.json` | *None* | `stdio`, `sse` |
| **Cline** | `<VS Code User folder>/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` or `~/.cline/data/settings/cline_mcp_settings.json` | *None* | `stdio`, `sse` |
| **Claude Code plugins** | `~/.claude/plugins/installed_plugins.json` *(read-only)* | *None* | `stdio` |
| **Claude Desktop extensions** | `Claude Extensions/*/manifest.json` in Claude Desktop folder *(read-only)* | *None* | `stdio` |

### Custom Config Paths (`paths.json`)

If your client configuration is stored in a non-standard location or inside a custom profile directory, you can override discovery by creating a `paths.json` file in the MCP Browser state directory:

```json
{
  "claude-desktop": ["/custom/path/to/claude_desktop_config.json"],
  "cursor": ["/custom/path/to/cursor/mcp.json"]
}
```

---

## Safe Editing Engine

Modifying developer configuration files demands absolute precision and zero data loss. MCP Browser follows strict transactional rules:

### 1. Minimal In-Place Modification
Only the specific server entry is added, updated, or removed. Other configured servers, unrecognized vendor keys, file indentation, and trailing newlines are preserved verbatim.

### 2. Symlink Preservation
If your dotfiles or configuration files are symlinked (e.g., managed via Chezmoi, GNU Stow, or a dotfiles repository), MCP Browser resolves the real underlying file and updates it directly—the symlink remains intact.

### 3. Pre-Write Automatic Backups
Before any write operation, the existing file is copied to the `backups/` subfolder in the state directory as `<filename>.<UTC-timestamp>`. MCP Browser retains a rolling history of the last 20 backups per file. Files that did not previously exist have nothing to back up.

### 4. Atomic Swaps & Conflict Detection
Writes are performed by writing to a temporary file in the same directory and atomically replacing the target using OS-level renames. If another program modifies the file during editing, MCP Browser detects the conflict, aborts the write, and reports a `409 Conflict`.

### 5. Multi-Client Transactions
When adding a server to multiple clients simultaneously:
- A pre-flight verification checks all target configuration files first. If any check fails, nothing is written.
- Target writes proceed individually; each success or failure is reported independently with no partial rollbacks.

### 6. Comments & Formatting
- **TOML (Codex):** Comments, whitespace, and table structures are parsed and preserved.
- **JSONC (Cursor, VS Code, Zed):** Standard JSON cannot contain comments. When rewriting JSONC files with comments, comments would be lost; MCP Browser detects comments and requires explicit user confirmation.
- **Zed `settings.json`:** Because Zed stores your entire editor configuration in `settings.json`, any file containing comments is never rewritten by MCP Browser—you must edit it in Zed directly.

### 7. Secret Redaction & Hygiene
- Secrets are masked with `•••` in lists, previews, and API responses.
- Real values are fetched only when an entry is opened for editing. A masked value is never written back to disk.
- Redaction covers `KEY=value` arguments with secret-like keys (e.g., `*TOKEN*`, `*KEY*`, `*SECRET*`), values following `-e`, `--env`, `-H`, `--header` (e.g., `Authorization: Bearer •••`), and token-like URL path segments.
- Subprocess stderr output and error messages are scrubbed of sensitive values before display.

### 8. Defensive Resource Bounds
- Process stderr output is limited to a 4 KB rolling ring buffer.
- Discovery scans are capped at 100 pages / 5,000 items.
- Tool execution payloads exceeding 10 MB are truncated with warning indicators.
- Server scanning never automatically triggers browser authentication; servers requiring authentication are flagged as `needs_auth` and only connect when you explicitly click **Connect**.

---

## Unsupported Features & Boundaries

- **Claude Cloud Connectors:** Connectors added through claude.ai exist in your cloud account rather than on local disk and cannot be managed here.
- **VS Code `${input:...}` Variables:** Entries relying on interactive VS Code input prompts are listed, but connecting directly fails with an explanatory message.
- **WebSocket Transports (`type: "ws"`):** Displayed with an advisory note; connection is unsupported.
- **Extension Marketplaces:** Plugin and extension sources are strictly read-only. MCP Browser does not install third-party plugins or automatically restart external applications.
