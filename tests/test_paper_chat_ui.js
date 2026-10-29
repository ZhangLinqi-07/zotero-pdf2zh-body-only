/* SPDX-License-Identifier: AGPL-3.0-only */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Node {
  constructor(doc, tag, text = '') {
    this.ownerDocument = doc; this.tagName = tag; this.localName = tag; this.namespaceURI = 'http://www.w3.org/1999/xhtml'; this.children = []; this.parentNode = null;
    this.style = { cssText: '' }; this.attributes = {}; this.listeners = {}; this._text = text;
    this._value = undefined; this.scrollTop = 0; this.scrollHeight = 120; this.clientHeight = 100;
  }
  set textContent(text) { this._text = String(text); this.children = []; }
  get textContent() { return this._text + this.children.map(node => node.textContent).join(''); }
  set value(value) { this._value = value; }
  get value() { return this._value ?? (this.tagName === 'select' ? this.children[0]?.value || '' : ''); }
  appendChild(child) { child.remove(); child.parentNode = this; this.children.push(child); return child; }
  insertBefore(child, other) { child.remove(); const i = this.children.indexOf(other); child.parentNode = this; this.children.splice(i < 0 ? this.children.length : i, 0, child); return child; }
  replaceChildren(...nodes) { this._text = ''; for (const child of this.children) child.parentNode = null; this.children = []; for (const node of nodes) this.appendChild(node); }
  remove() { if (this.parentNode) { this.parentNode.children.splice(this.parentNode.children.indexOf(this), 1); this.parentNode = null; } }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
  removeEventListener(name, listener) { this.listeners[name] = (this.listeners[name] || []).filter(item => item !== listener); }
  async trigger(name, event = {}) { for (const listener of this.listeners[name] || []) await listener({ target: this, preventDefault() {}, ...event }); }
  focus() { this.focused = true; }
  contains(other) { return this === other || this.children.some(node => node.contains(other)); }
  closest(tag) { return this.tagName === tag ? this : this.parentNode?.closest(tag); }
  get parentElement() { return this.parentNode; }
}

