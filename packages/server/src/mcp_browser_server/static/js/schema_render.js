// Form model -> DOM nodes. Built with createElement/textContent only: schema strings are
// untrusted (they come from third-party MCP servers) and are never parsed as HTML.
let uid = 0;

function el(tag, props = {}, text) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}

function control(f, id) {
  let c;
  if (f.kind === "boolean") {
    c = el("input", { type: "checkbox", id });
    c.checked = Boolean(f.value);
    c.addEventListener("change", () => { f.value = c.checked; });
    return c;
  }
  if (f.kind === "enum") {
    c = el("select", { id });
    if (!f.required) c.append(el("option", { value: "" }, "(not set)"));
    for (const o of f.options) c.append(el("option", { value: o }, o));
    c.value = f.value;
    c.addEventListener("change", () => { f.value = c.value; });
    return c;
  }
  if (f.kind === "array" || f.kind === "json") {
    c = el("textarea", { id, rows: f.kind === "json" ? "4" : "3", spellcheck: "false" });
    if (f.kind === "json") c.classList.add("mono");
  } else {
    c = el("input", { id, type: f.kind === "string" ? "text" : "number", autocomplete: "off" });
    if (f.kind === "integer") c.step = "1"; else if (f.kind === "number") c.step = "any";
  }
  c.value = f.value ?? "";
  c.addEventListener("input", () => { f.value = c.value; });
  return c;
}

function hint(f) {
  if (f.kind === "array") return `one ${f.itemType} per line`;
  if (f.kind === "json") return "JSON";
  return "";
}

function renderField(f) {
  if (f.kind === "object") {
    const set = el("fieldset", { class: "sub" });
    set.append(el("legend", {}, f.label + (f.required ? " *" : "")));
    if (f.description) set.append(el("p", { class: "muted small" }, f.description));
    for (const child of f.children) set.append(renderField(child));
    return set;
  }
  const id = "sf" + ++uid;
  const wrap = el("div", { class: f.kind === "boolean" ? "field inline" : "field" });
  const label = el("label", { for: id }, f.label + (f.required ? " *" : ""));
  const h = hint(f);
  if (h) label.append(el("span", { class: "muted small" }, ` (${h})`));
  const c = control(f, id);
  wrap.append(...(f.kind === "boolean" ? [c, label] : [label, c]));
  if (f.description) wrap.append(el("p", { class: "muted small" }, f.description));
  return wrap;
}

export function render(model, container) {
  container.replaceChildren();
  if (model.mode === "json") {
    const id = "sf" + ++uid;
    const ta = el("textarea", { id, rows: "6", class: "mono", spellcheck: "false" });
    ta.value = model.jsonText;
    ta.addEventListener("input", () => { model.jsonText = ta.value; });
    container.append(
      el("p", { class: "muted small" }, "This tool's schema is not simple enough for a form. Enter the arguments as JSON."),
      el("label", { for: id }, "Arguments (JSON object)"), ta);
    return;
  }
  if (!model.fields.length) container.append(el("p", { class: "muted small" }, "This tool takes no arguments."));
  for (const f of model.fields) container.append(renderField(f));
}
