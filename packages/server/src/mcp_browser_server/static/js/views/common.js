// Static page chrome: header, banners, toast, confirm dialog. Only x-text for dynamic text.
export const head = `
<header class="top">
  <h1><a href="#" @click.prevent="back()">MCP Browser</a></h1>
  <span class="muted small" x-show="loaded" x-text="entries.length + ' servers across ' + clients.length + ' clients'"></span>
</header>
<div class="banner err" role="alert" x-show="authFailed" x-cloak>
  Not authorized. Reopen the URL printed by <code>mcp-browser open</code> (it carries a fresh access token), then reload.
</div>
<div class="banner err" role="alert" x-show="error && !authFailed" x-cloak x-text="error"></div>
<div class="banner ok" role="status" x-show="toast" x-cloak>
  <span x-text="toast"></span>
  <button type="button" class="link" @click="toast = ''">Dismiss</button>
</div>
<main>`;

export const tail = `
</main>
<dialog class="confirm" aria-labelledby="confirm-title"
        x-effect="confirm ? ($el.open || $el.showModal()) : ($el.open && $el.close())"
        @close="cancelConfirm()">
  <h2 id="confirm-title" x-text="confirm ? confirm.title : ''"></h2>
  <p x-text="confirm ? confirm.body : ''"></p>
  <pre class="small" x-show="confirm && confirm.detail" x-text="confirm ? confirm.detail : ''"></pre>
  <div class="row end">
    <button type="button" @click="cancelConfirm()">Cancel</button>
    <button type="button" :class="confirm && confirm.danger ? 'danger' : 'primary'" @click="confirmYes()"
            x-text="confirm ? confirm.ok : ''"></button>
  </div>
</dialog>`;
