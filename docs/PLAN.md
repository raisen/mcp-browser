# mcp-browser — Implementation Plan

Local web tool that lists, searches and executes every MCP server configured in Claude Desktop, Claude Code,
Codex, Gemini CLI, Antigravity, Cursor, VS Code, Windsurf, Zed and Cline, and adds/edits/deletes servers by
rewriting the clients' real config files. Python >= 3.11, uv workspace, three packages, no Node, OS-agnostic.

Rules for every implementer: source files (py/js/css/html/tests) <= 250 lines, `static/vendor/` excluded. Reuse
libraries. No personal names, usernames, emails or absolute home paths in any file. `mcp` is imported only in
`packages/core/src/mcp_browser_core/transports.py`, `connect.py` and `oauth.py`. All path resolution goes through
`Paths`. All commands run inside the devcontainer: `devcontainer exec --workspace-folder . <cmd>`. Never run on the host.

Verified on PyPI 2026-11-02: `mcp` 2.3.0 (requires `httpx2>=2.10`, `starlette`, `uvicorn`, `sse-starlette`; the latter is server-side only and is not bundled) and `httpx2` 2.16.0 exist.
Do not downgrade to `mcp` 1.x or `httpx`. Alpine latest is 3.17.5.

## 1. Repo tree (file — purpose — est. lines)

```
pyproject.toml                        uv workspace root (`package = false`, members packages/*)  45
uv.lock                               single lockfile
README.md                             install (uv tool / PyInstaller zip), security, clients    200
LICENSE                               MIT, "mcp-browser contributors"
AGENTS.md                             repo rules (line limit, devcontainer, no secrets)          40
CLAUDE.md                             `@AGENTS.md`                                                1
.gitignore                            *.log .venv dist build __pycache__ *.spec ...
.devcontainer/devcontainer.json       python 3.12 image, uv via postCreateCommand, port 8765     20
.github/workflows/ci.yml              matrix ubuntu/macos/windows: sync, ruff, pyright, pytest  60
.github/workflows/release.yml         PyPI publish (core, server, cli) + PyInstaller zips       120
scripts/check_lines.py                fails if any source file > 250 lines (git ls-files)        55
packaging/pyinstaller_entry.py        `from mcp_browser.cli import main; main()`                 10
packaging/build.py                    runs pyinstaller with the flags in §11, zips dist          60
packaging/NOTES.md                    unsigned-binary notes, SHA256 verification                 40

packages/core/pyproject.toml          dist mcp-browser-core, hatchling                           30
packages/core/src/mcp_browser_core/
  __init__.py                         re-exports models + `__version__`                          60
  models.py                           transports, ServerEntry, clients, DiscoveryResult,
                                      Target/NewEntry/EntryPatch, WriteReport, AddResult        150
  catalog_models.py                   ToolInfo, ResourceInfo, PromptInfo, CatalogEntry,
                                      CallResult                                                 50
  errors.py                           `McpBrowserError` + subclasses with `code`, `status`       85
  paths.py                            `Paths(environ, platform, cwd)`; tokens; state layout     190
  expand.py                           `expand()` placeholder expansion + envFile parsing        120
  specs/__init__.py                   `REGISTRY: dict[str, ClientSpec]` assembled from modules   30
  specs/base.py                       `ClientSpec`, `PathRule` dataclasses                       50
  specs/claude.py                     Claude Code, Claude Desktop, plugins, extensions specs    110
  specs/codex_gemini.py               Codex, Gemini CLI, Antigravity specs                      100
  specs/editors.py                    Cursor, VS Code, Windsurf, Zed, Cline specs               130
  formats/__init__.py                 `load`, `dump`, `detect_indent`, `has_comments`            60
  formats/json_strict.py              json load/dump preserving indent + trailing newline        80
  formats/jsonc.py                    json5 load; dump = strict json; `has_comments()` scanner   90
  formats/toml.py                     tomlkit load/dump                                          50
  dialects/__init__.py                `Dialect` protocol + `get_dialect(name)`                   50
  dialects/common.py                  shared helpers: split transport/extra, env/headers        120
  dialects/mcpservers_json.py         Claude Code/Desktop/Cursor/Antigravity/Windsurf/Cline     200
  dialects/codex.py                   TOML `[mcp_servers.*]`                                    150
  dialects/gemini.py                  Gemini `url`/`httpUrl`                                    100
  dialects/vscode.py                  `servers` key, `inputs` preserved                         110
  dialects/zed.py                     `context_servers`, `source:"custom"`                       90
  dialects/readonly.py                plugins + extensions -> ServerEntry(read_only=True)       150
  discovery.py                        `discover(paths) -> DiscoveryResult`                      180
  writer.py                           atomic locked write with backups + retries                200
  mutate.py                           add/update/delete/rename -> uses dialect + writer         200
  transports.py                       builds the SDK transport from an expanded Transport,
                                      stderr capture                                            120
  connect.py                          `session()`, `Session`, timeout and error mapping         220
  catalog.py                          `<state>/catalog.json` cache + scan                       150
  oauth.py                            OAuthHook + file token storage + provider factory         160
  secrets.py                          `mask_entry()`, `SECRET_KEYS`, `contains_mask()`          100
  py.typed

packages/server/pyproject.toml        dist mcp-browser-server                                    30
packages/server/src/mcp_browser_server/
  __init__.py                                                                                    5
  app.py                              `create_app(settings) -> Starlette`                       120
  settings.py                         `ServerSettings` (port, token, paths, limits, redirect)    35
  auth.py                             `SecurityMiddleware` (host/origin/bearer)                 120
  api_models.py                       request/response pydantic models                          110
  routes/__init__.py                  route table assembly                                       40
  routes/servers_read.py              list, get, reveal                                         120
  routes/servers_write.py             add, update, delete, rename                               170
  routes/connect.py                   connect/scan/call/read resource/get prompt                180
  routes/meta.py                      healthz, clients, projects, oauth callback                100
  static_files.py                     importlib.resources mount                                  40
  static/index.html                   shell: head, nav, `<div id="app">`, one module script      60
  static/css/base.css                 tokens, layout, dark mode                                200
  static/css/components.css           list, forms, dialogs, badges                              200
  static/js/main.js                   boot: imports Alpine ESM, token, templates, `Alpine.start` 80
  static/js/app.js                    `app()` Alpine data (state + actions)                     180
  static/js/api.js                    fetch wrapper with bearer, error -> `ApiError`            80
  static/js/search.js                 client-side token match                                   60
  static/js/schema_form.js            JSON Schema -> form model; `toArgs()`; fallback textarea  200
  static/js/schema_render.js          form model -> HTML string                                 200
  static/js/views/list.js             server list template string                             150
  static/js/views/detail.js           server detail, tools, call result template              200
  static/js/views/editor.js           add/edit dialog template                                 200
  static/vendor/alpine.esm.js         vendored alpinejs 3.17.5 dist/module.esm.js (not line-checked)

packages/cli/pyproject.toml           dist mcp-browser, console script `mcp-browser`             30
packages/cli/src/mcp_browser/
  __init__.py                                                                                    5
  __main__.py                         `from .cli import main; main()`                             5
  cli.py                              argparse: serve/start/stop/status/open                   150
  daemon.py                           Popen detach, pid file, probe, stop                       160

tests/conftest.py                     autouse env isolation fixture, `paths`, `paths_for`        75
tests/fixtures/configs/*              one sample config per client (+ jsonc, toml comments)
tests/fixtures/fixture_server.py      tiny stdio MCP server (echo, add, slow, fail tools)        60
tests/core/test_paths.py                                                                        120
tests/core/test_expand.py                                                                        80
tests/core/test_formats.py                                                                      100
tests/core/test_secrets.py                                                                       80
tests/core/test_dialect_<name>.py     one per dialect, round-trip                             ~100 each
tests/core/test_discovery.py                                                                    120
tests/core/test_writer.py             concurrency, backups, comments, mode, symlink             180
tests/core/test_mutate.py                                                                       150
tests/core/test_connect_e2e.py        fixture server connect/list/call/timeout                  120
tests/core/test_catalog.py                                                                       80
tests/server/test_auth.py                                                                       100
tests/server/test_servers_api.py                                                                200
tests/server/test_connect_api.py      includes a real stdio call (runs on Windows CI)           150
tests/cli/test_cli.py                 argparse + daemon pid logic (Popen mocked)                 120
```

