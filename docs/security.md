# Security Architecture & Binary Integrity

[← Back to README](../README.md)

MCP Browser is built from the ground up for strict local operation, defensive isolation, and zero telemetry.

---

## Security Model & Threat Boundaries

### 1. Loopback Network Isolation
- The server binds strictly to the loopback interface (`127.0.0.1`). There is deliberately no `--host` option; the server cannot be exposed to an external network.
- Every HTTP request must supply a valid `Host` header matching `127.0.0.1:<port>` or `localhost:<port>`. Foreign hostnames and cross-site `Origin` headers are immediately rejected with `403 Forbidden`, neutralizing DNS rebinding attacks from malicious websites.

### 2. Bearer Token Lifecycle
- All `/api/*` endpoints require authentication via `Authorization: Bearer <token>`.
- The token is a cryptographically strong random value generated on server start and stored in the state directory with strict file permissions (`0600`).
- The token reaches the client UI solely through the URL hash fragment (`http://127.0.0.1:8765/#token=...`). Browsers never transmit URL hash fragments in HTTP requests over the wire. Once loaded into client memory, the hash fragment is removed from the address bar.
- The token is displayed in your terminal output on launch but is never written to `server.log`.

### 3. Execution Boundaries for `stdio` Servers
- Connecting to a `stdio` MCP server executes the configured command on your host machine under your current user account, exactly as the AI client would.
- **Rule of Thumb:** Only connect to MCP servers whose underlying binaries, commands, and dependencies you trust. Tool calls inherit your local user account permissions.

### 4. Untrusted Workspace Safeguards
Project-level configuration files (e.g., `.mcp.json`, `.cursor/mcp.json`, `.vscode/mcp.json`, `.codex/config.toml`) can be committed by untrusted third parties in cloned repositories.
- The server refuses to connect, call tools, inspect resources, or load prompts from project-level configurations (`409 confirmation_required`).
- The UI displays an explicit warning highlighting the exact command, arguments, URL, host, and environment variables that the server will access.
- Execution proceeds only when the user explicitly reviews and sends `confirm_untrusted: true`.
- Confirmations are ephemeral and never cached or persisted across sessions.
- `Scan all` automatically skips untrusted project entries.

### 5. Content Security Policy (CSP)
Every HTML response is served with a hardened Content Security Policy:
```http
Content-Security-Policy: default-src 'self'; frame-ancestors 'none'; X-Content-Type-Options: nosniff; Referrer-Policy: no-referrer;
```
- No external scripts, fonts, analytics, or stylesheets are loaded.
- Framing inside `<iframe>` elements is denied (`frame-ancestors 'none'`).
- Referrer headers are stripped (`Referrer-Policy: no-referrer`).

### 6. Zero Telemetry & Privacy
- MCP Browser makes zero external network connections (except optional on-demand GitHub release checks in the native macOS app).
- Environment values, authorization tokens, and API keys are masked in the browser and scrubbed from error logs.
- On Windows, state folders rely on user profile ACL permissions, which restrict access to your user account.

---

## Binary Integrity and Verification

Every official release includes cryptographically verifiable artifacts to guarantee authenticity.

### macOS App (.dmg)
Official `.dmg` releases are signed with an Apple Developer ID Application certificate and notarized by Apple via the Apple Notary Service with stapled tickets.
- Gatekeeper automatically validates the ticket upon mount and launch.
- No `xattr` or quarantine workarounds are required.

### Windows Standalone Executables (.zip)
Because standalone Windows binaries are built on GitHub Actions and not code-signed with an expensive EV certificate, Windows SmartScreen may present a defense prompt (*"Windows protected your PC"*):
1. Click **More info**.
2. Click **Run anyway**.
3. Alternatively, unblock the downloaded archive in PowerShell before unzipping:
   ```powershell
   Unblock-File -Path .\mcp-browser-0.1.0-windows-x86_64.zip
   ```

### macOS Standalone CLI (.zip)
If you run the raw standalone CLI zip archive rather than the official `.dmg` installer, macOS marks the unzipped binary with the `com.apple.quarantine` attribute:
```sh
xattr -dr com.apple.quarantine mcp-browser
```

### Cryptographic Checksums
Every release publishes a `SHA256SUMS.txt` manifest containing SHA-256 hashes for all `.dmg` and `.zip` archives. Verify your download:

```sh
# macOS
shasum -a 256 -c SHA256SUMS.txt --ignore-missing

# Linux
sha256sum -c SHA256SUMS.txt --ignore-missing

# Windows (PowerShell)
(Get-FileHash .\mcp-browser-0.1.0-windows-x86_64.zip -Algorithm SHA256).Hash
```
