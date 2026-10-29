/* SPDX-License-Identifier: AGPL-3.0-only */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() { this.value = ''; this.children = []; this.handlers = {}; this.dataset = {}; this.disabled = false; }
  get options() { return this.children; }
  append(child) { this.children.push(child); }
  appendChild(child) { this.append(child); return child; }
  replaceChildren(...children) { this.children = children; this.value = ''; }
  addEventListener(type, handler) { this.handlers[type] = handler; }
}

(async () => {
  const elements = new Map(), calls = [], loadHandlers = [];
  const get = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  let authenticated = true, backend = 'api';
  const profiles = () => [
    { id: 'openaicompatible', label: 'Existing API', model: 'existing-model', endpoint: 'https://example.invalid/v1', configured: true },
    { id: 'codex', label: 'Codex', model: 'Default', configured: authenticated },
  ];
  const location = { href: 'http://127.0.0.1:19739/?api=openaicompatible', hash: '' };
  const scope = vm.createContext({
    document: { getElementById: get, createElement: () => new Element(), createTextNode: text => ({ textContent: text }), querySelectorAll: () => [] },
    window: { addEventListener: (name, callback) => { if (name === 'load') loadHandlers.push(callback); } },
    location, history: { replaceState: (_, __, url) => { location.href = String(url); } }, URL,
    MutationObserver: class { observe() {} }, setTimeout: () => 1, clearTimeout() {}, console,
    fetch: async (url, options) => {
      calls.push({ url, method: options?.method || 'GET' });
      let result = { status: 'success' };
      if (url === '/api/reading/config') {
        if (options?.method === 'POST') backend = JSON.parse(options.body).backend || backend;
        result = { ...result, profiles: profiles(), selected: backend === 'codex' ? 'codex' : 'openaicompatible',
          options: { backend, codexModel: '', documentMode: 'auto', pdfProtocol: 'auto', searchProvider: 'auto' } };
      } else if (url === '/api/capabilities') result = { ...result, readingSearch: true, fullPageImageReading: true };
      else if (url === '/api/layout-settings') result = { ...result, settings: { preserveColumns: true, mathMode: 'auto' } };
      else if (url === '/api/paper-chat/config') result = { ...result, codex: { available: true, authenticated, message: 'Local status' } };
      else if (url.startsWith('/api/paper-chat/models')) result = { ...result, models: [] };
      else if (url === '/api/model-backend') result = { ...result, settings: { translationBackend: 'api', model: '' } };
      else if (url === '/api/reading/jobs') result = { ...result, jobs: [] };
      else if (url === '/api/reading/documents') result = { ...result, document: { id: 'a'.repeat(32), filename: 'synthetic.pdf', pages: 2 } };
      else if (url === '/translatedInfo') result = { ...result, files: [] };
      else throw new Error('Unexpected route ' + url);
      return { ok: true, json: async () => result };
    },
  });
  vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, '../payload/web/reading.js'), 'utf8'), scope);
  await loadHandlers[0]();
  await get('readingExisting').handlers.change({ target: { value: 'synthetic.pdf' } });
  assert.equal(get('readingProvider').value, 'openaicompatible');
  assert.equal(get('startReading').disabled, false);
  get('readingBackend').value = 'codex';
  get('translationBackend').value = 'codex';
  await get('saveModelBackend').handlers.click();
  assert.equal(get('readingProvider').value, 'codex', 'Saving Codex must override the previous API and URL query');
  authenticated = false;
  // Refresh without the original query to exercise login expiry and retained selection.
  location.href = 'http://127.0.0.1:19739/';
  await get('refreshSharedApi').handlers.click();
  assert.equal(get('readingProvider').value, 'codex', 'Login expiry must not silently choose the paid API');
  assert.equal(get('startReading').disabled, true);
  get('readingProvider').value = 'openaicompatible';
  get('readingProvider').handlers.change();
  assert.equal(get('startReading').disabled, false, 'An explicit API selection can enable reading');
  assert.equal(calls.filter(call => call.url === '/api/reading/jobs' && call.method === 'POST').length, 0);
  console.log('Reading backend selection and expired-login billing isolation passed');
})().catch(error => { console.error(error); process.exit(1); });