## 2. Core models — `models.py` and `catalog_models.py` (frozen by Wave 0; the files are the contract)

`models.py` (no `mcp` import; pydantic v2):

```python
Scope = Literal["user", "local", "project", "plugin", "extension"]
Format = Literal["json", "jsonc", "toml"]
Platform = Literal["darwin", "win32", "linux"]

class StdioTransport(BaseModel):
    kind: Literal["stdio"] = "stdio"
    command: str; args: list[str] = []; env: dict[str, str] = {}; cwd: str | None = None
    env_file: str | None = None          # Cursor/VS Code envFile

class HttpTransport(BaseModel):
    kind: Literal["http"] = "http"       # streamable HTTP
    url: str; headers: dict[str, str] = {}; oauth: dict[str, Any] | None = None

class SseTransport(BaseModel):
    kind: Literal["sse"] = "sse"
    url: str; headers: dict[str, str] = {}; oauth: dict[str, Any] | None = None

Transport = Annotated[StdioTransport | HttpTransport | SseTransport, Field(discriminator="kind")]

def make_entry_id(client_id, scope, config_path, name) -> str
    # blake2b(f"{client_id}|{scope}|{config_path}|{name}".encode(), digest_size=8).hexdigest()
def fingerprint(transport: StdioTransport | HttpTransport | SseTransport | None) -> str
    # blake2b(transport.model_dump_json().encode() if transport else b"", digest_size=8).hexdigest()

class Capabilities(BaseModel):  stdio: bool = True; http: bool = True; sse: bool = True; project_scope: bool; editable: bool = True
class ConfigFileInfo(BaseModel): path: str; exists: bool; scope: Scope; format: Format; project: str | None = None; has_comments: bool = False
class ClientInfo(BaseModel):    id: str; display_name: str; config_paths: list[ConfigFileInfo]; capabilities: Capabilities; needs_restart: bool = False

class ServerEntry(BaseModel):
    id: str; name: str; client_id: str; scope: Scope
    config_path: str                      # absolute path of the file it came from
    project: str | None = None            # project dir for project/local scope; the VERBATIM `projects` key
    transport: Transport | None = None    # None when unparseable (e.g. type:"ws")
    error: str | None = None              # why transport is None
    enabled: bool = True                  # mirrors disabled/enabled fields, read-only in UI
    extra: dict[str, Any] = {}            # every native field not mapped above, kept verbatim
    read_only: bool = False; read_only_reason: str | None = None

class DiscoveryResult(BaseModel): entries: list[ServerEntry]; clients: list[ClientInfo]; projects: list[str]; warnings: list[str]

class Target(BaseModel):    client_id: str; scope: Scope; project: str | None = None
class NewEntry(BaseModel):  name: str; transport: Transport; extra: dict[str, Any] = {}
class EntryPatch(BaseModel): name: str | None = None; transport: Transport | None = None; extra: dict[str, Any] | None = None
class WriteReport(BaseModel):
    path: str; backup_path: str | None    # None when the file did not exist before the write
    created_file: bool; entry: ServerEntry
class AddResult(BaseModel):  target: Target; report: WriteReport | None = None; error: str | None = None
```

`catalog_models.py`:

```python
class ToolInfo(BaseModel):     name: str; description: str | None = None; input_schema: dict[str, Any] = {}
class ResourceInfo(BaseModel): uri: str; name: str | None; mime_type: str | None; description: str | None   # all optional
class PromptInfo(BaseModel):   name: str; description: str | None = None; arguments: list[dict[str, Any]] = []
class CatalogEntry(BaseModel):
    entry_id: str; fingerprint: str       # models.fingerprint(entry.transport)
    scanned_at: datetime; tools: list[ToolInfo] = []; resources: list[ResourceInfo] = []; prompts: list[PromptInfo] = []
    status: Literal["ok", "error", "needs_auth"]; error: str | None = None; stderr_tail: str | None = None
class CallResult(BaseModel):   content: list[dict[str, Any]]; structured: dict[str, Any] | None = None; is_error: bool = False; duration_ms: int = 0; stderr_tail: str | None = None; truncated: bool = False
```

`errors.py`: `class McpBrowserError(Exception)` with class attrs `code: str`, `status: int`, instance `message`, `detail: dict[str, Any]`,
and `to_body() -> {"error": code, "message", "detail"}`. Constructor `Err(message="", **detail)`. Subclasses:
`NotFound(404,"not_found")`, `ReadOnly(403,"read_only")`, `UnsupportedTransport(422,"unsupported_transport")`,
`InvalidArguments(400,"invalid_arguments")`, `UnresolvedPlaceholders(400,"unresolved_placeholders", placeholders=[...])`,
`FileChanged(409,"file_changed")`, `CommentsWouldBeLost(409,"comments_would_be_lost", can_override=bool)`,
`ConnectFailed(502,"connect_failed", stderr_tail=str)`, `OperationTimeout(504,"timeout")`, `Unauthorized(401,"unauthorized")`,
`Conflict(409,"name_exists")`.

## 3. Paths — `paths.py`

```python
class Paths:
    def __init__(self, environ: Mapping[str, str], platform: Platform, cwd: Path) -> None
    environ: dict[str, str]; platform: Platform; cwd: Path
    home: Path                                   # USERPROFILE on win32, HOME elsewhere
    appdata / localappdata / xdg_config: Path    # properties with per-OS defaults under home
    state_dir: Path                              # $MCP_BROWSER_STATE_DIR, else darwin ~/Library/Application Support/mcp-browser,
                                                 # win32 {localappdata}/mcp-browser, linux ($XDG_STATE_HOME or ~/.local/state)/mcp-browser
    token_file / pid_file / log_file / catalog_file / backups_dir / locks_dir / oauth_dir / paths_file: Path
    def expand_home(self, p: str) -> Path
    def claude_dir(self) -> Path                 # $CLAUDE_CONFIG_DIR or ~/.claude (plugins)
    def claude_json_dir(self) -> Path            # $CLAUDE_CONFIG_DIR or home (holds .claude.json)
    def claude_desktop_dir(self) -> Path
    def codex_home(self) -> Path                 # $CODEX_HOME or ~/.codex
    def code_user_dir(self) -> Path              # VS Code `User` dir (single path)
    def tokens(self, project: Path | None = None) -> dict[str, str]
    def candidates(self, rule: PathRule, project: Path | None = None) -> list[Path]   # [] if platform not in rule.platforms; globs yield existing matches only
    def existing(self, rule, project=None) -> list[Path]
    def override_paths(self) -> dict[str, list[str]]      # <state>/paths.json {client_id: [paths]}; {} if absent/invalid
def current_platform() -> Platform
def default_paths() -> Paths  # os.environ, current_platform(), Path.cwd()
```

