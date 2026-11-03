// Server list: search, filters, rows, Connect, Scan.
export const template = `
<template x-if="view === 'list'">
<section aria-label="Servers">
  <div class="toolbar">
    <label class="grow"><span class="sr">Search servers and tools</span>
      <input id="search" type="search" placeholder="Search servers, commands, tools (press /)" x-model="query" autocomplete="off">
    </label>
    <button type="button" class="primary" @click="newEntry()">Add server</button>
    <button type="button" @click="askScan()" :disabled="!entries.length" x-text="scanLabel()"></button>
    <button type="button" @click="load(true)" :disabled="loading">Refresh</button>
  </div>
  <div class="toolbar filters">
    <label>Client
      <select x-model="filters.client"><option value="">All</option>
        <template x-for="c in clients" :key="c.id"><option :value="c.id" x-text="c.display_name"></option></template>
      </select></label>
    <label>Scope
      <select x-model="filters.scope"><option value="">All</option>
        <template x-for="s in scopes()" :key="s"><option :value="s" x-text="s"></option></template>
      </select></label>
    <label>Status
      <select x-model="filters.status"><option value="">All</option>
        <option value="ok">scanned</option><option value="error">failed</option>
        <option value="needs_auth">sign-in needed</option><option value="unscanned">not scanned</option><option value="invalid">unsupported</option>
      </select></label>
  </div>
  <p class="muted small">Connecting runs the configured command (or contacts its URL) to list the server's tools.</p>
  <div class="banner warn" x-show="warnings.length" x-cloak>
    <template x-for="w in warnings" :key="w"><p x-text="w"></p></template>
  </div>
  <p class="muted" x-show="loading && !loaded" role="status"><span class="spin"></span> Loading...</p>
  <div class="empty" x-show="loaded && !entries.length && !error" x-cloak>
    <h2>No MCP servers found</h2>
    <p>None of the supported clients (Claude Desktop, Claude Code, Codex, Gemini CLI, Cursor, VS Code, Windsurf, Zed, Cline) has a server configured yet.</p>
    <button type="button" class="primary" @click="newEntry()">Add your first server</button>
  </div>
  <p class="muted" x-show="loaded && entries.length && !visible().length" x-cloak>No servers match.</p>
  <ul class="rows" x-show="entries.length">
    <template x-for="e in visible()" :key="e.id">
      <li class="row-item">
        <div class="grow">
          <div class="title">
            <button type="button" class="link name" @click="open(e)" x-text="e.name"></button>
            <span class="badge" :class="'b-' + status(e).key"><span class="spin" x-show="busy[e.id]"></span>
              <span x-text="status(e).label"></span></span>
            <span class="badge" x-show="e.read_only">read-only</span>
            <span class="badge" x-show="e.enabled === false">disabled</span>
            <span class="badge b-untrusted" x-show="e.untrusted" title="Came from a project config file">project config</span>
          </div>
          <div class="muted small"><span x-text="clientName(e.client_id)"></span> &middot; <span x-text="e.scope"></span>
            <span x-show="e.project"> &middot; <span x-text="e.project"></span></span></div>
          <div class="mono small clip" x-text="summary(e)"></div>
          <p class="err-text small" x-show="errors[e.id]" x-text="errors[e.id] && errors[e.id].message"></p>
        </div>
        <button type="button" @click="connect(e)" :disabled="busy[e.id] || !e.transport"
                :title="'Runs the configured command to list tools'" x-text="connectLabel(e)"></button>
      </li>
    </template>
  </ul>
</section>
</template>`;
