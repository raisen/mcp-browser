// JSON Schema -> form model, and back to an arguments object. Pure data, no DOM.
// Supported: string, number, integer, boolean, enum, array of scalars, object nested one level.
// Anything else (refs, oneOf/anyOf/allOf, deeper nesting) falls back to a JSON textarea.
const COMPLEX = ["$ref", "oneOf", "anyOf", "allOf", "not", "if", "patternProperties"];
const SCALARS = ["string", "number", "integer", "boolean"];

function kindOf(s) {
  if (!s || typeof s !== "object" || COMPLEX.some((k) => k in s)) return "json";
  if (Array.isArray(s.enum) && s.enum.length && s.enum.every((v) => typeof v === "string" || typeof v === "number")) return "enum";
  let t = s.type;
  if (Array.isArray(t)) { const rest = t.filter((x) => x !== "null"); t = rest.length === 1 ? rest[0] : null; }
  if (SCALARS.includes(t)) return t;
  if (t === "array") return s.items && SCALARS.includes(s.items.type) && !COMPLEX.some((k) => k in s.items) ? "array" : "json";
  if (t === "object") return s.properties ? "object" : "json";
  return "json";
}

function toText(kind, v) {
  if (v === undefined || v === null) return "";
  if (kind === "array") return Array.isArray(v) ? v.join("\n") : String(v);
  if (kind === "json") return JSON.stringify(v, null, 2);
  return v;
}

function own(obj, k) {
  return obj && typeof obj === "object" && Object.hasOwn(obj, k) ? obj[k] : undefined;
}

function makeField(key, schema, required, depth, init) {
  let kind = kindOf(schema);
  if (kind === "object" && depth >= 1) kind = "json";
  const f = {
    key, kind, required, schema,
    label: key,
    description: typeof schema?.description === "string" ? schema.description : "",
    options: kind === "enum" ? schema.enum.map(String) : [],
    itemType: kind === "array" ? schema.items.type : "",
  };
  const start = init !== undefined ? init : schema?.default;
  f.defaultValue = kind === "boolean" ? schema?.default === true : undefined;
  if (kind === "object") {
    const req = Array.isArray(schema.required) ? schema.required : [];
    f.children = Object.entries(schema.properties).map(([k, s]) =>
      makeField(k, s, req.includes(k), depth + 1, own(start, k)));
  } else if (kind === "boolean") {
    f.value = start === undefined ? f.defaultValue : Boolean(start);
  } else {
    f.value = toText(kind, start);
    if (kind === "enum") f.value = start === undefined ? "" : String(start);
  }
  return f;
}

export function buildForm(schema, initial) {
  const props = schema && typeof schema === "object" && schema.type === "object" && schema.properties
    && !COMPLEX.some((k) => k in schema) ? schema.properties : null;
  if (!props) {
    return { mode: "json", fields: [], jsonText: initial ? JSON.stringify(initial, null, 2) : "{}" };
  }
  const req = Array.isArray(schema.required) ? schema.required : [];
  const fields = Object.entries(props).map(([k, s]) =>
    makeField(k, s, req.includes(k), 0, own(initial, k)));
  return { mode: "form", fields, jsonText: "" };
}

function scalar(kind, text, label) {
  if (kind === "string" || kind === "enum") return text;
  if (kind === "boolean") return Boolean(text);
  const n = Number(text);
  if (!Number.isFinite(n) || (kind === "integer" && !Number.isInteger(n))) {
    throw new Error(`${label}: expected ${kind === "integer" ? "an integer" : "a number"}`);
  }
  return n;
}

function fieldValue(f) {
  // returns undefined when the field should be omitted
  if (f.kind === "object") {
    const obj = collect(f.children);
    return Object.keys(obj).length || f.required ? obj : undefined;
  }
  if (f.kind === "boolean") return f.required || f.value !== f.defaultValue ? f.value : undefined;
  const text = typeof f.value === "string" ? f.value : String(f.value ?? "");
  if (f.kind === "json") {
    if (!text.trim()) return undefined;
    try { return JSON.parse(text); } catch { throw new Error(`${f.label}: invalid JSON`); }
  }
  if (f.kind === "array") {
    const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
    if (!lines.length && !f.required) return undefined;
    return lines.map((l) => scalar(f.itemType, l, f.label));
  }
  if (text === "") {
    if (f.required && f.kind === "string") return "";
    if (f.required) throw new Error(`${f.label} is required`);
    return undefined;
  }
  if (f.kind === "enum") return f.schema.enum.find((o) => String(o) === text);
  return scalar(f.kind, text, f.label);
}

function collect(fields) {
  const out = Object.create(null); // keys come from a third-party schema: never "__proto__"
  for (const f of fields) {
    const v = fieldValue(f);
    if (v !== undefined) out[f.key] = v;
  }
  return out;
}

export function toArgs(model) {
  if (model.mode === "json") {
    let v;
    try { v = JSON.parse(model.jsonText || "{}"); } catch { throw new Error("Arguments are not valid JSON"); }
    if (!v || typeof v !== "object" || Array.isArray(v)) throw new Error("Arguments must be a JSON object");
    return v;
  }
  return collect(model.fields);
}
