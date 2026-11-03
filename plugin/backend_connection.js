/* SPDX-License-Identifier: AGPL-3.0-only */
var KinboBackendConnection = (() => {
  const prefix = 'extensions.zotero.pdf2zh.';
  let options = null, active = false, pending = null, revision = 0;
  const waits = new Set();
  function file(path) { return Zotero.File.pathToFile(path); }
  function existing(path) { return path && file(path).exists() && file(path).isFile(); }
  function child(root, ...parts) { const result = file(root); for (const part of parts) result.append(part); return result.path; }
  function directory(name) { return Services.dirsvc.get(name, Components.interfaces.nsIFile).path; }
  function endpoint() {
    const uri = Services.io.newURI(options.baseURL());
    return { local: uri.scheme === 'http' && ['127.0.0.1', 'localhost'].includes(uri.host),
      port: uri.port === -1 ? (uri.scheme === 'https' ? 443 : 80) : uri.port };
  }
  async function connected() {
    try {
      const result = await Zotero.HTTP.request('GET', options.baseURL() + '/api/capabilities', { responseType: 'json', timeout: 1500 });
      return Boolean(result.response?.pdfReading);
    } catch (_) { return false; }
  }
  function pause(win) {
    return new Promise(resolve => {
      const wait = { win, resolve };
      wait.timer = win.setTimeout(() => { waits.delete(wait); resolve(); }, 500); waits.add(wait);
    });
  }
  function run(executable, args, finished = () => {}) {
    const process = Components.classes['@mozilla.org/process/util;1'].createInstance(Components.interfaces.nsIProcess);
    process.init(file(executable));
    process.runwAsync(args, args.length, { observe: finished }, false);
  }
  async function knownRoot(port, win) {
    const saved = Zotero.Prefs.get(prefix + 'bodyOnlyBackendDir_' + port, true);
    if (saved) return saved;
    const plist = child(directory('Home'), 'Library', 'LaunchAgents', 'org.kinbo.backend.' + port + '.plist');
    if (file(plist).exists()) {
      const document = new win.DOMParser().parseFromString(await Zotero.File.getContentsAsync(plist), 'text/xml');
      const key = [...document.querySelectorAll('plist > dict > key')].find(node => node.textContent === 'ProgramArguments');
      const args = [...key?.nextElementSibling?.children || []].map(node => node.textContent);
      const index = args.indexOf('--server-dir');
      if (index !== -1 && args[index + 1]) return args[index + 1];
    }
    const standard = child(directory('Home'), 'Library', 'Application Support', 'Kinbo', 'app', 'server');
    return file(child(standard, '.body-only-launch.json')).exists() ? standard : null;
  }
  async function wakeMac(root, port) {
    if (!file(child(root, 'server.py')).exists() && file(child(root, 'server', 'server.py')).exists()) root = child(root, 'server');
    for (const name of ['server.py', 'run_body_only.py', '.body-only-launch.json', '.body-only-installed.json']) {
      if (!existing(child(root, name))) throw new Error('Missing managed backend');
    }
    const settings = JSON.parse(await Zotero.File.getContentsAsync(child(root, '.body-only-launch.json')));
    const parent = file(root).parent.path;
    const python = [child(parent, '.server-venv', 'bin', 'python'), child(root, '.server-venv', 'bin', 'python'),
      child(root, '.venv', 'bin', 'python'), settings.server_python].find(existing);
    if (!python) throw new Error('Missing managed Python');
    const source = await Zotero.File.getResourceAsync(options.rootURI + 'content/scripts/kinbo-macos-start.py');
    if (!active) return false;
    const temporary = file(directory('TmpD')); temporary.append('kinbo-macos-start.py');
    temporary.createUnique(Components.interfaces.nsIFile.NORMAL_FILE_TYPE, 0o600);
    try {
      await Zotero.File.putContentsAsync(temporary, source);
      if (!active) { temporary.remove(false); return false; }
      run(python, [temporary.path, '--server-dir', root, '--port', String(port)], () => {
        try { temporary.remove(false); } catch (_) { /* Already removed by the OS. */ }
      });
    } catch (error) { try { temporary.remove(false); } catch (_) {} throw error; }
    Zotero.Prefs.set(prefix + 'bodyOnlyBackendDir_' + port, root, true);
    return true;
  }
  async function wake(win, interactive, token) {
    if (await connected()) return active && token === revision;
    if (!active || token !== revision) return false;
    const { local, port } = endpoint();
    if (!local) return false;
    let launched = false;
    if (Zotero.isMac) {
      let root = await knownRoot(port, win);
      if (!active || token !== revision) return false;
      if (!root && interactive) {
        const choice = Services.prompt.confirmEx(win, '连接 Kinbo 后台',
          'Kinbo 尚未连接到本机后台。关联原后台文件夹后会自动启动，并保留当前端口与 API 配置。首次使用可下载完整安装包。',
          Services.prompt.BUTTON_POS_0 * Services.prompt.BUTTON_TITLE_IS_STRING |
          Services.prompt.BUTTON_POS_1 * Services.prompt.BUTTON_TITLE_CANCEL |
          Services.prompt.BUTTON_POS_2 * Services.prompt.BUTTON_TITLE_IS_STRING,
          '选择后台文件夹', null, '下载完整安装包', null, { value: false });
        if (!active || token !== revision) return false;
        if (choice === 2) Zotero.launchURL('https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/releases/latest');
        if (choice !== 0) return null;
        const { FilePicker } = ChromeUtils.importESModule('chrome://zotero/content/modules/filePicker.mjs');
        const picker = new FilePicker(); picker.init(win, '选择包含 server.py 的 Kinbo 后台文件夹', picker.modeGetFolder);
        if (await picker.show() !== picker.returnOK) return null;
        root = picker.file;
      }
      if (!active || token !== revision) return false;
      if (root) launched = await wakeMac(root, port);
    } else if (Zotero.isWin) {
      run(child(directory('SysD'), 'schtasks.exe'), ['/Run', '/TN', 'Kinbo Backend (' + port + ')']); launched = true;
    }
    for (let attempt = 0; launched && active && token === revision && attempt < 20; attempt++) {
      await pause(win);
      if (active && token === revision && await connected()) return active && token === revision;
    }
    return false;
  }
  async function ensure(win, interactive = true) {
    if (!active) return false;
    win ||= Zotero.getMainWindow();
    // A click during the silent startup check may still need the folder picker.
    if (pending) { const ready = await pending; if (ready || !interactive || !active) return ready; }
    const token = revision;
    pending = wake(win, interactive, token).catch(() => false);
    const result = await pending; pending = null;
    if (result === false && interactive && active && token === revision) win.alert(!endpoint().local
      ? 'Kinbo 未能连接到设置中的后台。请确认该服务器可访问；远程或 HTTPS 后台由服务器管理员启动。服务器地址保留不变。'
      : Zotero.isMac
      ? 'Kinbo 后台尚未就绪。请确认所选目录包含原后台及 Python 环境，并在系统登录项中允许 Kinbo 后台运行。服务器地址保留不变。'
      : 'Kinbo 后台尚未就绪。请使用完整安装包配置后台自动启动，并确认后台端口与 Zotero 设置一致。服务器地址保留不变。');
    return result && active && token === revision;
  }
  return { ensure,
    start(config) { options = config; active = true; revision++; ensure(Zotero.getMainWindow(), false); },
    stop() {
      active = false; revision++;
      for (const wait of waits) { try { wait.win.clearTimeout(wait.timer); } catch (_) {} wait.resolve(); }
      waits.clear();
    },
  };
})();
