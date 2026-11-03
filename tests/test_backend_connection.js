/* SPDX-License-Identifier: AGPL-3.0-only */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture({ remote = false, cancel = false, windows = false, saved = false, delayed = false, pauseOnly = false } = {}) {
  const files = new Map(), prefs = {}, launches = [], alerts = [], timers = new Map(), opened = [], calls = [];
  let online = false, promptCount = 0, serial = 0, resume;
  const root = '/existing folder/app/server', python = '/existing folder/app/.server-venv/bin/python';
  for (const name of ['server.py', 'run_body_only.py', '.body-only-installed.json']) files.set(root + '/' + name, '{}');
  files.set(root + '/.body-only-launch.json', JSON.stringify({ server_python: '/base/python' })); files.set(python, 'binary');
  if (saved) prefs['extensions.zotero.pdf2zh.bodyOnlyBackendDir_8892'] = root;
  function file(value) {
    return { path: value, get parent() { return file(path.posix.dirname(this.path)); },
      append(part) { this.path = path.posix.join(this.path, part); }, exists() { return files.has(this.path); },
      isFile() { return files.has(this.path); }, createUnique() { this.path += ++serial; files.set(this.path, ''); },
      remove() { files.delete(this.path); } };
  }
  const win = { alert: text => alerts.push(text), setTimeout(fn) {
    const id = ++serial; timers.set(id, fn);
    if (!delayed && !pauseOnly) queueMicrotask(() => { if (timers.delete(id)) fn(); });
    return id;
  }, clearTimeout: id => timers.delete(id) };
  const scope = vm.createContext({ Components: { interfaces: { nsIFile: { NORMAL_FILE_TYPE: 0 }, nsIProcess: {} },
    classes: { '@mozilla.org/process/util;1': { createInstance: () => ({
      init(executable) { this.executable = executable.path; },
      runwAsync(args, count, observer) { launches.push({ executable: this.executable, args: [...args] }); online = !delayed && !pauseOnly; observer.observe(); },
    }) } } },
    ChromeUtils: { importESModule: () => ({ FilePicker: class { init() {} async show() { return 0; } get returnOK() { return 0; } get file() { return root; } } }) },
    Services: { dirsvc: { get: key => file(key === 'Home' ? '/home/test' : key === 'SysD' ? '/system' : '/tmp') },
      io: { newURI: value => { const url = new URL(value); return { host: url.hostname, port: Number(url.port) || -1, scheme: 'http' }; } },
      prompt: { confirmEx: () => { promptCount++; return cancel ? 1 : 0; } } },
    Zotero: { isMac: !windows, isWin: windows, getMainWindow: () => win,
      launchURL: value => opened.push(value), Prefs: { get: key => prefs[key], set: (key, value) => { prefs[key] = value; } },
      File: { pathToFile: file, getContentsAsync: async value => files.get(value),
        getResourceAsync: async () => '# Only the packaged helper', putContentsAsync: async (target, text) => files.set(target.path, text) },
      HTTP: { request: async (method, url) => {
        calls.push({ method, url });
        if (delayed && !resume) await new Promise(resolve => { resume = resolve; });
        if (!online) throw new Error('PRIVATE_SENTINEL');
        return { response: { pdfReading: true } };
      } },
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../plugin/backend_connection.js'), 'utf8'), scope);
  const connection = scope.KinboBackendConnection;
  connection.start({ baseURL: () => remote ? 'https://remote.invalid:8892' : 'http://127.0.0.1:8892', rootURI: 'fixture:///' });
  return { connection, launches, alerts, timers, prefs, files, root, python, opened, calls, win,
    prompts: () => promptCount, resume: () => resume?.(), setOnline: value => { online = value; } };
}
const flush = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  const first = fixture(); await flush();
  assert.equal(first.prompts(), 0, 'Silent startup must not display a folder picker');
  assert.equal(await first.connection.ensure(first.win), true);
  assert.equal(first.prompts(), 1);
  assert.equal(first.launches[0].executable, first.python, 'Use the existing virtual environment');
  assert.deepEqual(first.launches[0].args.slice(1), ['--server-dir', first.root, '--port', '8892']);
  assert.equal([...first.files.keys()].filter(name => name.startsWith('/tmp/')).length, 0, 'Temporary helper must be removed on process exit');
  assert(first.calls.every(call => call.method === 'GET'), 'Connection recovery must not invoke a model or change backend data');
  first.connection.stop(); assert.equal(first.timers.size, 0);

  const automatic = fixture({ saved: true }); await flush();
  assert.equal(automatic.launches.length, 1); assert.equal(automatic.prompts(), 0);
  assert.equal(await automatic.connection.ensure(automatic.win), true); assert.equal(automatic.launches.length, 1);
  automatic.connection.stop();

  const canceled = fixture({ cancel: true }); await flush();
  assert(!await canceled.connection.ensure(canceled.win)); assert.equal(canceled.launches.length, 0); assert.equal(canceled.alerts.length, 0);
  canceled.connection.stop();

  const remote = fixture({ remote: true }); await flush();
  assert(!await remote.connection.ensure(remote.win)); assert.equal(remote.launches.length, 0); assert.equal(remote.prompts(), 0);
  assert.equal(remote.opened.length, 0, 'Offline actions must not open a broken browser page'); remote.connection.stop();

  const windows = fixture({ windows: true }); await flush();
  assert.equal(windows.launches[0].executable, '/system/schtasks.exe');
  assert.deepEqual(windows.launches[0].args, ['/Run', '/TN', 'Kinbo Backend (8892)']); windows.connection.stop();

  const late = fixture({ saved: true, delayed: true });
  late.connection.stop(); late.resume(); await flush();
  assert.equal(late.launches.length, 0, 'A late offline response after disable must not start a service'); assert.equal(late.timers.size, 0);
  assert.equal(late.alerts.length, 0);
  const waiting = fixture({ saved: true, pauseOnly: true }); await flush();
  assert.equal(waiting.timers.size, 1);
  waiting.connection.stop(); await flush();
  assert.equal(waiting.timers.size, 0, 'Disable must clear active backend readiness timers');
  assert.equal(waiting.launches.length, 1); assert.equal(waiting.alerts.length, 0);
  console.log('Automatic backend recovery, folder association, venv, port preservation, cancellation and disable cleanup passed');
})().catch(error => { console.error(error); process.exit(1); });
