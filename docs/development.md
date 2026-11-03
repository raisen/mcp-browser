# Developer & Contributor Guide

[← Back to README](../README.md)

This document covers the local development environment, repository architecture, testing workflows, release processes, and instructions for adding support for new AI coding clients.

---

## Workspace Setup

Development is standardized using either the official devcontainer or local `uv`.

### Using the Devcontainer (Recommended)
The devcontainer bundles Python 3.12, `uv`, and all development dependencies.
```sh
make up      # Start the devcontainer
make check   # Run complete CI test suite inside the container
```

### Local Setup without Devcontainer
You can also run tasks directly on your host using `uv`:
```sh
uv sync --all-packages
make check IN=   # Run CI checks using local host tools
```

---

## Make Targets & Commands

Run `make help` to inspect available build automation targets:

| Target | Description |
| :--- | :--- |
| `make check` | Runs all CI checks in sequence: `sync`, `lint`, `typecheck`, `test`, `lines`. |
| `make test` | Runs the test suite via `pytest` (e.g., `make test ARGS="-k test_name"`). |
| `make lint` | Runs Ruff linter and format verification. |
| `make fmt` | Automatically fixes lint violations and reformats source code. |
| `make typecheck` | Runs Pyright static type analysis. |
| `make lines` | Enforces the strict 250-line maximum per source file (`scripts/check_lines.py`). |
| `make build` | Packages all workspace wheels into `dist/`. |
| `make bundle` | Generates standalone PyInstaller binary bundles. |
| `make clean` | Removes build artifacts, caches, and distribution bundles. |

### Product Host Targets
*Note:* The targets `make run`, `make start`, `make stop`, and `make open` always execute on your **host machine** (outside the container), because they need to access real user configuration files and open the host web browser.

---

## Monorepo Architecture

The repository is structured as a clean Python monorepo managed with `uv` workspaces:

```
mcp-browser/
├── packages/
│   ├── core/         # Config discovery, safe editing engine, dialects, MCP client
│   ├── server/       # Starlette HTTP server, REST endpoints, zero-build Alpine/HTML UI
│   └── cli/          # Command-line entry points and daemon management
├── packaging/        # PyInstaller build scripts and macOS Swift menu bar app wrapper
├── site/             # Static marketing website, documentation mirrors, and llms.txt
├── tests/            # Test suites (core, server, cli) and sample config fixtures
└── docs/             # Architecture, security, and developer reference guides
```

### Design Constraints
- **Strict Line Limits:** Every source file (`.py`, `.js`, `.css`, `.html`) must remain **<= 250 lines**. This ensures modularity and readable components.
- **Zero-Build UI:** The frontend runs directly in modern browsers using native HTML5, Alpine.js, and Pico CSS without heavy Node.js or Webpack build steps.

---

## Adding a New Client

To add support for a new AI coding assistant:

1. **Define a Client Specification:**
   Add a new `ClientSpec` entry in `packages/core/src/mcp_browser_core/specs/`:
   ```python
   ClientSpec(
       id="my-client",
       name="My AI Assistant",
       dialect="mcpservers_json",
       format="json",
       config_paths_per_os={
           "darwin": ["~/Library/Application Support/MyClient/config.json"],
           "linux": ["~/.config/MyClient/config.json"],
           "windows": ["%APPDATA%\\MyClient\\config.json"],
       },
       project_relative_paths=[".myclient/config.json"],
       root_key="mcpServers",
   )
   ```

2. **Select or Implement a Dialect:**
   - If the client's configuration syntax matches an existing format (`mcpservers_json`, `codex`, `gemini`, `vscode`, `zed`), reuse it.
   - If the syntax is novel, implement a new dialect parser in `packages/core/src/mcp_browser_core/dialects/`.

3. **Add Test Fixtures & Round-Trip Tests:**
   - Add a representative configuration file in `tests/fixtures/configs/`.
   - Add unit tests verifying discovery, safe reading, mutation, and comment preservation.

4. **Update Documentation:**
   Add the client and its config paths to [docs/clients.md](clients.md).

---

## Release Process

1. **Bump Version:** Update the version string in `packages/core/pyproject.toml`, `packages/server/pyproject.toml`, and `packages/cli/pyproject.toml`.
2. **Tag Release:** Commit and create an annotated git tag:
   ```sh
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin vX.Y.Z
   ```
3. **Automated CI/CD:**
   - GitHub Actions verifies test suites and matching version pins.
   - Publishes Python wheels to PyPI.
   - Compiles standalone binaries for macOS (arm64/x86_64), Windows, and Linux.
   - Signs and notarizes the macOS `.dmg` with Apple Developer ID.
   - Generates `SHA256SUMS.txt` and publishes the GitHub Release.
