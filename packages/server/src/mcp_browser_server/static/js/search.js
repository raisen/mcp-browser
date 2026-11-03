// Client-side search: every lowercase token must appear somewhere in the haystack.
export function haystack(entry, cat) {
  const t = entry.transport;
  const parts = [entry.name, entry.client_id, entry.scope, entry.project || ""];
  if (t) {
    parts.push(t.kind);
    if (t.kind === "stdio") parts.push(t.command, ...(t.args || []));
    else parts.push(t.url);
  }
  if (cat) {
    for (const tool of cat.tools || []) parts.push(tool.name, tool.description || "");
    for (const r of cat.resources || []) parts.push(r.uri, r.name || "");
    for (const p of cat.prompts || []) parts.push(p.name, p.description || "");
  }
  return parts.join(" ").toLowerCase();
}

export function matches(entry, cat, query) {
  const tokens = (query || "").toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return true;
  const hay = haystack(entry, cat);
  return tokens.every((tok) => hay.includes(tok));
}
