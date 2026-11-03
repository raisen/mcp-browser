// Thin fetch wrapper. The bearer token lives only in sessionStorage and is never logged.
const KEY = "mcpBrowserToken";

export class ApiError extends Error {
  constructor(status, code, message, detail) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail || {};
  }
}

export function getToken() {
  try { return sessionStorage.getItem(KEY) || ""; } catch { return ""; }
}

export function setToken(token) {
  try { sessionStorage.setItem(KEY, token); } catch { /* storage blocked: token stays unset */ }
}

async function request(method, path, body) {
  const headers = { Authorization: `Bearer ${getToken()}` };
  const init = { method, headers };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, "network", "Cannot reach the mcp-browser server. Is it still running?", {});
  }
  let data = null;
  const text = await res.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = null; }
  }
  if (!res.ok) {
    const code = data && data.error ? data.error : res.status === 401 ? "unauthorized" : "http_" + res.status;
    const message = (data && data.message) || res.statusText || "Request failed";
    throw new ApiError(res.status, code, message, (data && data.detail) || {});
  }
  return data;
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body === undefined ? {} : body),
  put: (path, body) => request("PUT", path, body),
  del: (path) => request("DELETE", path),
};

export const enc = encodeURIComponent;
