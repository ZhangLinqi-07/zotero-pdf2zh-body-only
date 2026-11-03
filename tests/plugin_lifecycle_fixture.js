/* SPDX-License-Identifier: AGPL-3.0-only */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(0, 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
function fixture({ waitForUI = false, waitForUpstream = false, previous = false } = {}) {
  const calls = { load: 0, started: 0, stopped: 0, upstreamStopped: 0, previousStopped: 0, unloaded: 0 };
  let uiReady, upstreamReady;
  const scope = vm.createContext({ Components: {}, ChromeUtils: {}, APP_SHUTDOWN: 2,
    Zotero: { initializationPromise: Promise.resolve(), uiReadyPromise: waitForUI ? new Promise(resolve => { uiReady = resolve; }) : Promise.resolve(),
      logError() {}, getMainWindow: () => ({}), pdf2zh: previous ? { hooks: { onShutdown() { calls.previousStopped++; throw new Error('Old dead wrapper'); } } } : undefined },
    Services: { scriptloader: { loadSubScript(url, context) {
      if (url.endsWith('body-only.js')) context.BodyOnlyBridge = {
        start() { calls.started++; }, stop() { calls.stopped++; throw new Error('Dead wrapper'); },
        removeWindow() { throw new Error('Closed window'); }, addWindow() {},
      };
      else {
        calls.load++;
        scope.Zotero.pdf2zh = { hooks: { onStartup: () => waitForUpstream ? new Promise(resolve => { upstreamReady = resolve; }) : Promise.resolve(),
          onShutdown() { calls.upstreamStopped++; }, onMainWindowLoad() {}, onMainWindowUnload() { calls.unloaded++; } } };
      }
    } } },
  });
  vm.runInContext(source, scope);
  return { scope, calls, uiReady: () => uiReady?.(), upstreamReady: () => upstreamReady?.() };
}
(async () => {
  const normal = fixture({ previous: true });
  await normal.scope.startup({ rootURI: 'fixture:///' }, 1); await flush();
  assert.equal(normal.calls.previousStopped, 1); assert.equal(normal.calls.load, 1); assert.equal(normal.calls.started, 1);
  try { await normal.scope.onMainWindowUnload({ window: {} }, 1); } catch (_) {}
  assert.equal(normal.calls.unloaded, 1, 'Bridge window errors must not skip upstream window cleanup');
  normal.scope.shutdown({}, 1);
  assert.equal(normal.calls.stopped, 1); assert.equal(normal.calls.upstreamStopped, 1, 'Bridge errors must not skip upstream shutdown');

  const deferred = fixture({ waitForUpstream: true });
  await deferred.scope.startup({ rootURI: 'fixture:///' }, 1);
  await flush();
  deferred.scope.shutdown({}, 1); deferred.upstreamReady(); await flush();
  assert.equal(deferred.calls.started, 0, 'Disabled plugin must not inject a late bridge');

  const lateUI = fixture({ waitForUI: true });
  const starting = lateUI.scope.startup({ rootURI: 'fixture:///' }, 1);
  lateUI.scope.shutdown({}, 1); lateUI.uiReady(); await starting; await flush();
  assert.equal(lateUI.calls.load, 0, 'Disabled plugin must not load upstream after UI initialization');
  console.log('Built bootstrap upgrade and asynchronous shutdown regression passed');
})().catch(error => { console.error(error); process.exit(1); });
