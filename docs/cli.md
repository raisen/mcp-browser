# CLI & Daemon Architecture Reference

[← Back to README](../README.md)

MCP Browser provides a command-line interface with foreground and background execution modes, automated daemon lifecycle tracking, and port collision defense.

---

## Command Reference

| Command | Description |
| :--- | :--- |
| `mcp-browser` or `mcp-browser serve` | Runs the server in the foreground, prints the authenticated URL, and opens your browser. Press `Ctrl+C` to terminate. |
| `mcp-browser start` | Spawns the server as a background daemon process, logs output to `server.log`, and opens your browser. |
| `mcp-browser stop` | Gracefully stops the verified background server process. Refuses to signal any PID that `/healthz` does not verify as ours. |
| `mcp-browser status` | Checks server health and prints running status (returns exit code `0` if active, `1` if stopped). |
| `mcp-browser open` | Opens the web dashboard of the currently running server in your default browser. |

### Global Flags

- `--port N`: Specify the listening port (default: `8765`).
- `--no-open`: Start the server without automatically opening the browser. Useful for headless servers or remote terminal sessions.

---

## Daemon Lifecycle & Verification

### PID Verification Handshake
To prevent accidental signals or malicious PID re-use, `mcp-browser stop` and `status` perform a strict handshake:
1. The server stores its process ID in `server.pid` inside the state folder.
2. Before sending any termination signal, the CLI queries `http://127.0.0.1:<port>/healthz`.
3. The `/healthz` response returns the internal process PID.
4. Only if the PID reported by `/healthz` matches the PID recorded in `server.pid` is the signal dispatched.

### Port Squatting Prevention
If the configured port (default `8765`) is already in use:
- If the running process is an authentic MCP Browser instance, `serve`, `start`, and `open` gracefully display its active URL rather than crashing.
- If the port is occupied by an unrelated program (even one simulating `/healthz`), the server alerts the user that the port is taken and refuses to transmit the authentication token.
- You can switch to any free port using `--port <N>`.

### Linux Private Launcher File
On Linux, opening a browser with the token in the command-line argument (`xdg-open "http://...#token=..."`) could leak the token to other local users viewing the process tree via `ps`.
- To avoid this, MCP Browser creates a short-lived, private HTML redirect file (file mode `0600`) inside the state folder and opens the browser on that local file.
- The redirect file forwards to the loopback URL and immediately self-deletes.
- If your browser is confined in a sandbox (e.g., Snap or Flatpak) and cannot access the private state path, copy and paste the printed URL directly into your browser.

---

## State Directory & File Layout

MCP Browser stores persistent runtime state, authentication tokens, catalog caches, and backups in OS-standard directories:

| Operating System | Default State Path |
| :--- | :--- |
| **macOS** | `~/Library/Application Support/mcp-browser` |
| **Linux** | `$XDG_STATE_HOME/mcp-browser` (defaults to `~/.local/state/mcp-browser`) |
| **Windows** | `%LOCALAPPDATA%\mcp-browser` |

### Environment Variables
- `MCP_BROWSER_STATE_DIR`: Overrides the default state directory path.
- `MCP_BROWSER_PORT`: Sets the default fallback port (overridden by `--port`).

### State Directory Contents
```
<state-dir>/
├── server.pid            # Process ID of the active daemon
├── token                 # Ephemeral random Bearer auth token (mode 0600)
├── server.log            # Daemon standard output and error log
├── paths.json            # Optional user-defined custom config file paths
├── catalog_cache.json    # Cached results of MCP server tool/resource scans
└── backups/              # Rolling timestamped backups of modified config files
    ├── .claude.json.2026-11-03T05:00:00Z
    └── mcp.json.2026-11-03T05:12:00Z
```
