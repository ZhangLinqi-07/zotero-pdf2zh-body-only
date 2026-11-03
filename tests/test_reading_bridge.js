/* SPDX-License-Identifier: AGPL-3.0-only */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class MenuNode {
  constructor(tag) {
    this.localName = tag; this.children = []; this.attributes = {}; this.listeners = new Map();
    this.classList = { add() {} }; this.style = { setProperty() {} };
  }
  get id() { return this.attributes.id; } set id(value) { this.attributes.id = value; }
  get lastElementChild() { return this.children.at(-1); }
  setAttribute(key, value) { this.attributes[key] = value; }
  getAttribute(key) { return this.attributes[key] ?? null; }
  removeAttribute(key) { delete this.attributes[key]; }
  appendChild(node) { node.parentNode = this; this.children.push(node); return node; }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(node => node !== this); this.parentNode = null; }
  querySelectorAll(selector) {
    const id = selector.match(/^\[id="(.+)"\]$/)?.[1];
    return this.children.flatMap(node => [...(id ? node.id === id : node.localName === selector) ? [node] : [], ...node.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0]; }
  addEventListener(name, fn) { this.listeners.set(name, fn); }
  removeEventListener(name) { this.listeners.delete(name); }
}

async function upgradeMenus() {
  const document = new MenuNode('document'), errors = [], timers = new Map();
  document.createXULElement = tag => new MenuNode(tag);
  document.getElementById = id => document.querySelector('[id="' + id + '"]');
  const root = () => {
    const menu = document.appendChild(new MenuNode('menu')); menu.id = 'zotero-itemmenu-pdf2zh'; menu.setAttribute('label', 'PDF2zh');
    const popup = menu.appendChild(new MenuNode('menupopup'));
    for (const id of ['translate-pdf', 'crop-pdf', 'compare-pdf', 'crop-compare-pdf']) {
      const item = popup.appendChild(new MenuNode('menuitem')); item.id = 'zotero-itemmenu-' + id; item.setAttribute('label', 'PDF2zh: ' + id);
    }
    return menu;
  };
  const legacy = root(); legacy.setAttribute('label', 'Kinbo');
  const obsolete = ['pdf2zh-body-only-reading', 'pdf2zh-body-only-stop-reading', 'pdf2zh-body-only-chat', 'pdf2zh-body-only-model', 'kinbo-backend-update'];
  for (const id of obsolete) { const node = legacy.children[0].appendChild(new MenuNode('menuitem')); node.id = id; }
  const current = root(), popup = current.children[0];
  popup.appendChild(new MenuNode('menuseparator'));
  for (const id of obsolete) { const node = popup.appendChild(new MenuNode('menuitem')); node.id = id; }
  const tools = document.appendChild(new MenuNode('menupopup')); tools.id = 'menu_ToolsPopup';
  const staleTools = tools.appendChild(new MenuNode('menuitem')); staleTools.id = 'kinbo-paper-chat-tools';
  const win = { document, setTimeout: fn => { timers.set(1, fn); return 1; }, clearTimeout: id => timers.delete(id) };
  const scope = vm.createContext({ BodyOnlyRootURI: 'fixture:///', Components: {}, ChromeUtils: {},
    Services: { scriptloader: { loadSubScript(url, target) {
      if (url.endsWith('kinbo-connection.js')) target.KinboBackendConnection = { start() {}, stop() {}, ensure: async () => true };
      if (url.endsWith('kinbo-paper-chat.js')) target.KinboPaperChat = { start() {}, stop() { throw new Error('Dead Reader wrapper'); } };
      if (url.endsWith('kinbo-updater.js')) target.KinboBackendUpdate = { start() {}, stop() { throw new Error('Already closed'); } };
    } }, io: { newURI: () => ({ scheme: 'http' }) }, uuid: { generateUUID: () => 'a'.repeat(32) } },
    Zotero: { getMainWindow: () => win, getMainWindows: () => [win], Prefs: { get() {}, set() {} },
      logError: error => errors.push(error), HTTP: { request: async () => ({ response: { jobs: [] } }) } } });
  vm.runInContext(fs.readFileSync(process.env.KINBO_BRIDGE_SOURCE || path.join(__dirname, '../plugin/body_only_bridge.js'), 'utf8'), scope);
  scope.BodyOnlyBridge.start(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(document.querySelectorAll('[id="zotero-itemmenu-pdf2zh"]').length, 1, 'Hot upgrade must remove the stale upstream root');
  assert.equal(document.getElementById('zotero-itemmenu-pdf2zh'), current, 'Keep the current upstream translation handlers');
  assert.equal(popup.querySelectorAll('menuitem').length, 5, 'Only four translation commands and one reading command may remain');
  assert.equal(popup.querySelectorAll('menuseparator').length, 1);
  assert.equal(document.querySelectorAll('[id="pdf2zh-body-only-reading"]').length, 1);
  assert.equal(document.getElementById('pdf2zh-body-only-model').parentNode, tools);
  assert(!document.getElementById('pdf2zh-body-only-chat')); assert(!document.getElementById('pdf2zh-body-only-stop-reading'));
  scope.BodyOnlyBridge.addWindow(win);
  assert.equal(tools.children.length, 3, 'Window activation must not duplicate Tools commands');
  scope.BodyOnlyBridge.stop();
  assert.equal(tools.children.length, 0, 'A Reader cleanup exception must not leave Tools entries');
  assert.equal(popup.querySelectorAll('menuitem').length, 4); assert.equal(popup.listeners.size, 0);
  assert.equal(current.getAttribute('label'), 'PDF2zh'); assert.equal(timers.size, 0);
  assert.equal(errors.length, 2, 'Cleanup failures must be recorded without interrupting later cleanup');
}

async function run(mode) {
  const alerts = [], calls = [];
  const parent = { isRegularItem: () => true, libraryID: 1, key: 'ABCD1234', getField: () => 'Synthetic paper' };
  const item = { isAttachment: () => true, attachmentContentType: 'application/pdf', parentID: mode === 'noParent' ? null : 1,
    key: 'PDFK1234', getFilePathAsync: async () => 'C:/fixture.pdf' };
  const win = { ZoteroPane: { getSelectedItems: () => [item] }, alert: text => alerts.push(text),
    btoa: text => Buffer.from(text, 'binary').toString('base64') };
  class Popup {
    constructor() { this.ItemProgress = class { setProgress() {} setText() {} setError() {} }; }
    changeHeadline() {} show() {} startCloseTimer() {}
  }
  const scope = vm.createContext({
    Services: { io: { newURI: value => ({ scheme: new URL(value).protocol.slice(0, -1) }) },
      uuid: { generateUUID: () => 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa' } },
    IOUtils: { read: async () => new Uint8Array(Buffer.from('%PDF-fixture')), stat: async () => ({ size: 12 }) },
    Zotero: { Prefs: { get: name => name.endsWith('new_serverip') ? 'http://127.0.0.1:8893' : null, set() {} },
      Reader: {}, Items: { get: () => parent }, Libraries: { get: () => ({ editable: true }) }, ProgressWindow: Popup,
      HTTP: { request: async (method, url, options) => {
        calls.push({ method, url, options });
        if (mode === 'rawHttpError') throw new Error('Request body contained sk-private-fixture-secret');
        if (url.endsWith('/api/capabilities')) return { response: { zoteroNotes: true, pdfReading: true, readingSearch: true, fullPageImageReading: mode !== 'oldServer' } };
        if (url.endsWith('/api/reading/config')) return { response: { options: { backend: 'api' } } };
        if (url.endsWith('/documents')) return { response: { status: 'success', document: { id: 'b'.repeat(32) } } };
        return { status: 400, response: { status: 'error', code: 'READING_VALIDATION',
          message: 'DeepSeek 官方 API 不接收 PDF，请选择全部页面图像 sk-private-fixture-secret' } };
      } },
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../plugin/body_only_bridge.js'), 'utf8'), scope);
  await scope.BodyOnlyBridge.openReading(win);
  assert.equal(alerts.length, 1);
  assert(!alerts[0].includes('sk-private-fixture-secret'));
  if (mode === 'oldServer') assert(alerts[0].includes('0.3.6'));
  if (mode === 'noParent') assert(alerts[0].includes('父条目'));
  if (mode === 'validation') {
    assert(alerts[0].includes('全部页面图像'));
    assert(calls.at(-1).options.successCodes.includes(400));
  }
  if (mode === 'rawHttpError') assert(alerts[0].includes('无法连接'));
}

(async () => {
  for (const mode of ['oldServer', 'noParent', 'validation', 'rawHttpError']) await run(mode);
  await upgradeMenus();
  console.log('Reading errors, credential privacy, legacy upgrade menus and failed Reader cleanup passed');
})().catch(error => { console.error(error); process.exit(1); });