`PathRule(template: str, platforms: tuple[str, ...] = all three, scope: Scope = "user")`. Templates use tokens `{home}`,
`{appdata}`, `{localappdata}`, `{xdg_config}`, `{claude_dir}`, `{claude_json_dir}`, `{claude_desktop_dir}`, `{codex_home}`,
`{code_user}`, `{project}`. Glob allowed (`Claude_*`, `*/manifest.json`).

- `{claude_json_dir}` = `$CLAUDE_CONFIG_DIR` or `{home}`. `{claude_dir}` = `$CLAUDE_CONFIG_DIR` or `~/.claude`.
- `{claude_desktop_dir}`: darwin `{home}/Library/Application Support/Claude`; win32 the first existing of
  `{localappdata}/Packages/Claude_*/LocalCache/Roaming/Claude`, `{appdata}/Claude` (falls back to the latter);
  linux `{xdg_config}/Claude`.
- `{code_user}`: darwin `~/Library/Application Support/Code/User`, win32 `%APPDATA%\Code\User`, linux `{xdg_config}/Code/User`.
- The state directory is computed by `Paths` itself (not platformdirs) so any platform can be simulated in tests.
- State layout: `<state>/token` (0600), `server.pid`, `server.log`, `catalog.json`, `backups/` (0700), `locks/`, `oauth/`, `paths.json`.
- `projects` keys in `.claude.json` are used VERBATIM as JSON keys and never normalized, since Windows spells them
  differently. Convert to `Path` only to reach the filesystem. Local-scope adds may only target existing keys.
- Windows relies on the per-user profile's default ACL for the 0600/0700 intent; README notes it.

## 4. ClientSpec table — `specs/`

```python
@dataclass(frozen=True)
class ClientSpec:
    id: str; display_name: str; dialect: str; format: Format
    user_paths: tuple[PathRule, ...]; project_paths: tuple[str, ...]   # project-relative, e.g. ".cursor/mcp.json"
    root_key: str                        # "mcpServers" | "servers" | "context_servers" | "mcp_servers"
    capabilities: Capabilities          # lives in models.py
    needs_restart: bool = False; editable: bool = True; read_only_reason: str | None = None
    dedicated_file: bool = True          # False for Zed: the file is the whole editor settings
    local_projects_key: str | None = None            # "projects" for claude-code (local scope in .claude.json)
    type_style: Literal["none", "std", "cline"] = "none"   # mcpservers_json: how `type` is written
    url_key: Literal["url", "serverUrl"] = "url"           # mcpservers_json: url field name
```

| id | display | dialect | fmt | user paths (first existing wins) | project path | root key | caps |
|---|---|---|---|---|---|---|---|
| claude-code | Claude Code | mcpservers_json | json | `{claude_json_dir}/.claude.json` (single candidate) | `.mcp.json` | mcpServers (+ `projects.<key>.mcpServers` = local) | all |
| claude-desktop | Claude Desktop | mcpservers_json | json | `{claude_desktop_dir}/claude_desktop_config.json` | none | mcpServers | stdio only, restart |
| codex | Codex | codex | toml | `{codex_home}/config.toml` | `.codex/config.toml` | mcp_servers | stdio, http (no sse) |
| gemini | Gemini CLI | gemini | json | `{home}/.gemini/settings.json` | `.gemini/settings.json` | mcpServers | all |
| antigravity | Antigravity | mcpservers_json | json | `{home}/.gemini/config/mcp_config.json`, `{home}/.gemini/antigravity/mcp_config.json` | none | mcpServers | stdio, http |
| cursor | Cursor | mcpservers_json | jsonc | `{home}/.cursor/mcp.json` | `.cursor/mcp.json` | mcpServers | all |
| vscode | VS Code | vscode | jsonc | `{code_user}/mcp.json` | `.vscode/mcp.json` | servers | all |
| windsurf | Windsurf | mcpservers_json | json | `{home}/.codeium/windsurf/mcp_config.json` | none | mcpServers | stdio, http |
| zed | Zed | zed | jsonc | mac/linux `{home}/.config/zed/settings.json`; win `{appdata}/Zed/settings.json`; `dedicated_file=False` | `.zed/settings.json` | context_servers | stdio, http |
| cline | Cline | mcpservers_json | json | `{code_user}/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`, `{home}/.cline/data/settings/cline_mcp_settings.json` | none | mcpServers | all |
| claude-code-plugins | Claude Code plugins | readonly | json | `{claude_dir}/plugins/installed_plugins.json` | none | — | read-only: "installed by plugin; edit the plugin" |
| claude-desktop-ext | Claude Desktop extensions | readonly | json | `{claude_desktop_dir}/Claude Extensions/*/manifest.json` | none | — | read-only: "managed by Claude Desktop" |

Project directories = keys of `projects` in Claude Code's `.claude.json` (verbatim strings) plus `cwd`; each spec with
project paths is checked in each. Adding a client = one `ClientSpec` row (+ a dialect only if the shape is new).

## 5. Dialects — `dialects/`

```python
ParseResult = tuple[Transport | None, str | None, bool, dict[str, Any]]    # (transport, error, enabled, extra)
class Dialect(Protocol):
    def parse(self, name: str, raw: dict[str, Any], spec: ClientSpec) -> ParseResult
    def render(self, entry: ServerEntry, existing: dict[str, Any] | None, spec: ClientSpec) -> dict[str, Any]
        # merge: start from existing (or {}), delete keys of the other transport kinds, set mapped keys, keep extra
    def root(self, doc: Any, spec: ClientSpec, scope: Scope, project: str | None, create: bool) -> MutableMapping[str, Any] | None
        # the dict holding server entries (creates the key chain only when create=True)
def get_dialect(name: str) -> Dialect
```

Per-dialect field mapping (native -> normalized; everything else -> `extra`):

