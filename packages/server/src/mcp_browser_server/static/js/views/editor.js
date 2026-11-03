// Add / edit form. Env and header values are password inputs with a per-row reveal toggle.
const kv = (key, title, addLabel) => `
  <fieldset class="kv">
    <legend>${title}</legend>
    <template x-for="(row, i) in ed.${key}" :key="i">
      <div class="kv-row">
        <label class="sr" :for="'${key}-k' + i">Name</label>
        <input :id="'${key}-k' + i" type="text" placeholder="Name" x-model="row.k" autocomplete="off" spellcheck="false">
        <label class="sr" :for="'${key}-v' + i">Value</label>
        <input :id="'${key}-v' + i" :type="row.show ? 'text' : 'password'" placeholder="Value" x-model="row.v"
               autocomplete="new-password" spellcheck="false">
        <button type="button" @click="row.show = !row.show" :aria-pressed="row.show" x-text="row.show ? 'Hide' : 'Show'"></button>
        <button type="button" @click="dropRow('${key}', i)" aria-label="Remove row">&times;</button>
      </div>
    </template>
    <button type="button" @click="addRow('${key}')">${addLabel}</button>
  </fieldset>`;

export const template = `
<template x-if="view === 'editor'">
<form class="editor" @submit.prevent="save(false)" aria-label="Server editor">
  <button type="button" class="link" @click="back()">&larr; All servers</button>
  <h2 x-text="ed.mode === 'add' ? 'Add server' : 'Edit server'"></h2>
  <p class="muted" x-show="ed.loading" role="status"><span class="spin"></span> Loading values...</p>
  <div class="banner warn" x-show="ed.locked">
    Editing in <span x-text="ed.locked && ed.locked.client"></span>:
    <span class="mono small" x-text="ed.locked && ed.locked.path"></span>
  </div>
  <fieldset :disabled="ed.loading || ed.saving" class="plain">
    <div class="field"><label for="ed-name">Name</label>
      <input id="ed-name" type="text" x-model="ed.name" required autocomplete="off" spellcheck="false"></div>
    <fieldset class="radios"><legend>Transport</legend>
      <label><input type="radio" value="stdio" x-model="ed.kind" @change="onKind()"> stdio (local command)</label>
      <label><input type="radio" value="http" x-model="ed.kind" @change="onKind()"> streamable HTTP</label>
      <label><input type="radio" value="sse" x-model="ed.kind" @change="onKind()"> SSE</label>
    </fieldset>
    <div x-show="ed.kind === 'stdio'">
      <div class="field"><label for="ed-cmd">Command</label>
        <input id="ed-cmd" type="text" x-model="ed.command" class="mono" autocomplete="off" spellcheck="false"></div>
      <div class="field"><label for="ed-args">Arguments <span class="muted small">(one per line)</span></label>
        <textarea id="ed-args" rows="3" x-model="ed.argsText" class="mono" spellcheck="false"></textarea></div>
      <div class="field"><label for="ed-cwd">Working directory <span class="muted small">(optional)</span></label>
        <input id="ed-cwd" type="text" x-model="ed.cwd" class="mono" autocomplete="off"></div>
      <div class="field"><label for="ed-envfile">Env file <span class="muted small">(optional)</span></label>
        <input id="ed-envfile" type="text" x-model="ed.envFile" class="mono" autocomplete="off"></div>
      ${kv("env", "Environment variables", "Add variable")}
    </div>
    <div x-show="ed.kind !== 'stdio'">
      <div class="field"><label for="ed-url">URL</label>
        <input id="ed-url" type="url" x-model="ed.url" class="mono" autocomplete="off" spellcheck="false"></div>
      ${kv("headers", "Headers", "Add header")}
    </div>
    <div class="field"><label for="ed-extra">Extra fields <span class="muted small">(JSON object, kept as-is in the config)</span></label>
      <textarea id="ed-extra" rows="3" x-model="ed.extraText" class="mono" spellcheck="false"></textarea></div>
    <fieldset class="targets" x-show="ed.mode === 'add'"><legend>Add to</legend>
      <p class="muted small" x-show="!ed.targets.length">No editable clients were found.</p>
      <template x-for="t in ed.targets" :key="t.key">
        <label class="target" :class="targetOff(t) ? 'off' : ''" :title="targetWhy(t)">
          <input type="checkbox" x-model="t.checked" :disabled="targetOff(t)">
          <span x-text="t.label"></span>
          <span class="muted small" x-show="targetOff(t)" x-text="'(' + targetWhy(t) + ')'"></span>
        </label>
      </template>
    </fieldset>
  </fieldset>
  <p class="err-text" role="alert" x-show="ed.error" x-text="ed.error"></p>
  <ul class="results" x-show="ed.results" aria-live="polite">
    <template x-for="(r, i) in ed.results || []" :key="i">
      <li :class="r.error ? 'err-text' : 'ok-text'">
        <strong x-text="targetLabel(r.target)"></strong>:
        <span x-show="r.error" x-text="r.error"></span>
        <span x-show="r.report"><span x-text="r.report && ('written to ' + r.report.path)"></span>
          <span x-show="r.report && r.report.backup_path" class="muted small" x-text="r.report && r.report.backup_path ? ' (backup ' + r.report.backup_path + ')' : ''"></span></span>
      </li>
    </template>
  </ul>
  <p class="ok-text" role="status" x-show="ed.done">
    <span x-text="ed.done ? 'Saved to ' + ed.done.path + '.' : ''"></span>
    <span x-text="ed.locked ? restartHint(ed.locked.client_id) : ''"></span></p>
  <div class="row">
    <button type="submit" class="primary" :disabled="ed.loading || ed.saving">
      <span class="spin" x-show="ed.saving"></span> <span x-text="ed.mode === 'add' ? 'Add' : 'Save'"></span></button>
    <button type="button" @click="back()" x-text="ed.results || ed.done ? 'Done' : 'Cancel'"></button>
  </div>
</form>
</template>`;
