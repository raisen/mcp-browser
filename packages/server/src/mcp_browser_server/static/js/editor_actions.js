// Add / edit / delete. Secrets are loaded from /reveal only when the editor opens.
import { api, enc } from "./api.js";

const MASK = "•••";
const rows = (obj) => Object.entries(obj || {}).map(([k, v]) => ({ k, v: String(v), show: false }));

function blank() {
  return {
    mode: "add", id: null, name: "", kind: "stdio", command: "", argsText: "", cwd: "", envFile: "",
    url: "", env: [], headers: [], extraText: "", oauth: null, targets: [], results: null,
    error: "", saving: false, loading: false, done: null, locked: null,
  };
}

function toDict(list, label) {
  const out = Object.create(null); // a "__proto__" row must stay a plain key
  for (const r of list) {
    if (!r.k.trim()) continue;
    if (r.v === MASK) throw new Error(`${label} "${r.k}" still holds a masked value. Close and reopen the editor.`);
    out[r.k.trim()] = r.v;
  }
  return out;
}

export const editorActions = {
  ed: blank(),

  targetsFor() {
    const seen = new Map();
    const add = (c, scope, project) => {
      const key = [c.id, scope, project || ""].join("|");
      if (seen.has(key)) return;
      const label = scope === "user" ? "user" : `${scope}: ${project}`;
      seen.set(key, { key, client_id: c.id, scope, project: project || null, caps: c.capabilities,
        label: `${c.display_name} · ${label}`, checked: false });
    };
    for (const c of this.clients) {
      add(c, "user", null);
      for (const p of c.config_paths) if (["local", "project"].includes(p.scope) && p.project) add(c, p.scope, p.project);
      if (c.capabilities.project_scope) this.projects.forEach((p) => add(c, "project", p));
    }
    return [...seen.values()];
  },
  targetOff(t) {
    const caps = t.caps || {};
    return caps.editable === false || caps[this.ed.kind] === false;
  },
  targetWhy(t) {
    if (!this.targetOff(t)) return "";
    return (t.caps || {}).editable === false ? "This client is read-only here" : `${this.ed.kind} servers are not supported by this client`;
  },
  onKind() { this.ed.targets.forEach((t) => { if (this.targetOff(t)) t.checked = false; }); },

  newEntry() {
    this.ed = blank();
    this.ed.targets = this.targetsFor();
    this.view = "editor";
    this.error = "";
  },
  async editEntry(e) {
    this.ed = blank();
    this.ed.mode = "edit"; this.ed.id = e.id; this.ed.loading = true; this.view = "editor"; this.error = "";
    try {
      const r = await api.get(`/api/servers/${enc(e.id)}/reveal`);
      const t = r.transport || {};
      Object.assign(this.ed, {
        name: r.name, kind: t.kind || "stdio", command: t.command || "", argsText: (t.args || []).join("\n"),
        cwd: t.cwd || "", envFile: t.env_file || "", url: t.url || "", oauth: t.oauth || null,
        env: rows(t.env), headers: rows(t.headers), extraText: Object.keys(r.extra || {}).length ? JSON.stringify(r.extra, null, 2) : "",
        locked: { client: this.clientName(r.client_id), path: r.config_path, scope: r.scope, project: r.project, client_id: r.client_id },
      });
    } catch (x) { this.fail(x); this.ed.error = x.message; } finally { this.ed.loading = false; }
  },
  addRow(key) { this.ed[key].push({ k: "", v: "", show: false }); },
  dropRow(key, i) { this.ed[key].splice(i, 1); },

  payload() {
    const d = this.ed;
    if (!d.name.trim()) throw new Error("Name is required");
    let transport;
    if (d.kind === "stdio") {
      if (!d.command.trim()) throw new Error("Command is required");
      transport = { kind: "stdio", command: d.command.trim(), args: d.argsText.split("\n").filter((l) => l !== ""),
        env: toDict(d.env, "Variable"), cwd: d.cwd.trim() || null, env_file: d.envFile.trim() || null };
    } else {
      if (!d.url.trim()) throw new Error("URL is required");
      transport = { kind: d.kind, url: d.url.trim(), headers: toDict(d.headers, "Header"), oauth: d.oauth };
    }
    let extra = {};
    if (d.extraText.trim()) {
      try { extra = JSON.parse(d.extraText); } catch { throw new Error("Extra fields are not valid JSON"); }
      if (!extra || typeof extra !== "object" || Array.isArray(extra)) throw new Error("Extra fields must be a JSON object");
    }
    return { name: d.name.trim(), transport, extra };
  },

  async save(allowLoss = false) {
    const d = this.ed;
    d.error = ""; d.done = null;
    let body;
    try { body = this.payload(); } catch (x) { d.error = x.message; return; }
    const targets = d.targets.filter((t) => t.checked && !this.targetOff(t));
    if (d.mode === "add" && !targets.length) { d.error = "Choose at least one client to add this server to."; return; }
    d.saving = true;
    try {
      if (d.mode === "add") {
        const res = await api.post("/api/servers", { ...body, allow_comment_loss: allowLoss,
          targets: targets.map((t) => ({ client_id: t.client_id, scope: t.scope, project: t.project })) });
        d.results = res;
        res.forEach((r) => { if (r.report) { const t = d.targets.find((x) => x.key === [r.target.client_id, r.target.scope, r.target.project || ""].join("|")); if (t) t.checked = false; } });
        const ok = res.filter((r) => r.report);
        if (ok.length) this.say(`Added to ${ok.length} of ${res.length} target(s).` + this.restartHint(ok[0].target.client_id));
      } else {
        const rep = await api.put(`/api/servers/${enc(d.id)}`, { ...body, allow_comment_loss: allowLoss });
        d.done = rep;
        this.say(`Saved ${rep.path}.` + this.restartHint(d.locked && d.locked.client_id));
      }
      await this.load(false);
    } catch (x) { this.writeFailed(x, () => this.save(true)); } finally { d.saving = false; }
  },

  writeFailed(x, retry) {
    if (x.status === 401) this.fail(x);
    if (x.code === "comments_would_be_lost") {
      if (x.detail && x.detail.can_override === true) {
        this.ask({ title: "Comments will be removed", ok: "Rewrite without comments", danger: true, run: retry,
          body: "The config file contains comments. Saving rewrites it as plain JSON and drops them. A backup copy is kept." });
        return;
      }
      this.ed.error = "This file contains comments and is shared with other settings, so mcp-browser will not rewrite it. Edit it in the client app directly.";
      return;
    }
    this.ed.error = x.message + (x.detail && x.detail.placeholders ? ` (${x.detail.placeholders.join(", ")})` : "");
  },

  askDelete(e) {
    this.ask({ title: `Delete "${e.name}"?`, ok: "Delete", danger: true,
      body: `This removes the server from ${e.config_path}. A backup of that file is kept.`,
      run: () => this.remove(e, false) });
  },
  async remove(e, allowLoss) {
    this.error = "";
    try {
      const rep = await api.del(`/api/servers/${enc(e.id)}?allow_comment_loss=${allowLoss}`);
      this.say(`Deleted ${e.name} from ${rep.path}.` + this.restartHint(e.client_id));
      this.selected = null; this.view = "list";
      await this.load(false);
    } catch (x) {
      this.writeFailed(x, () => this.remove(e, true));
      if (this.ed.error) { this.error = this.ed.error; this.ed.error = ""; }
    }
  },
  targetLabel(t) { return `${this.clientName(t.client_id)} · ${t.scope === "user" ? "user" : t.scope + ": " + t.project}`; },
};
