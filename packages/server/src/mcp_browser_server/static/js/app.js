// Root Alpine component: shared state, loading, list actions. Detail and editor actions are mixins.
import { ApiError, api, enc } from "./api.js";
import { matches } from "./search.js";
import { detailActions } from "./detail_actions.js";
import { editorActions } from "./editor_actions.js";

const base = {
  view: "list", entries: [], catalog: {}, clients: [], projects: [], warnings: [],
  query: "", filters: { client: "", scope: "", status: "" },
  loading: false, loaded: false, authFailed: false, error: "", toast: "", toastTimer: null,
  selected: null, busy: {}, errors: {}, confirm: null,

  async init() {
    window.addEventListener("keydown", (ev) => {
      const t = ev.target;
      const typing = t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName));
      if (ev.key === "/" && !typing && !ev.metaKey && !ev.ctrlKey && !ev.altKey) {
        const box = document.getElementById("search");
        if (box) { ev.preventDefault(); this.view = "list"; box.focus(); }
      }
    });
    await this.load(false);
  },

  fail(e) {
    if (e.status === 401) this.authFailed = true;
    this.error = e.message || String(e);
  },

  say(text) {
    this.toast = text;
    clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => { this.toast = ""; }, 12000);
  },

  async load(refresh) {
    this.loading = true;
    this.error = "";
    try {
      const [s, clients, projects] = await Promise.all([
        api.get("/api/servers" + (refresh ? "?refresh=1" : "")),
        api.get("/api/clients"), api.get("/api/projects")]);
      this.entries = s.entries;
      this.warnings = s.warnings || [];
      this.catalog = Object.fromEntries(s.catalog.map((c) => [c.entry_id, c]));
      this.clients = clients;
      this.projects = projects;
      this.authFailed = false;
      if (this.selected) this.selected = this.entries.find((e) => e.id === this.selected.id) || null;
      if (!this.selected && this.view === "detail") this.view = "list";
    } catch (e) { this.fail(e); } finally { this.loading = false; this.loaded = true; }
  },

  visible() {
    const f = this.filters;
    return this.entries.filter((e) =>
      (!f.client || e.client_id === f.client) && (!f.scope || e.scope === f.scope)
      && (!f.status || this.status(e).key === f.status)
      && matches(e, this.catalog[e.id], this.query));
  },
  scopes() { return [...new Set(this.entries.map((e) => e.scope))].sort(); },
  clientName(id) { const c = this.clients.find((x) => x.id === id); return c ? c.display_name : id; },
  filtering() { return Boolean(this.query || this.filters.client || this.filters.scope || this.filters.status); },
  summary(e) {
    const t = e.transport;
    if (!t) return e.error || "unsupported entry";
    return t.kind === "stdio" ? [t.command, ...(t.args || [])].join(" ") : t.url;
  },
  status(e) {
    if (this.busy[e.id]) return { key: "busy", label: "connecting" };
    if (e.error || !e.transport) return { key: "invalid", label: "unsupported" };
    const c = this.catalog[e.id];
    if (!c) return { key: "unscanned", label: "not scanned" };
    if (c.status === "needs_auth") return { key: "needs_auth", label: "sign-in needed" };
    return c.status === "ok"
      ? { key: "ok", label: `${c.tools.length} tools` } : { key: "error", label: "failed" };
  },
  scanLabel() { return this.filtering() ? `Scan ${this.visible().length} shown` : "Scan all"; },

  connectLabel(e) { return this.status(e).key === "needs_auth" ? "Sign in & connect" : "Connect"; },

  // POST that, on 409 confirmation_required (project config), shows what would run and resends once confirmed.
  async guarded(path, body) {
    try { return await api.post(path, body); } catch (e) {
      if (e.code !== "confirmation_required") throw e;
      if (!(await this.askUntrusted(e.detail))) throw new ApiError(0, "cancelled", "Cancelled: not confirmed.", {});
      return api.post(path, { ...body, confirm_untrusted: true });
    }
  },
  askUntrusted(d) {
    const lines = [];
    if (d.kind === "stdio") {
      lines.push(`Runs: ${d.command}`, `Arguments: ${(d.args || []).map((a) => JSON.stringify(a)).join(" ") || "(none)"}`);
      if (d.cwd) lines.push(`Working directory: ${d.cwd}`);
      lines.push("The program also receives your whole environment.");
    } else {
      lines.push(`Contacts: ${d.url}`, `Host: ${d.host || "(unknown)"}`);
      if ((d.header_names || []).length) lines.push(`Headers sent: ${d.header_names.join(", ")}`);
    }
    lines.push(`Environment variables it reads: ${(d.env_vars || []).join(", ") || "none"}`);
    return new Promise((resolve) => {
      this.confirm = {
        title: `Run "${d.name}" from a project config?`, ok: "Run it", danger: true,
        body: "This entry comes from a file inside a project folder, so whoever wrote it chose what runs. Check it before going on.",
        detail: lines.join("\n"), run: () => resolve(true), cancel: () => resolve(false),
      };
    });
  },
  cancelConfirm() {
    const c = this.confirm;
    this.confirm = null;
    if (c && c.cancel) c.cancel();
  },

  async connect(e) {
    this.busy[e.id] = true;
    delete this.errors[e.id];
    try {
      const c = await this.guarded(`/api/servers/${enc(e.id)}/connect`, {});
      this.catalog[c.entry_id] = c;
    } catch (x) {
      if (x.status === 401) this.fail(x);
      if (x.code === "cancelled") return;
      this.errors[e.id] = { message: x.message, stderr: (x.detail && x.detail.stderr_tail) || "" };
    } finally { delete this.busy[e.id]; }
  },

  askScan() {
    const usable = this.visible().filter((e) => e.transport);
    const ids = usable.filter((e) => !e.untrusted).map((e) => e.id);
    const skipped = usable.length - ids.length;
    const note = skipped
      ? ` ${skipped} project config ${skipped === 1 ? "entry is" : "entries are"} skipped; open one and press Connect to confirm it individually.` : "";
    if (!ids.length) { this.say(`Nothing to scan.${note}`); return; }
    this.ask({
      title: `${this.scanLabel()}?`, ok: "Run and scan",
      body: `This runs the configured command (or contacts the URL) of ${ids.length} server(s) to list their tools. Servers that need sign-in are marked, not opened.${note}`,
      run: () => this.scan(ids),
    });
  },
  async scan(ids) {
    ids.forEach((id) => { this.busy[id] = true; });
    try {
      const out = await api.post("/api/servers/scan", { ids });
      out.forEach((c) => { this.catalog[c.entry_id] = c; });
    } catch (x) { this.fail(x); } finally { ids.forEach((id) => { delete this.busy[id]; }); }
  },

  ask(spec) { this.confirm = spec; },
  async confirmYes() {
    const c = this.confirm;
    this.confirm = null;
    if (c && c.run) await c.run();
  },
  restartHint(clientId) {
    const c = this.clients.find((x) => x.id === clientId);
    return c && c.needs_restart ? ` Restart ${c.display_name} for the change to take effect.` : "";
  },
  back() { this.view = "list"; this.error = ""; },
};

export function app() {
  return Object.assign({}, base, detailActions, editorActions);
}
