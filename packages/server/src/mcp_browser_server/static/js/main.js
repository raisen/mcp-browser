// Boot: take the token from the URL hash, mount the view templates, start Alpine.
import Alpine from "../vendor/alpine.esm.js";
import { setToken } from "./api.js";
import { app } from "./app.js";
import { head, tail } from "./views/common.js";
import { template as list } from "./views/list.js";
import { template as detail } from "./views/detail.js";
import { template as editor } from "./views/editor.js";

const match = /[#&]token=([^&]+)/.exec(location.hash);
if (match) {
  setToken(decodeURIComponent(match[1]));
  history.replaceState(null, "", location.pathname + location.search);
}

const root = document.getElementById("app");
root.setAttribute("x-data", "app");
// The templates are static strings; no server data is ever interpolated into them.
root.innerHTML = head + list + detail + editor + tail;

Alpine.data("app", app);
Alpine.start();