function fixture({ existingReader = false, lateToolbar = false } = {}) {
  const listeners = {}, calls = [], prefs = {}, timers = new Map(); let timerID = 0;
  const win = { JSON, setTimeout(fn) { timers.set(++timerID, fn); return timerID; }, clearTimeout(id) { timers.delete(id); }, addEventListener() {}, removeEventListener() {} };
  const doc = { defaultView: win, createElementNS(ns, tag) { return new Node(doc, tag); }, createTextNode(text) { return new Node(doc, '#text', text); } };
  const host = new Node(doc, 'div'), iframe = new Node(doc, 'iframe'); host.appendChild(iframe);
  const nativeToolbar = new Node(doc, 'div');
  doc.toolbarReady = !lateToolbar;
  doc.querySelector = selector => selector === '[data-kinbo-chat-toggle]'
    ? nativeToolbar.children.find(node => node.getAttribute('data-kinbo-chat-toggle') === 'true') || null
    : doc.toolbarReady && ['.toolbar .end', '.toolbar'].includes(selector) ? nativeToolbar : null;
  const pageDiv = new Node(doc, 'div');
  const characters = text => [...text].map((u, index) => ({ u, rect: [index, 0, index + 1, 10] }));
  const fullPages = ['FULL FIRST PAGE', 'FULL FINAL PAGE'];
  const reader = { itemID: 1, _iframe: iframe, _iframeWindow: { document: doc }, navigate: async value => { reader.navigated = value; },
    _internalReader: { _primaryView: { _iframeWindow: { JSON, PDFViewerApplication: {
      pdfDocument: { numPages: 2, getPageData: async ({ pageIndex }) => ({ chars: characters(fullPages[pageIndex]) }) },
      pdfViewer: { getPageView: () => ({ div: pageDiv, viewport: { convertToViewportRectangle: value => value } }) },
    } } } } };
  const session = { id: 'a'.repeat(32), messages: [], busy: false };
  const observers = new Map();
  const context = vm.createContext({
    Zotero: {
      Prefs: { get: name => prefs[name], set: (name, value) => { prefs[name] = value; } },
      Reader: { _readers: existingReader ? [reader] : [], getByTabID: () => reader,
        registerEventListener: (name, listener) => { listeners[name] = listener; }, unregisterEventListener: name => { delete listeners[name]; } },
      Notifier: { registerObserver: observer => { observers.set(1, observer); return 1; }, unregisterObserver: id => observers.delete(id) },
      Items: { get: () => ({ key: 'PDFKEY12', libraryID: 1, parentID: null, getField: () => 'Synthetic paper' }) },
      HTTP: { request: async (method, url, options) => {
        const data = options.body ? JSON.parse(options.body) : undefined; calls.push({ method, url, data });
        if (url.endsWith('/config')) return { status: 200, response: { status: 'success', active: 'openai', profiles: [{ id: 'openai', label: 'API', model: 'fixture-model' }], codex: { available: true, authenticated: true } } };
        if (url.includes('/models?')) return { status: 200, response: { status: 'success', models: [{ id: 'codex-fixture', isDefault: true, supportedReasoningEfforts: [{ reasoningEffort: 'high' }] }] } };
        if (url.endsWith('/messages')) { session.messages.push({ role: 'user', content: data.question }); session.busy = true; }
        if (url.endsWith('/cancel')) session.busy = false;
        if (url.endsWith('/clear')) session.messages = [];
        return { status: 200, response: { status: 'success', session: { ...session, messages: [...session.messages] } } };
      } }, launchURL: url => calls.push({ launched: url }),
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../plugin/paper_chat.js'), 'utf8'), context);
  const chat = context.KinboPaperChat;
  chat.start({ baseURL: () => 'http://127.0.0.1:8893', syncAPI: async () => 'openai' });
  return { chat, context, reader, doc, calls, listeners, host, iframe, timers, prefs, session, pageDiv, nativeToolbar, observers, win };
}

(async () => {
  const restored = fixture({ existingReader: true });
  assert.equal(restored.nativeToolbar.children.length, 1, 'An already-open PDF must receive its toolbar entry without a render event');
  restored.listeners.renderToolbar({ reader: restored.reader, doc: restored.doc, append: node => restored.nativeToolbar.appendChild(node) });
  assert.equal(restored.nativeToolbar.children.length, 1, 'Render events must not duplicate a restored toolbar button');
  assert.equal(restored.calls.length, 0, 'Restoring toolbar controls must not read a paper or invoke any service');
  const restoredPanel = await restored.chat.openFromWindow({ Zotero_Tabs: { selectedID: 'existing-reader' }, setTimeout: restored.win.setTimeout });
  assert.equal(restoredPanel.session.id, restored.session.id, 'The menu entry must open the active reader sidebar');
  assert.equal(restored.calls.filter(call => call.url?.endsWith('/messages')).length, 0);
  restored.chat.stop();
  assert.equal(restored.nativeToolbar.children.length, 0); assert.equal(restored.observers.size, 0);
  const late = fixture({ existingReader: true, lateToolbar: true });
  assert.equal(late.timers.size, 1);
  late.doc.toolbarReady = true;
  for (const [id, callback] of [...late.timers]) { late.timers.delete(id); callback(); }
  assert.equal(late.nativeToolbar.children.length, 1, 'Delayed reader initialization must still receive its toolbar button');
  late.chat.stop(); assert.equal(late.timers.size, 0);
  const switched = fixture(); switched.context.Zotero.Reader._readers.push(switched.reader);
  switched.observers.get(1).notify('select', 'tab');
  assert.equal(switched.nativeToolbar.children.length, 1, 'Switching reader tabs must restore a missing entry');
  switched.chat.stop();
  const f = fixture(), h = f.chat.helpers;
  assert.deepEqual(JSON.parse(JSON.stringify(h.citation('kinbo://page/12?quote=exact%20sentence'))), { page: 12, quote: 'exact sentence' });
  for (const value of ['javascript:alert(1)', 'kinbo://page/0', 'kinbo://page/1?quote=%broken', 'kinbo://page/1/../../etc', 'kinbo://page/9007199254740992']) assert.equal(h.citation(value), null);
  const chars = [{ u: 'of', rect: [0, 0, 2, 10] }, { u: '\ufb01ce', rect: [2, 0, 5, 10] }, { u: ' ', rect: [5, 0, 6, 10] }, { u: 'x', rect: [6, 0, 7, 10] }];
  assert.equal(h.quoteRects(chars, 'of\ufb01ce').length, 2);
  assert.equal(h.quoteRects(chars, 'office').length, 0, 'Compatibility forms must not silently match a different mathematical or text glyph');
  assert.equal(h.quoteRects([...chars, ...chars], 'of\ufb01ce').length, 0);
  assert.equal(h.quoteRects(chars, 'invented').length, 0);
  assert.equal(h.quoteRects(chars, '  ').length, 0);
  const pages = await h.extractPages(f.reader);
  assert.equal(pages.length, 2); assert.equal(pages[1].text, 'FULL FINAL PAGE');
  const blank = fixture(); blank.reader._internalReader._primaryView._iframeWindow.PDFViewerApplication.pdfDocument.getPageData = async () => ({ chars: [] });
  await assert.rejects(() => blank.chat.helpers.extractPages(blank.reader), /OCR/); blank.chat.stop();
  const rendered = new Node(f.doc, 'div'); h.renderText(f.doc, rendered, '<img src=x onerror=alert(1)>\n[bad](javascript:alert) [page](kinbo://page/2)\n```\n<script>\n```');
  assert(rendered.textContent.includes('<img src=x onerror=alert(1)>'));
  const descendants = node => node.children.flatMap(child => [child, ...descendants(child)]);
  const links = descendants(rendered).filter(node => node.tagName === 'a');
  assert.equal(links[0].getAttribute('href'), null); assert.equal(links[1].getAttribute('href'), 'kinbo://page/2');
  assert.equal(descendants(rendered).filter(node => node.tagName === 'script' || node.tagName === 'img').length, 0);
  assert(!h.safeError(new Error('Request sk-secret-key')).includes('sk-secret'));
  assert.equal(Object.keys(f.listeners).length, 2); assert.equal(f.calls.length, 0, 'Registering reader events must not call a model or service');
  const selected = { text: 'FULL FINAL PAGE', page: 2 };
  const panel = await f.chat.open(f.reader, selected);
  assert.equal(f.calls.filter(call => call.url?.endsWith('/messages')).length, 0, 'Opening and selecting text must not invoke a model');
  const creation = f.calls.find(call => call.url?.endsWith('/sessions'));
  assert.equal(creation.data.pages.length, 2); assert.equal(creation.data.pages[1].text, 'FULL FINAL PAGE');
  assert.equal(panel.selection.text, selected.text); assert.equal(panel.session.id, f.session.id);
  panel.question.value = 'Explain the final page'; await panel.send.trigger('click');
  const sent = f.calls.find(call => call.url?.endsWith('/messages'));
  assert.equal(sent.data.question, 'Explain the final page'); assert.equal(sent.data.selection.page, 2); assert.equal(sent.data.mode, 'api');
  assert.equal(sent.data.webSearch, false); assert.equal(panel.question.value, ''); assert.equal(panel.busy, true);
  panel.question.value = 'duplicate'; await panel.send.trigger('click');
  assert.equal(f.calls.filter(call => call.url?.endsWith('/messages')).length, 1, 'Busy sessions must not send duplicates');
  await panel.cancel.trigger('click'); assert.equal(panel.busy, false);
  panel.mode.value = 'codex'; await panel.mode.trigger('change'); assert.equal(panel.model.value, 'codex-fixture'); assert.equal(panel.effort.children.length, 2);
  panel.network.checked = true; panel.effort.value = 'high'; panel.question.value = 'Search context'; await panel.send.trigger('click');
  assert.equal(f.calls.filter(call => call.url?.endsWith('/messages')).at(-1).data.webSearch, true);
  assert.equal(f.calls.filter(call => call.url?.endsWith('/messages')).at(-1).data.effort, 'high');
  await panel.cancel.trigger('click'); await panel.clear.trigger('click'); assert.equal(panel.session.messages.length, 0);
  await panel.sideButton.trigger('click'); assert.equal(f.host.children[0], panel.aside);
  const cite = new Node(f.doc, 'a', 'Original'); cite.setAttribute('href', 'kinbo://page/2?quote=FULL%20FINAL%20PAGE'); panel.messages.appendChild(cite);
  await panel.aside.trigger('click', { target: cite });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(f.reader.navigated.position.pageIndex, 1); assert(f.pageDiv.children.length > 0);
  f.chat.stop(); assert.equal(f.host.children.length, 1); assert.equal(f.host.children[0], f.iframe); assert.equal(f.pageDiv.children.length, 0); assert.equal(f.timers.size, 0); assert.equal(Object.keys(f.listeners).length, 0);
  console.log('Paper chat mocked-reader checks passed: full text, selection, API/Codex, safe citations, highlights, persistence and cleanup');
})().catch(error => { console.error(error); process.exit(1); });
