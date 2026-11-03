// Server detail: fields, banners, tabs, tool form, call result.
export const template = `
<template x-if="view === 'detail' && selected">
<section aria-label="Server detail">
  <button type="button" class="link" @click="back()">&larr; All servers</button>
  <div class="toolbar">
    <h2 class="grow" x-text="selected.name"></h2>
    <button type="button" class="primary" @click="connect(selected)" :disabled="busy[selected.id] || !selected.transport">
      <span class="spin" x-show="busy[selected.id]"></span> <span x-text="connectLabel(selected)"></span></button>
    <button type="button" @click="editEntry(selected)" :disabled="selected.read_only">Edit</button>
    <button type="button" class="danger" @click="askDelete(selected)" :disabled="selected.read_only">Delete</button>
  </div>
  <div class="banner warn" x-show="selected.untrusted">
    Project config file: anything in it may be hostile. You are asked to confirm before it runs or is contacted.
    <span x-show="selected.enabled === false">Claude Code has this server disabled.</span>
  </div>
  <div class="banner warn" x-show="selected.read_only">
    Read-only: <span x-text="selected.read_only_reason || 'this entry cannot be edited here'"></span>
  </div>
  <p class="muted small">Connect starts the configured command (or contacts its URL) so it can list tools; calling a tool runs it for real.</p>
  <dl class="fields">
    <dt>Client</dt><dd x-text="clientName(selected.client_id) + ' (' + selected.scope + ')'"></dd>
    <dt>Config file</dt><dd class="mono small" x-text="selected.config_path"></dd>
    <dt x-show="selected.project">Project</dt><dd x-show="selected.project" class="mono small" x-text="selected.project"></dd>
    <dt>Transport</dt><dd x-text="selected.transport ? selected.transport.kind : 'unsupported'"></dd>
    <dt>Target</dt><dd class="mono small" x-text="summary(selected)"></dd>
    <dt x-show="selected.transport && selected.transport.env && Object.keys(selected.transport.env).length">Env</dt>
    <dd x-show="selected.transport && selected.transport.env && Object.keys(selected.transport.env).length" class="mono small"
        x-text="selected.transport && selected.transport.env ? Object.keys(selected.transport.env).join(', ') + ' (values hidden)' : ''"></dd>
    <dt x-show="selected.transport && selected.transport.headers && Object.keys(selected.transport.headers).length">Headers</dt>
    <dd x-show="selected.transport && selected.transport.headers && Object.keys(selected.transport.headers).length" class="mono small"
        x-text="selected.transport && selected.transport.headers ? Object.keys(selected.transport.headers).join(', ') + ' (values hidden)' : ''"></dd>
  </dl>
  <p class="err-text" x-show="selected.error" x-text="selected.error"></p>
  <div class="banner err" x-show="errors[selected.id]">
    <p x-text="errors[selected.id] && errors[selected.id].message"></p>
    <template x-if="errors[selected.id] && errors[selected.id].stderr">
      <details open><summary>Server stderr</summary><pre x-text="errors[selected.id].stderr"></pre></details></template>
  </div>
  <p class="muted" x-show="!cat() && !busy[selected.id]">Not scanned yet. Use Connect to list tools, resources and prompts.</p>
  <template x-if="cat()">
    <div>
      <p class="muted small">Scanned <span x-text="cat().scanned_at"></span>
        <span class="err-text" x-show="cat().status === 'error'"> &middot; failed: <span x-text="cat().error"></span></span></p>
      <details x-show="cat().stderr_tail"><summary>Server stderr</summary><pre x-text="cat().stderr_tail"></pre></details>
      <div class="tabs" role="tablist">
        <button type="button" role="tab" :aria-selected="tab === 'tools'" @click="setTab('tools')" x-text="'Tools (' + cat().tools.length + ')'"></button>
        <button type="button" role="tab" :aria-selected="tab === 'resources'" @click="setTab('resources')" x-text="'Resources (' + cat().resources.length + ')'"></button>
        <button type="button" role="tab" :aria-selected="tab === 'prompts'" @click="setTab('prompts')" x-text="'Prompts (' + cat().prompts.length + ')'"></button>
      </div>
      <div x-show="tab === 'tools'">
        <ul class="rows"><template x-for="t in cat().tools" :key="t.name">
          <li class="row-item" :class="tool && tool.name === t.name ? 'sel' : ''">
            <div class="grow"><button type="button" class="link name" @click="pickTool(t)" x-text="t.name"></button>
              <p class="muted small" x-text="t.description || ''"></p></div>
          </li></template></ul>
        <div class="panel" x-show="tool">
          <h3 x-text="tool ? tool.name : ''"></h3>
          <div class="row"><button type="button" class="link" @click="toggleRaw()" x-text="rawJson ? 'Use form' : 'Edit as raw JSON'"></button></div>
          <div class="schema-form" x-show="!rawJson" x-effect="mount($el, formKey)"></div>
          <div x-show="rawJson"><label for="raw-args">Arguments (JSON object)</label>
            <textarea id="raw-args" rows="8" class="mono" spellcheck="false" x-model="rawText"></textarea></div>
          <p class="err-text" role="alert" x-show="callError" x-text="callError"></p>
          <pre x-show="callStderr" x-text="callStderr"></pre>
          <button type="button" class="primary" @click="callTool()" :disabled="!!busy['call:' + (tool && tool.name)]">
            <span class="spin" x-show="busy['call:' + (tool && tool.name)]"></span> Call tool</button>
          <template x-if="result">
            <div class="result" :class="result.is_error ? 'is-err' : ''" aria-live="polite">
              <p class="small"><strong x-text="result.is_error ? 'Tool returned an error' : 'Result'"></strong>
                <span class="muted" x-text="' ' + result.duration_ms + ' ms'"></span></p>
              <p class="err-text small" x-show="result.truncated">Result truncated at 10 MB.</p>
              <template x-for="(b, i) in result.content" :key="i"><pre x-text="blockText(b)"></pre></template>
              <template x-if="structured()"><details><summary>Structured content</summary><pre x-text="structured()"></pre></details></template>
              <details x-show="result.stderr_tail"><summary>Server stderr</summary><pre x-text="result.stderr_tail"></pre></details>
            </div>
          </template>
        </div>
      </div>
      <div x-show="tab === 'resources'">
        <p class="muted" x-show="!cat().resources.length">No resources.</p>
        <ul class="rows"><template x-for="r in cat().resources" :key="r.uri"><li class="row-item">
          <div class="grow"><div class="mono small" x-text="r.uri"></div>
            <p class="muted small" x-text="[r.name, r.mime_type, r.description].filter(Boolean).join(' - ')"></p></div>
          <button type="button" @click="readResource(r)" :disabled="!!busy['res:' + r.uri]">Read</button></li></template></ul>
      </div>
      <div x-show="tab === 'prompts'">
        <p class="muted" x-show="!cat().prompts.length">No prompts.</p>
        <ul class="rows"><template x-for="p in cat().prompts" :key="p.name"><li class="row-item" x-init="initArgs(p.name)">
          <div class="grow"><strong x-text="p.name"></strong><p class="muted small" x-text="p.description || ''"></p>
            <template x-for="a in p.arguments" :key="a.name"><div class="field">
              <label :for="'pa-' + p.name + a.name" x-text="a.name + (a.required ? ' *' : '')"></label>
              <input :id="'pa-' + p.name + a.name" type="text" x-model="promptArgs[p.name][a.name]" autocomplete="off"></div></template></div>
          <button type="button" @click="getPrompt(p)" :disabled="!!busy['prm:' + p.name]">Get</button></li></template></ul>
      </div>
      <p class="err-text" role="alert" x-show="tab !== 'tools' && callError" x-text="callError"></p>
      <div class="panel" x-show="output && tab !== 'tools'"><h3 x-text="output ? output.title : ''"></h3>
        <p class="err-text small" x-show="output && output.truncated">Result truncated at 10 MB.</p>
        <pre x-text="output ? output.text : ''"></pre></div>
    </div>
  </template>
</section>
</template>`;
