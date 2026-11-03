// Detail view: tabs, tool form, calls, resource and prompt output.
import { enc } from "./api.js";
import { buildForm, toArgs } from "./schema_form.js";
import { render } from "./schema_render.js";

let liveForm = null; // kept outside Alpine state so typing in the form never re-renders it

function shorten(value) {
  // Replace long base64 payloads so results stay readable.
  if (Array.isArray(value)) return value.map(shorten);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) =>
      [k, (k === "data" || k === "blob") && typeof v === "string" && v.length > 120 ? `<${v.length} characters of data>` : shorten(v)]));
  }
  return value;
}

export const detailActions = {
  tab: "tools", tool: null, formKey: 0, rawJson: false, rawText: "{}",
  result: null, callError: "", callStderr: "", output: null, promptArgs: Object.create(null),

  open(e) {
    this.selected = e;
    this.view = "detail";
    this.error = "";
    this.tab = "tools";
    this.tool = null; this.result = null; this.output = null; this.callError = "";
    liveForm = null;
    window.scrollTo(0, 0);
  },
  initArgs(name) { if (!this.promptArgs[name]) this.promptArgs[name] = Object.create(null); },
  cat() { return this.selected ? this.catalog[this.selected.id] || null : null; },
  setTab(t) { this.tab = t; this.output = null; this.callError = ""; },

  pickTool(t) {
    this.tool = t;
    liveForm = buildForm(t.input_schema || {});
    this.formKey++;
    this.rawJson = false;
    this.result = null; this.callError = ""; this.callStderr = "";
    this.rawText = "{}";
  },
  mount(el) { if (liveForm) render(liveForm, el); },
  toggleRaw() {
    this.callError = "";
    try {
      if (!this.rawJson) {
        this.rawText = JSON.stringify(toArgs(liveForm), null, 2);
        this.rawJson = true;
      } else {
        const args = JSON.parse(this.rawText || "{}");
        if (!args || typeof args !== "object" || Array.isArray(args)) throw new Error("Arguments must be a JSON object");
        liveForm = buildForm(this.tool.input_schema || {}, args);
        this.formKey++;
        this.rawJson = false;
      }
    } catch (e) { this.callError = e.message; }
  },

  async callTool() {
    const key = "call:" + this.tool.name;
    this.callError = ""; this.callStderr = ""; this.result = null;
    let args;
    try { args = this.rawJson ? JSON.parse(this.rawText || "{}") : toArgs(liveForm); } catch (e) {
      this.callError = e instanceof SyntaxError ? "Arguments are not valid JSON" : e.message;
      return;
    }
    this.busy[key] = true;
    try {
      this.result = await this.guarded(`/api/servers/${enc(this.selected.id)}/tools/${enc(this.tool.name)}/call`, { arguments: args });
    } catch (e) {
      if (e.status === 401) this.fail(e);
      this.callError = e.message;
      this.callStderr = (e.detail && e.detail.stderr_tail) || "";
      if (e.code === "invalid_arguments" && e.detail && e.detail.errors) this.callError += " " + JSON.stringify(e.detail.errors);
    } finally { delete this.busy[key]; }
  },
  blockText(b) { return b.type === "text" && typeof b.text === "string" ? b.text : JSON.stringify(shorten(b), null, 2); },
  structured() { return this.result && this.result.structured ? JSON.stringify(this.result.structured, null, 2) : ""; },

  async fetchOutput(key, title, path, body) {
    this.busy[key] = true; this.output = null; this.callError = "";
    try {
      const data = await this.guarded(path, body);
      const cut = Array.isArray(data) ? data.some((c) => c && c.truncated) : Boolean(data && data.truncated);
      this.output = { title, text: JSON.stringify(shorten(data), null, 2), truncated: cut };
    } catch (e) {
      if (e.status === 401) this.fail(e);
      this.callError = e.message;
    } finally { delete this.busy[key]; }
  },
  readResource(r) {
    return this.fetchOutput("res:" + r.uri, r.uri, `/api/servers/${enc(this.selected.id)}/resources/read`, { uri: r.uri });
  },
  getPrompt(p) {
    const args = Object.create(null);
    for (const [k, v] of Object.entries(this.promptArgs[p.name] || {})) if (v !== "") args[k] = v;
    return this.fetchOutput("prm:" + p.name, p.name, `/api/servers/${enc(this.selected.id)}/prompts/${enc(p.name)}`, { arguments: args });
  },
};