| dialect | stdio | http | sse | enabled | notes |
|---|---|---|---|---|---|
| mcpservers_json | `command,args,env,cwd,envFile->env_file` | `type:"http"\|"streamableHttp"`, `url`\|`serverUrl`, `headers`, `oauth` | `type:"sse"` + `url` | `!disabled` | `type` written for Claude Code (required on url entries), Cursor, Cline (`streamableHttp`/`sse`); omitted for Desktop/Windsurf/Antigravity; `serverUrl` for Antigravity/Windsurf. `type:"ws"` -> transport None, error "websocket not supported". Variant flags live on the spec: `type_style: "none"\|"std"\|"cline"`, `url_key: "url"\|"serverUrl"` |
| codex | `command,args,env,cwd`; `env_vars` -> extra (honored at connect as passthrough names) | `url`, `http_headers`->headers; `bearer_token_env_var` -> header `Authorization: Bearer ${VAR}` (connect time only, not stored in headers); `env_http_headers` {header: ENV} -> headers at connect | n/a (reject) | `enabled` (default true) | all other keys (`startup_timeout_sec`, `tool_timeout_sec`, `enabled_tools`, `disabled_tools`, `required`, `tools`, `auth`, `oauth`, `scopes`) -> extra |
| gemini | `command,args,env,cwd` | `httpUrl`->url, `headers`, `oauth` | `url`->url, `headers` | always true | `timeout,trust,includeTools,excludeTools` -> extra; no `type` |
| vscode | `type:"stdio"`, `command,args,cwd,env,envFile` | `type:"http"`, `url,headers,oauth` | `type:"sse"` | always true | root key `servers`; siblings `inputs`,`sandbox` untouched; `${input:x}` is left in place and the entry is listed, but connecting fails with an error explaining that input variables are not supported |
| zed | `command,args,env` | `url,headers` | n/a | `enabled` | write `source:"custom"` on add; `settings.json` may contain many unrelated keys |
| readonly | plugins: `<installPath>/.mcp.json` `mcpServers` or `plugin.json` inline; extensions: `manifest.json` `server.mcp_config` | — | — | true | expand `${__dirname}` to install dir; other `${user_config.*}` left and reported in `error` |

Round-trip test per dialect: parse fixture -> render onto original raw -> `==` original dict (ordering ignored).

## 6. Formats, discovery, writer, mutate

