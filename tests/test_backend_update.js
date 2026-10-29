/* SPDX-License-Identifier: AGPL-3.0-only */
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('plugin/backend_update.js', 'utf8');
async function scenario(version, scheme = 'http', host = '127.0.0.1') {
  const calls = [], messages = [];
  const scope = { Uint8Array, Services: { io: { newURI: () => ({ scheme, host }) } }, Zotero: {
    getMainWindow: () => ({ btoa: value => Buffer.from(value, 'binary').toString('base64'), setTimeout: () => 1, clearTimeout() {} }),
    File: { async getResourceAsync(url) {
      return url.endsWith('.json') ? JSON.stringify({ backendVersion: '0.4.1', sha256: 'hash', bytes: 3 }) : 'AQID';
    } },
    ProgressWindow: function() { this.changeHeadline = () => {}; this.ItemProgress = function(icon, text) { messages.push(text); }; this.show = () => {}; this.startCloseTimer = () => {}; },
    HTTP: { async request(method, url, options) {
      calls.push({ method, url, options });
      if (url.endsWith('kinbo-backend.json')) return { response: { backendVersion: '0.4.1', sha256: 'hash', bytes: 3 } };
      if (url.endsWith('.zip')) return { response: Uint8Array.from([1, 2, 3]).buffer };
      if (method === 'GET') return { status: 200, response: { version, token: 'secret', update: {} } };
      return { status: 202, response: { status: 'success' } };
    } },
  } };
  vm.createContext(scope); vm.runInContext(source, scope);
  scope.KinboBackendUpdate.start({ baseURL: () => 'http://127.0.0.1:8891', rootURI: 'jar:fixture/' });
  for (let index = 0; index < 15; index++) await Promise.resolve();
  scope.KinboBackendUpdate.stop();
  return { calls, messages, updater: scope.KinboBackendUpdate };
}
(async () => {
  const old = await scenario('0.4.0pre1');
  const submitted = old.calls.find(call => call.method === 'POST');
  assert(submitted);
  assert.equal(submitted.options.headers['X-Kinbo-Update-Token'], 'secret');
  assert.equal(JSON.parse(submitted.options.body).bundle, 'AQID');
  assert(!(await scenario('0.4.1')).calls.some(call => call.method === 'POST'));
  assert(!(await scenario('0.5.0')).calls.some(call => call.method === 'POST'));
  assert.equal((await scenario('0.4.0', 'https', 'remote.test')).calls.length, 0);
  assert(old.updater.newer('0.4.1', '0.4.1pre9'));
  console.log('Kinbo backend updater checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
