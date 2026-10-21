/* SPDX-License-Identifier: AGPL-3.0-only */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

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
  console.log('Native reading error handling and credential privacy passed');
})().catch(error => { console.error(error); process.exit(1); });
