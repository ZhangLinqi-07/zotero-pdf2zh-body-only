/* SPDX-License-Identifier: AGPL-3.0-only */
var KinboBackendUpdate = (() => {
  let options, active = false, timer, syncing = false, metadata, attempted = '', lastMessage = '';
  const headers = { 'X-Kinbo-Client': 'zotero' };
  function notify(message) {
    if (message === lastMessage) return;
    lastMessage = message;
    const popup = new Zotero.ProgressWindow({ closeOnClick: true });
    popup.changeHeadline('Kinbo 更新');
    new popup.ItemProgress('chrome://zotero/skin/16/universal/item-type-note.svg', message);
    popup.show(); popup.startCloseTimer(10000);
  }
  function key(value) {
    const match = /^(\d+)\.(\d+)\.(\d+)(?:pre(\d+))?$/.exec(value || '');
    if (!match) throw new Error('Invalid backend version');
    return [+match[1], +match[2], +match[3], match[4] === undefined ? 1 : 0, +(match[4] || 0)];
  }
  function newer(left, right) {
    const a = key(left), b = key(right);
    for (let index = 0; index < a.length; index++) if (a[index] !== b[index]) return a[index] > b[index];
    return false;
  }
  async function tick(manual = false) {
    if (syncing || !active) return;
    syncing = true;
    try {
      const base = options.baseURL(), uri = Services.io.newURI(base);
      if (uri.scheme !== 'http' || !['localhost', '127.0.0.1'].includes(uri.host)) {
        if (manual) notify('自动同步需要本机后台地址，请使用完整安装器升级远程后台');
        return;
      }
      metadata ||= JSON.parse(await Zotero.File.getResourceAsync(options.rootURI + 'content/kinbo-backend.json'));
      const response = await Zotero.HTTP.request('GET', base + '/api/kinbo/update', {
        headers, responseType: 'json', timeout: 5000, successCodes: [200, 404] });
      if (response.status === 404) { notify('插件已更新。旧后台需先用完整安装器升级一次，之后可自动同步'); return; }
      const status = response.response, update = status.update || {};
      if (['failed', 'rolled_back'].includes(update.state) && update.backendVersion === metadata.backendVersion && !manual) {
        notify(update.message || '后台更新未完成，请查看 Kinbo 更新状态后重试'); return;
      }
      if (!newer(metadata.backendVersion, status.version)) {
        if (manual || update.state === 'completed') notify('插件与后台已是配套版本 ' + status.version);
        return;
      }
      if (attempted === metadata.backendVersion && !manual) return;
      if (!active) return;
      const bundle = await Zotero.File.getResourceAsync(options.rootURI + 'content/kinbo-backend.b64');
      if (metadata.bytes > 12 * 1024 * 1024 || bundle.length !== 4 * Math.ceil(metadata.bytes / 3)) throw new Error('Invalid bundled backend');
      const submitted = await Zotero.HTTP.request('POST', base + '/api/kinbo/update', {
        headers: { ...headers, 'Content-Type': 'application/json', 'X-Kinbo-Update-Token': status.token },
        body: JSON.stringify({ ...metadata, bundle }), responseType: 'json', timeout: 30000,
        successCodes: [200, 202, 400, 403, 409, 413, 500] });
      if (submitted.status >= 400) { attempted = metadata.backendVersion; notify(submitted.response?.message || '后台更新校验未通过'); return; }
      attempted = metadata.backendVersion;
      notify('后台更新包已校验，将在当前任务完成后自动同步');
    } catch (_) {
      if (manual) notify('暂时无法连接本机后台，请启动 Kinbo 服务后重试');
    } finally { syncing = false; }
  }
  async function poll() {
    await tick();
    if (active) timer = Zotero.getMainWindow()?.setTimeout(poll, 15000);
  }
  return { tick, newer,
    start(value) { options = value; active = true; poll(); },
    stop() { active = false; if (timer) Zotero.getMainWindow()?.clearTimeout(timer); timer = null; },
  };
})();