`formats`: `load(text: str, fmt: Format) -> Any` (json / json5 / tomlkit document); `dump(doc, fmt, *, indent: int = 2, newline: bool = True) -> str`;
`detect_indent(text) -> int`; `has_comments(text, fmt) -> bool` (jsonc: `//` or `/* */` outside strings, found by a character
scanner tracking string state and `\` escapes, never a regex, so URLs inside strings are not comments; json: False;
toml: False since tomlkit preserves comments).

`discovery.discover(paths: Paths, specs: Mapping[str, ClientSpec] = REGISTRY) -> DiscoveryResult`: for each spec, for each
candidate path that exists, load, find root, parse each entry, build `ServerEntry`. Parse failures of a whole file become
`warnings` (file still listed in `clients[].config_paths`). Never executes anything. `${VAR}` placeholders are kept verbatim.

`writer.write_entry(path: str, fmt: Format, mutate: Callable[[Any], None], *, paths: Paths, allow_comment_loss: bool, create: bool, dedicated_file: bool = True) -> str | None`
(returns the backup path, or None when the file did not exist):
1. `target = Path(os.path.realpath(path))`; lock, hash, temp file and `os.replace` all use `target`, so a dotfile symlink survives.
   Lock `<state>/locks/<blake2b(target)>.lock` (filelock, timeout 10s).
2. read bytes + `hash0 = sha256`; if fmt == jsonc and `has_comments`: refuse with `CommentsWouldBeLost(can_override=dedicated_file)`
   unless `dedicated_file and allow_comment_loss` (for non-dedicated files such as Zed `allow_comment_loss` is ignored and the
   UI tells the user to edit that file in the app).
3. load, `mutate(doc)`, dump with detected indent + original trailing newline.
4. backup copy to `<state>/backups/<sanitized path>.<UTC timestamp>` (dir 0700, file 0600, prune to 20 per source). No backup
   when the file did not exist.
5. temp file in the same dir (`tempfile.NamedTemporaryFile(dir=parent, delete=False)`), write, flush, fsync, **close**,
   then `shutil.copymode`; the file must be closed before `os.replace` or Windows raises a sharing violation.
6. re-read + hash; if != hash0 -> remove temp, retry from step 2 (max 3) then `FileChanged`; else `os.replace`. A
   `PermissionError` from `os.replace` counts as a retry; after 3 tries raise `FileChanged`.

Missing file with `create=True`: write `{}` / empty TOML first (mode 0600). An unwritable directory is reported as a clear
error with no fallback location.

`mutate.py` (all take `paths: Paths` and `specs: Mapping[str, ClientSpec] = REGISTRY` as keywords):

```python
def add(new: NewEntry, targets: list[Target], *, paths, specs=REGISTRY, allow_comment_loss=False) -> list[AddResult]
def update(entry_id: str, patch: EntryPatch, *, paths, specs=REGISTRY, allow_comment_loss=False, catalog: Catalog | None = None) -> WriteReport
def delete(entry_id: str, *, paths, specs=REGISTRY, allow_comment_loss=False, catalog: Catalog | None = None) -> WriteReport
def rename(entry_id: str, new_name: str, *, paths, specs=REGISTRY, allow_comment_loss=False, catalog: Catalog | None = None) -> WriteReport
```

`add` preflights ALL targets (capability, duplicate name -> `Conflict`, comment rule) before writing any; a preflight failure
raises and writes nothing. It then writes each target and returns one `AddResult` per target; I/O failures on one target are
recorded in `AddResult.error` and do not abort the others; no rollback happens. `update`, `delete` and `rename` find the entry by
rediscovering, reject read-only entries with `ReadOnly`, forward `allow_comment_loss`, and call `catalog.drop(old_id)` when a
catalog is given (`rename` does delete + add inside one `mutate` callback).

## 7. MCP layer — `expand.py`, `transports.py`, `connect.py`, `catalog.py`, `oauth.py`

`expand.expand(value: str, env: Mapping[str,str], *, project: str | None, home: Path) -> tuple[str, list[str]]` handles
`${VAR}`, `${VAR:-d}`, `$VAR`, `${env:VAR}`, `%VAR%`, `${userHome}`, `${workspaceFolder}`, `${pathSeparator}`;
returns (text, unresolved). `expand_transport(t, env, *, project, home) -> tuple[Transport, list[str]]` expands
command/args/env/cwd/url/headers, loads `env_file` (`KEY=VALUE` lines, `#` comments) under the entry env. Any unresolved ->
`UnresolvedPlaceholders` at connect (callers raise it).

### Verified against the installed SDK (`mcp` 2.3.0, `httpx2` 2.16.0, `mcp-types` 2.3.0)

The 2.x client API differs from 1.x. These forms were run in the devcontainer (stdio, streamable HTTP and SSE round trips).

```python
# imports (only in transports.py / connect.py / oauth.py)
from mcp import Client, MCPError, StdioServerParameters            # also: mcp.stdio_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.client.sse import sse_client
from mcp.client._transport import TransportStreams                  # private module; type of the (read, write) pair
from mcp.client.auth import OAuthClientProvider, TokenStorage, OAuthFlowError, OAuthRegistrationError, OAuthTokenError
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientMetadata, OAuthClientInformationFull, OAuthToken
import httpx2                                                       # same API as httpx: AsyncClient, Timeout, Auth, ConnectError
```

- `Client` is a dataclass: `Client(server, *, cache=None, read_timeout_seconds=None, mode="auto", ...)`; use `async with Client(transport_cm, cache=None) as c:`.
  `server` may be a URL str, `StdioServerParameters`, an in-process server, or **any transport context manager yielding `(read, write)`**,
  e.g. the result of `stdio_client(...)`. Always pass `cache=None` (default is an in-memory response cache; scans must be fresh).
  `mode="auto"` probes `server/discover` and falls back to the initialize handshake; it works with old stdio servers.
- stdio: `stdio_client(StdioServerParameters(command=..., args=[...], env={...}, cwd=...), errlog=<file>)`. `env` is merged over a
  small default environment (HOME/PATH/...), so passing the full filtered environment works. **`errlog` is handed to the subprocess as
  `stderr=`, so it needs a real file descriptor**: use `os.pipe()` with the write end wrapped by `os.fdopen`
  (cast to `TextIO`), drained by a daemon thread that keeps only the last 4096 bytes (`StderrCapture`; bounded, works on Windows). Never an
  unbounded temp file: a hostile server filled disk at 5 GB in 2 s. Never `io.StringIO`. The default `errlog` is `sys.stderr`.
- streamable HTTP: `streamable_http_client(url, *, http_client: httpx2.AsyncClient | None, terminate_on_close=True)`. It has **no headers/auth
  kwarg**: build `httpx2.AsyncClient(headers=..., timeout=httpx2.Timeout(connect_timeout, read=call_timeout), auth=provider_or_None)`, enter it
  with `async with`, and pass it as `http_client=` (the SDK does not close a client you pass). Redirects are followed only within the origin.
- SSE: `sse_client(url, headers=None, timeout=5.0, sse_read_timeout=300.0, httpx_client_factory=..., auth=None, on_session_created=None)`.
- Results are pydantic models with **snake_case** attributes. `await c.list_tools()` -> `ListToolsResult(.tools, .next_cursor)`; likewise
  `list_resources()` (`.resources`), `list_prompts()` (`.prompts`); all accept `cursor=` and **must be paged until `next_cursor is None`**.
  `Tool`: `.name`, `.description` (may be `''`), `.input_schema` (dict). `Resource`: `.uri .name .mime_type .description`. `Prompt`:
  `.name .description .arguments` (items have name/title/description/required; dump with `model_dump(mode="json", exclude_none=True)`).
  Check `c.server_capabilities.tools/.resources/.prompts` and skip listing a kind the server does not advertise (that field is `None`).
- `await c.call_tool(name, args, read_timeout_seconds=None)` -> `CallToolResult(.content: list[block], .structured_content: dict | None, .is_error: bool)`.
  Convert blocks with `[b.model_dump(mode="json", exclude_none=True) for b in r.content]`. A tool that raises or an unknown tool name comes back as
  `is_error=True` with an error text block, it does not raise.
- `await c.read_resource(uri)` -> `.contents` (items: `uri, mime_type, text` or `blob`); `await c.get_prompt(name, {"k": "v"})` -> `.description`, `.messages`
  (`role`, `content` block). Dump with `model_dump(mode="json", exclude_none=True)`.
- Timeouts: wrap connect and each call in `anyio.fail_after(...)`, which raises the builtin `TimeoutError` (verified). The SDK's own
  `read_timeout_seconds` raises `MCPError("Request 'tools/call' timed out")` instead; do not rely on it.
- **Errors are wrapped in exception groups** and must be flattened recursively (`BaseExceptionGroup.exceptions`) before mapping:
  a missing stdio command raises a bare `FileNotFoundError`; a server that exits during startup raises `ExceptionGroup` containing
  `MCPError(-32000, "Connection closed")`; a refused HTTP connection raises `ExceptionGroup` containing `httpx2.ConnectError`.
  `MCPError` exposes `.code`, `.message`, `.data`.
- Fixture servers use `from mcp.server.mcpserver import MCPServer`: `s = MCPServer("name")`, `@s.tool()`, `@s.resource("res://a")`,
  `@s.prompt()`, then `s.run("stdio")` / `s.run("streamable-http", host="127.0.0.1", port=N)` / `s.run("sse", host=..., port=N)`.
  Write a `slow` tool as `async def` with `await anyio.sleep(...)`, since a sync tool's sleeping thread delays server shutdown.
- OAuth: `OAuthClientProvider(server_url, client_metadata: OAuthClientMetadata, storage: TokenStorage, redirect_handler: Callable[[str], Awaitable[None]] | None,
  callback_handler: Callable[[], Awaitable[AuthorizationCodeResult]] | None, client_metadata_url=None, validate_resource_url=None)` is an `httpx2.Auth`:
  pass it as `auth=` to the `httpx2.AsyncClient` (or `sse_client`). `TokenStorage` is a Protocol with `async get_tokens() -> OAuthToken | None`,
  `set_tokens(OAuthToken)`, `get_client_info() -> OAuthClientInformationFull | None`, `set_client_info(OAuthClientInformationFull)`.
  `OAuthClientMetadata(redirect_uris=[...] (required, min 1), client_name=..., scope=...)`. `AuthorizationCodeResult(code, state, iss)`.
  The callback handler takes **no arguments**, and the SDK generates `state` itself, verifying it with `secrets.compare_digest`; `state` is only visible
  inside the authorization URL given to `redirect_handler`.

### Module interfaces

```python
# transports.py
def open_streams(t: Transport, *, env: Mapping[str, str], errlog: TextIO | None, auth: httpx2.Auth | None,
                 connect_timeout: float, call_timeout: float) -> AbstractAsyncContextManager[TransportStreams]
    # stdio -> stdio_client(StdioServerParameters(...), errlog=errlog); http -> enters AsyncClient then streamable_http_client(url, http_client=client);
    # sse -> sse_client(...). `t` is already expanded. `env` is the full stdio environment.

# connect.py
@dataclass(frozen=True) class ConnectOptions: connect_timeout: float = 30.0; call_timeout: float = 300.0; interactive: bool = True
def session(entry: ServerEntry, paths: Paths, opts: ConnectOptions, oauth: OAuthHook | None, *, limiter: anyio.CapacityLimiter)
    -> AbstractAsyncContextManager[Session]      # implement as an @asynccontextmanager
class Session:   # thin wrapper, hides mcp types
    stderr_tail: str                                    # property: last 4 KB captured from the errlog file
    async def list_tools(self) -> list[ToolInfo]; list_resources(self) -> list[ResourceInfo]; list_prompts(self) -> list[PromptInfo]
    async def call_tool(self, name: str, args: dict[str, Any], timeout: float) -> CallResult
    async def read_resource(self, uri: str) -> list[dict[str, Any]]; get_prompt(self, name: str, args: dict[str, str]) -> dict[str, Any]
```

- Stdio env = `{k: v for k, v in os.environ.items() if not k.startswith("MCP_BROWSER_")}` with the expanded entry env on top, plus Codex
  `env_vars` passthrough names. HTTP: skip OAuth when an `Authorization` header is present.
- There is **no module-level semaphore**. The owner of the event loop creates `anyio.CapacityLimiter(8)` (the server keeps one on app state, built
  from `ServerSettings.max_concurrency`; `Catalog.scan` may build its own per call) and passes it as `limiter=`; `session()` holds one token for its lifetime.
- **Bounds (`bounds.py`).** `list_*` follow at most 100 pages / 5000 items, stop on a repeated cursor and run under one deadline. Tool, resource
  and prompt results are cut at 10 MB (longest strings first): `CallResult.truncated`, `"truncated": true` on each trimmed resource content dict,
  top-level `"truncated": true` on a prompt result; the UI shows it.
- **Scrubbing (`scrub.py`).** `session()` builds a `Scrubber` from the transport `prepare()` expanded (env values, expanded args, headers incl. Codex
  bearer/`env_http_headers`, secret URL parts, what each `${VAR}` became) and applies it to error messages, `stderr_tail` and listings, so
  nothing real enters `catalog.json` or an API error. Values under 4 characters are not scrubbed. Successful tool/resource/prompt output is not
  scrubbed (the user asked for it). A stdio line that is not JSON-RPC is logged as one short line, not a traceback.
- **Scans are non-interactive.** `Catalog.scan` forces `ConnectOptions.interactive=False`: `choose_auth` still uses stored OAuth tokens, but a needed
  sign-in raises `AuthRequired` (409 `needs_auth`) and the entry is recorded `status="needs_auth"`; only an explicit Connect opens a browser.
- Wrap connect in `anyio.fail_after(connect_timeout)` and calls in `fail_after(call_timeout)` -> `OperationTimeout`. Any other exception (after flattening
  groups) -> `ConnectFailed(message, stderr_tail=...)`.

```python
# catalog.py
class Catalog:
    def __init__(self, path: Path); load(); get(entry_id, fingerprint) -> CatalogEntry | None; put(CatalogEntry); drop(entry_id); all() -> list[CatalogEntry]
    async def scan(self, entries, paths, opts, *, limiter, oauth=None) -> list[CatalogEntry]   # gather bounded by limiter; each error recorded, never raises
```

`oauth.py`: `FileTokenStorage(path: Path)` implements `TokenStorage` over a 0600 JSON file. `OAuthHook(redirect_uri: str, open_browser=webbrowser.open)` is built by
the server with `redirect_uri=ServerSettings.redirect_uri`; core never guesses the port. `hook.handlers() -> (redirect_handler, callback_handler)` returns closures
sharing one slot: the redirect handler parses `state` from the authorization URL, registers an `anyio.Event` under it and opens the browser; the callback
handler awaits that event and returns the `AuthorizationCodeResult`. `hook.complete(code, state, iss=None) -> bool` is called by the server route (False -> HTTP 400
unknown state). `make_provider(server_url, hook, storage, *, scope=None, client_name="mcp-browser") -> OAuthClientProvider`.

Uvicorn runs with one process and no reload, so Windows keeps the Proactor loop that subprocess stdio needs. A stdio call through the API is part of the tests that
run on Windows CI.

## 8. Server API — `packages/server`

`ServerSettings` (`settings.py`, frozen dataclass): `paths: Paths`, `token: str`, `port=8765`, `max_concurrency=8`, `connect_timeout=30.0`, `call_timeout=300.0`;
`HOST = "127.0.0.1"` is a constant (loopback only, no host option); properties `allowed_hosts = {"127.0.0.1:{port}", "localhost:{port}"}` and
`redirect_uri = "http://127.0.0.1:{port}/oauth/callback"`.

Security middleware (`auth.py`), in order: (1) `Host` header must be in `allowed_hosts` else 400; (2) if `Origin` present it must be
`http(s)://<allowed host>` else 403; (3) paths matching `/api/*` require `Authorization: Bearer <token>` (constant-time compare) else 401. Token-free
allowlist (literal): `/healthz`, `/oauth/callback`, `/`, `/static/*`. Token: `<state>/token` (create 0600, `secrets.token_urlsafe(32)`). Every response carries `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'` (Alpine's standard build needs `unsafe-eval`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`. Responses never
include env/header values unless the route is `reveal`. Error body: `{"error": code, "message": str, "detail": {...}}` with the status from §2
(`McpBrowserError.to_body()`).

Request/response models are in `api_models.py` (the contract for the UI): `HealthResponse`, `ErrorBody`, `ServersResponse`, `ServerDetail`, `AddRequest`,
`UpdateRequest`, `ConnectRequest`, `ScanRequest`, `CallRequest`, `ReadResourceRequest`, `GetPromptRequest`.

| method path | request model | response | errors |
|---|---|---|---|
| GET /healthz | — | `{"ok":true,"version":str,"pid":int}` | — |
| GET /api/clients | — | `list[ClientInfo]` | |
| GET /api/projects | — | `list[str]` | |
| GET /api/servers | `?refresh=1` | `ServersResponse{entries: list[ServerEntry] (masked), catalog: list[CatalogEntry], warnings}` | |
| GET /api/servers/{id} | — | `ServerDetail{entry (masked), catalog: CatalogEntry\|null}` | 404 |
| GET /api/servers/{id}/reveal | — | `ServerEntry` unmasked | 404 |
| POST /api/servers | `AddRequest{name, transport, extra?, targets: list[Target], allow_comment_loss=false}` | `list[AddResult]` (status 200) | 409 name_exists/comments_would_be_lost (nothing written), 400 invalid_arguments, 422, 403 |
| PUT /api/servers/{id} | `UpdateRequest{transport?, extra?, name?, allow_comment_loss=false}` | `WriteReport` | 400 invalid_arguments, 403, 404, 409, 422 |
| DELETE /api/servers/{id} | `?allow_comment_loss=` | `WriteReport` | 403, 404, 409 |
| POST /api/servers/{id}/connect | `ConnectRequest{connect_timeout?}` | `CatalogEntry` (also stored) | 400 unresolved_placeholders, 502, 504 |
| POST /api/servers/scan | `ScanRequest{ids?: list[str], confirm_untrusted=false}` | `list[CatalogEntry]`; header `X-Skipped-Untrusted: N` | no ids: untrusted entries are skipped (counted in the header); listed untrusted ids: 409 confirmation_required unless `confirm_untrusted` |
| POST /api/servers/{id}/tools/{tool}/call | `CallRequest{arguments: dict, call_timeout?}` | `CallResult` | 400 invalid_arguments (jsonschema Draft 2020-12 validate), 404, 502, 504 |
| POST /api/servers/{id}/resources/read | `ReadResourceRequest{uri}` | `list[dict]` | 502, 504 |
| POST /api/servers/{id}/prompts/{name} | `GetPromptRequest{arguments}` | `dict` | 502, 504 |
| GET /oauth/callback | `?code&state&iss?` | HTML "you can close this tab" | 400 unknown state |
| GET / and /static/* | — | files via importlib.resources | |

Untrusted entries (`ServerEntry.untrusted`, set by discovery for scope `project`; `core/trust.py`): `connect`, tool `call`, `resources/read`, `prompts/{name}` and
`scan` with explicit ids answer `409 confirmation_required` unless the request body has `confirm_untrusted: true` (on `ConnectRequest`, `CallRequest`,
`ReadResourceRequest`, `GetPromptRequest`, `ScanRequest`; per request, never persisted). `detail` = `{entry_id, name, config_path, kind, command, args, cwd | url, header_names, host
(url authority without userinfo; null for stdio), env_vars (names only: ${VAR}, $VAR, ${env:VAR}, %VAR% in command/args/env/cwd/url/headers plus Codex
bearer_token_env_var, env_http_headers values and env_vars passthrough), inherits_environment (stdio), entries: [same for each untrusted id]}`. Claude Code's
`projects[<key>].disabledMcpjsonServers` makes matching project entries `enabled=false`. The UI shows `detail` in a confirm dialog and resends with the flag;
`needs_auth` catalog entries get a "Sign in & connect" button; `truncated` results show a "truncated at 10 MB" note.

Masking (`secrets.mask_entry`): every value in `transport.env`, `transport.headers`, and `extra` keys in
`SECRET_KEYS = {"env","headers","http_headers","env_http_headers","bearer_token_env_var","oauth","auth"}` -> `"•••"` (values only, keys kept).
It also masks URL userinfo and URL query values whose key contains one of `key|token|secret|auth|password`, and args that follow or embed in
a flag matching the same words (`--api-key x`, `--token=x`).
The editor loads unmasked data through `/reveal`. `POST` and `PUT` reject (`invalid_arguments`) any request in which a value equals `"•••"`
(`secrets.contains_mask`), so a masked value is never persisted.
`app.create_app(settings: ServerSettings) -> Starlette`; shared state on `app.state`: `settings`, `paths`, `catalog`, `oauth_hook`, `limiter`
(`anyio.CapacityLimiter(settings.max_concurrency)`), `discovery_cache`.

## 9. Web UI — `packages/server/src/mcp_browser_server/static/`

No build, no CDN. `index.html` is a shell: `<head>` with css links, `<body>` with `<div id="app">` and one
`<script type="module" src="/static/js/main.js">`. Alpine is vendored as an ES module: `alpinejs@3.17.5` `dist/module.esm.js` saved as
`static/vendor/alpine.esm.js`. `main.js` imports it, reads `#token=` from `location.hash`, stores it in `sessionStorage.mcpBrowserToken`,
clears the hash with `history.replaceState`, inserts the view templates (each `views/*.js` exports `export const template = \`…\``) into the DOM
as `<template x-if="view==='…'">` slots (list / detail / editor), calls `Alpine.data("app", app)` (from `app.js`), then `Alpine.start()`.
There is no `deferLoadingAlpine` and no `x-data` script tag; the root element gets `x-data="app"` before `Alpine.start()`.

State (`app.js`): `{ token, view: "list"|"detail"|"editor", entries, catalog: Map<id, CatalogEntry>, clients, projects, query,
filters: {client, scope, status}, selected: ServerEntry|null, revealed: ServerEntry|null, busy: Set<id>, toast, rawJson: bool }`.
Boot then calls `api.get("/api/servers")`.

Components: list view (search box, client/scope chips, rows with status badge, "Connect", "Scan all"), detail view
(entry fields masked, read-only banner with reason, stderr tail, tools/resources/prompts tabs, tool form via `schema_form.js`,
raw JSON toggle, result pane), editor dialog (name, transport kind radio, fields, env/headers key-value rows, extra JSON textarea,
multi-select target clients disabled when capability missing, per-target results from `list[AddResult]`, comment-loss confirm
(hidden when the error has `detail.can_override == false`; then the UI says to edit the file in the app), delete confirm naming the file).

`schema_form.js`: `buildForm(schema) -> FormModel` and `toArgs(model) -> object`; `schema_render.js`: `render(model) -> string`. Supports
string/number/integer/boolean/enum/array(of scalars)/object(nested one level); `$ref/oneOf/anyOf/allOf` or deeper -> JSON textarea.
`search.js`: `matches(entry, catalogEntry, query) -> bool` (lowercase tokens, all must appear in name|client|command/url|tool names|descriptions).

## 10. CLI + daemon — `packages/cli`

`mcp-browser [serve] [--port 8765] [--no-open]`: the server always binds 127.0.0.1 (no `--host`, no `--allow-remote`). Runs uvicorn in foreground
(one process, no reload), prints URL with `#token=`, opens browser unless `--no-open`.
`start [--port]`: if pid file alive -> print status; else `Popen(cmd, stdin=DEVNULL, stdout=stderr=open(<state>/server.log,"ab"))` where `cmd =
[sys.executable, "serve", "--no-open", ...]` if `getattr(sys, "frozen", False)` else `[sys.executable, "-m", "mcp_browser", "serve", "--no-open", ...]`.
Detach with `start_new_session=True` on POSIX; the Windows `creationflags=DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW` live only under
`if sys.platform == "win32":` so pyright and POSIX stay clean. Write `<state>/server.pid` JSON `{pid, port}`; poll `/healthz` up to 10 s; open browser.
`stop`: read the pid file, GET `/healthz`, and signal (SIGTERM / `TerminateProcess`) only when the `pid` in the `/healthz` body equals the pid file's pid,
so a recycled pid is never killed; wait 5 s, remove pid. A dead server or mismatched pid just clears the file. `status`: pid alive + `/healthz` via
`urllib.request` -> prints running/stopped, exit code 0/1. `open`: opens URL with token.

**Ownership and launcher (hardening).** A server counts as ours only when the pid file's pid is alive and `/healthz` on its port reports that same pid (`runtime.find_running`); any other listener (port squatter) is never trusted, never receives the token, and `serve`/`start`/`open`/`status` print that the port is taken by something else (`status` still reports stopped). On Linux only, the browser is opened on `file://<state>/launch.html` (mode 0600, `location.replace` to the tokenized URL, removed after 5 s or on the next run) so the token never appears in the browser's argv; other systems open the URL directly, and the URL is always printed as a fallback for confined browsers. `serve` exits through `SystemExit` on SIGTERM so the pid file is removed (regression-tested).

## 11. Packaging, CI, release

Root `pyproject.toml`: `[project]` stub with `package = false` (not published), `[tool.uv.workspace] members = ["packages/*"]`, `[tool.uv.sources]` for the
three packages `{ workspace = true }`, dev group `ruff pyright pytest anyio` plus the members; `[tool.ruff] line-length = 110`;
`[tool.pyright] typeCheckingMode = "strict"`; pytest `--import-mode=importlib`.
Sibling deps pinned exactly (`mcp-browser-core==X.Y.Z`); one `version` string copied in three `pyproject.toml` (release.yml checks they match).
Runtime deps: core `mcp>=2.3,<3`, `httpx2>=2.10` (imported directly), `anyio`, `pydantic>=2.12`, `tomlkit`, `json5`, `filelock`; server `starlette`, `uvicorn`, `jsonschema`
(platformdirs is not used: `Paths` computes per-OS locations so any platform can be simulated).

`scripts/check_lines.py` lists files with `git ls-files --cached --others --exclude-standard`, so it works before the first commit (Wave 0 runs `git init`; nobody
commits). It checks py/js/css/html, excluding `static/vendor/` and `uv.lock`. The devcontainer sets `containerEnv.UV_PROJECT_ENVIRONMENT=/home/vscode/.venv`,
keeping the venv out of the bind mount. `.gitignore` covers `*.log`, `.venv`, `dist`, `build`, `__pycache__`, `*.spec`. Ruff excludes `*.md` and `static/vendor`.

`ci.yml`: on push/PR, matrix `[ubuntu-latest, macos-latest, windows-latest]`, `actions/checkout` v7.0.1 and `astral-sh/setup-uv` v10.3.3 (both pinned to full commit SHAs with a version comment; PyInstaller pinned to `==6.22.3`),
`uv sync --all-packages --locked`, `uv run ruff check . && uv run ruff format --check .`, `uv run pyright`, `uv run pytest`, `uv run python scripts/check_lines.py`.
`release.yml`: on tag `v*`: job publish (`uv build --package …` core, server, cli in that order; `uv publish` with trusted publishing);
job binaries matrix `[macos-latest, macos-15-intel, windows-latest, ubuntu-22.04]`: `uv run pyinstaller --onedir --name mcp-browser
--collect-data mcp_browser_server --collect-submodules uvicorn --collect-all pydantic_core --collect-all mcp_browser_core --collect-all mcp packaging/pyinstaller_entry.py`,
zip, `sha256sum` -> `SHA256SUMS.txt`, `gh release create "$TAG" dist/*.zip SHA256SUMS.txt --generate-notes`.
`uv tool install "git+<repo>#subdirectory=packages/cli"` was tested in Wave 0 on a committed scratch copy (`git+file://…`): uv finds the
workspace root above the subdirectory, so `mcp-browser-core` and `mcp-browser-server` resolve from their `{ workspace = true }` sources and install
alongside the CLI (`mcp-browser` executable created). Workstream E re-checks it once against the real remote and documents it in the README as the
no-PyPI install path, together with `uv tool install mcp-browser` (PyPI) and `git clone && uv sync --all-packages && uv run mcp-browser`.

## 12. Tests — `tests/`

`conftest.py`: autouse fixture `isolated_env(tmp_path, monkeypatch)` clears then sets `HOME, USERPROFILE, APPDATA, LOCALAPPDATA, XDG_CONFIG_HOME,
XDG_STATE_HOME, MCP_BROWSER_STATE_DIR` under `tmp_path` (and removes `CLAUDE_CONFIG_DIR`, `CODEX_HOME`) and returns a `Paths` built from that environ; `paths` fixture
returns it; `paths_for(platform)` factory builds a `Paths` for darwin/win32/linux on any OS; `build_environ(root)` is importable; `anyio_backend` is `asyncio`.
`fixture_server.py`: `mcp` SDK server (`MCPServer`, see §7) with tools `echo(text)`, `add(a:int,b:int)`, `slow(seconds)`, `fail()`; stdio transport; tests
reference it as `[sys.executable, path]`. Async tests use `@pytest.mark.anyio`.
API tests use `starlette.testclient.TestClient(create_app(settings))` with a known token.

## 13. Workstreams

**Wave 0 — one agent, freezes interfaces (done).** Owns: root files, `.devcontainer/`, `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `LICENSE`, all three
`pyproject.toml`, `uv.lock`, `models.py`, `catalog_models.py`, `errors.py`, `paths.py` (complete for all three platforms), `specs/base.py`, `dialects/__init__.py`
(Protocol), `settings.py`, `api_models.py`, `tests/conftest.py`, `scripts/check_lines.py`, package skeletons with `py.typed`, and typed `NotImplementedError` stubs of every
module signature in §6-§8 so Wave 1 codes against real imports. Also verified the SDK names in §7 against the installed package; this file matches it.

**Wave 1a — four parallel agents (A, B, D, E), disjoint files.** Each may add tests only under its own test files and fixtures.

| ws | owns | depends on | acceptance |
|---|---|---|---|
| A config | `specs/*` (except `base.py`), `formats/*`, `dialects/*` (except `__init__.py` Protocol), `discovery.py`, `writer.py`, `mutate.py`, `secrets.py`, `tests/core/test_{paths,formats,secrets,dialect_*,discovery,writer,mutate}.py`, `tests/fixtures/configs/*` | Wave 0 | all 12 specs discover fixtures on 3 simulated OSes; round-trip per dialect; writer preserves indent/newline/mode/unknown keys and symlinks, makes backups (none for a new file), raises on comments (Zed: `can_override=false`) and on concurrent change (simulate by mutating file inside `mutate` callback); `add` preflight writes nothing on failure; masking rules and `contains_mask` |
| B mcp | `expand.py`, `transports.py`, `connect.py`, `catalog.py`, `oauth.py`, `tests/fixtures/fixture_server.py`, `tests/core/test_{expand,connect_e2e,catalog}.py` | Wave 0 | e2e: connect fixture server, list 4 tools, call `add` -> 3, `slow(5)` with timeout 1 -> `OperationTimeout`, `fail()` -> `is_error`; stderr tail captured; unresolved placeholder raises; a `CapacityLimiter(8)` caps concurrent sessions at 8; http and sse round trips against fixture servers; exception groups flattened |
| D ui | `static/**` | Wave 0 (`api_models.py` shapes) | opens offline against a stub JSON server; list/search/filter; connect button; schema form for all supported types + fallback; raw JSON toggle; editor with multi-target, capability-disabled checkboxes, per-target `AddResult` display, comment-loss (and `can_override=false`) and delete confirms; token moved from hash to sessionStorage; Alpine boots through `main.js` |
| E cli+pkg | `packages/cli/*`, `packaging/*`, `.github/workflows/*`, `README.md`, `tests/cli/*` | Wave 0 | `mcp-browser --help`; `start`/`status`/`stop` cycle with Popen mocked and with a real serve in devcontainer; pid file JSON; stop refuses a pid that `/healthz` does not confirm; frozen detection; workflows lint-valid; README sections: install, security model, per-client paths, cloud connectors not supported, Windows ACL note, Gatekeeper/SmartScreen, SHA256 |

**Wave 1b — one agent (C) after A and B finish**, against the real modules with no mocks.

| ws | owns | depends on | acceptance |
|---|---|---|---|
| C api | `packages/server` except `static/`, `tests/server/*` | A, B merged | TestClient: 401 without token, 400 bad Host, 403 bad Origin, allowlist works; CRUD on a temp Cursor config; `POST /api/servers` returns `list[AddResult]`; masking and `•••` rejection; `invalid_arguments` on schema violation; error body shape; `/healthz` pid; a real stdio connect + call through the API |

Verify (every workstream): `devcontainer exec --workspace-folder . uv run ruff check . && devcontainer exec --workspace-folder . uv run ruff format --check .`,
`… uv run pyright`, `… uv run pytest tests/<own dir>`, `… uv run python scripts/check_lines.py`.

**Wave 2 — integration.** One agent runs the full suite, starts `uv run mcp-browser serve --no-open`
in the devcontainer and exercises the API with `curl` (token from `<state>/token`) against fixture configs copied under the isolated HOME;
two reviewer agents cross-review A<->B and C<->D for interface drift, secrets in logs, line limits; fixes land in the owning files.
Final: `uv run pytest` green on all three CI OSes.

## 14. Definition of done

- CI green on ubuntu/macos/windows: ruff, pyright strict, pytest, line check.
- Fresh devcontainer: `uv run mcp-browser` opens the UI; every client's fixture config is listed; Connect on the fixture server
  lists tools and a tool call returns; add/edit/delete/rename round-trips on JSON, JSONC (with confirm) and TOML without touching
  other keys or comments (TOML); backups appear in the state dir.
- Read-only sources (plugins, extensions) are listed with a reason and are connectable but not editable.
- No `/api/*` request succeeds without the bearer token; requests with a foreign `Host` or `Origin` are rejected.
- `grep -r` over the repo finds no personal names, usernames, emails or absolute home paths.
- Release workflow produces PyPI packages and four `--onedir` zips with SHA256SUMS.

## 15. Non-goals

No registry/marketplace install, no multi-user or remote hosting (loopback only), no secrets vault or env management, no Claude cloud connectors
(claude.ai) — not in any file, documented in README, no enable/disable toggles beyond preserving `enabled`/`disabled` fields,
no websocket transport, no resolution of VS Code `${input:*}` (the entry is listed and the connect error explains why), no editing of plugin/extension sources,
no persistent server sessions, no comment preservation in JSONC (explicitly confirmed loss; Zed's shared settings file is never rewritten when it has comments),
no auto-restart of client apps.
