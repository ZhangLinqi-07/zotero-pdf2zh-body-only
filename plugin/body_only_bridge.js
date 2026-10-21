/* SPDX-License-Identifier: AGPL-3.0-only
 * Body-only enhancements by ZhangLinqi-07, 2026-10-21. */
var BodyOnlyBridge = (() => {
  const entries = new Map();
  const prefix = 'extensions.zotero.pdf2zh.';
  let active = false, timer = null, syncing = false, noteTools = null;
  const supported = new Set(['openailiked', 'openaicompatible', 'openai', 'gemini', 'deepseek', 'siliconflow', 'modelscope', 'zhipu', 'grok', 'groq']);
  function preference(name) { return Zotero.Prefs.get(prefix + name, true); }
  function clientID() {
    let value = preference('bodyOnlyNoteClient');
    if (!/^[a-f0-9]{32}$/.test(value || '')) {
      value = Services.uuid.generateUUID().toString().replace(/[{}-]/g, '').toLowerCase();
      Zotero.Prefs.set(prefix + 'bodyOnlyNoteClient', value, true);
    }
    return value;
  }
  function baseURL() {
    const result = String(preference('new_serverip') || 'http://127.0.0.1:8891').replace(/\/+$/, '');
    const uri = Services.io.newURI(result);
    if (!['http', 'https'].includes(uri.scheme)) throw new Error('请在 PDF2zh 设置中填写有效的本地服务地址');
    return result;
  }
  async function post(url, data) {
    const response = await Zotero.HTTP.request('POST', url, {
      body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' },
      responseType: 'json', timeout: 120000,
    });
    const result = response.response;
    if (!result || result.status === 'error') throw new Error(result?.message || '增强服务返回了错误');
    return result;
  }
  async function selectedPDF(win) {
    const tabId = win.Zotero_Tabs?.selectedID;
    const reader = tabId && Zotero.Reader?.getByTabID(tabId);
    let item = reader?.itemID ? Zotero.Items.get(reader.itemID) : win.ZoteroPane?.getSelectedItems()?.[0];
    if (!item) throw new Error('请先选择一篇论文或 PDF 附件');
    if (!item.isAttachment()) item = await item.getBestAttachment();
    if (!item || item.attachmentContentType !== 'application/pdf') throw new Error('所选条目没有可读取的 PDF 附件');
    const path = await item.getFilePathAsync();
    if (!path) throw new Error('PDF 尚未下载到本机，请先打开附件');
    const parent = item.parentID && Zotero.Items.get(item.parentID);
    if (!parent?.isRegularItem() || parent.deleted) throw new Error('请先为独立 PDF 创建父条目，再开始深度阅读');
    if (!Zotero.Libraries.get(parent.libraryID)?.editable) throw new Error('论文所在资料库不可编辑，无法保存子笔记');
    return { item, parent, path };
  }
  async function syncAPI(base) {
    let profiles = [];
    try { profiles = JSON.parse(preference('llmApis') || '[]'); } catch (_) { /* The reading page can configure an API. */ }
    const service = preference('next_service');
    profiles = profiles.filter(p => p.activate && p.apiKey && p.model && supported.has(p.service));
    profiles.sort((a, b) => Number(b.service === service) - Number(a.service === service));
    if (!profiles.length) return null;
    const profile = profiles[0];
    const response = await post(base + '/api/reading/sync-translation-api', {
      service: profile.service, model: profile.model, apiKey: profile.apiKey, apiUrl: profile.apiUrl || '',
    });
    return response.profile.id;
  }
  async function openReading(win) {
    try {
      const base = baseURL();
      const capability = await Zotero.HTTP.request('GET', base + '/api/capabilities', { responseType: 'json', timeout: 10000 });
      if (!capability.response?.zoteroNotes) throw new Error('请先启动 0.3.1 或更新版本的增强服务');
      const { item, parent, path } = await selectedPDF(win);
      const provider = await syncAPI(base);
      const io = typeof IOUtils !== 'undefined' ? IOUtils : win.IOUtils;
      let binary;
      if (io?.read) {
        if (io.stat && (await io.stat(path)).size > 50 * 1024 * 1024) throw new Error('深度阅读暂时接受不超过 50 MB 的 PDF');
        const bytes = await io.read(path);
        if (bytes.length > 50 * 1024 * 1024) throw new Error('深度阅读暂时接受不超过 50 MB 的 PDF');
        const chunks = [];
        for (let index = 0; index < bytes.length; index += 32768) chunks.push(String.fromCharCode(...bytes.subarray(index, index + 32768)));
        binary = chunks.join('');
      } else {
        binary = await Zotero.File.getBinaryContentsAsync(path);
        if (binary.length > 50 * 1024 * 1024) throw new Error('深度阅读暂时接受不超过 50 MB 的 PDF');
      }
      const filename = path.replace(/\\/g, '/').split('/').pop();
      const result = await post(base + '/api/reading/documents', { fileName: filename, fileContent: win.btoa(binary),
        zoteroTarget: { clientID: clientID(), libraryID: parent.libraryID, parentKey: parent.key, attachmentKey: item.key, title: parent.getField('title') } });
      Zotero.launchURL(base + '/?reading=' + encodeURIComponent(result.document.id) + (provider ? '&api=' + encodeURIComponent(provider) : '') + '#reading');
    } catch (_) {
      // Never display an HTTP exception that may contain the API request body.
      win.alert('无法打开深度阅读。请确认 PDF 已有父条目且资料库可编辑，增强服务已启动，并且 PDF2zh 的服务器地址指向 0.3.1 或更新版本。也可以在服务控制页直接选择 PDF，但单独上传的文件无法自动关联 Zotero。');
    }
  }
  function tools() {
    if (!noteTools) {
      const context = { window: Zotero.getMainWindow() };
      context.globalThis = context; context.self = context;
      Services.scriptloader.loadSubScript(BodyOnlyRootURI + 'content/scripts/body-only-marked.js', context);
      Services.scriptloader.loadSubScript(BodyOnlyRootURI + 'content/scripts/body-only-purify.js', context);
      Services.scriptloader.loadSubScript(BodyOnlyRootURI + 'content/scripts/body-only-note.js', context);
      noteTools = context;
    }
    return noteTools;
  }
  async function syncNotes() {
    if (syncing || !active) return;
    syncing = true;
    try {
      const base = baseURL(), identity = clientID();
      const response = await Zotero.HTTP.request('GET', base + '/api/reading/zotero/pending?clientID=' + identity, { responseType: 'json', timeout: 10000 });
      for (const job of response.response?.jobs || []) {
        if (!active) break;
        try {
          const target = job.zoteroTarget;
          if (target?.clientID !== identity || !/^[a-f0-9]{32}$/.test(job.id)) continue;
          const parent = await Zotero.Items.getByLibraryAndKeyAsync(target.libraryID, target.parentKey);
          if (!parent?.isRegularItem() || parent.deleted || !Zotero.Libraries.get(parent.libraryID)?.editable) throw new Error('Unavailable parent');
          await parent.loadDataType('childItems');
          const children = await Zotero.Items.getAsync(parent.getNotes());
          for (const child of children) await child.loadDataType('note');
          const marker = 'readingJob=' + job.id;
          let note = children.find(child => !child.deleted && child.getNote().includes(marker));
          if (!note) {
            const renderer = tools();
            note = new Zotero.Item('note'); note.libraryID = parent.libraryID; note.parentID = parent.id;
            note.setNote(renderer.BodyOnlyNotes.render(job, base, renderer.marked, renderer.DOMPurify));
            note.addTag('深度结构化阅读', 1);
            await note.saveTx();
          }
          await post(base + '/api/reading/jobs/' + job.id + '/zotero-note', { clientID: identity, state: 'saved', noteKey: note.key });
        } catch (_) {
          try { await post(base + '/api/reading/jobs/' + job.id + '/zotero-note', { clientID: identity, state: 'error' }); } catch (_) {}
        }
      }
    } catch (_) { /* Offline Zotero/server sessions retry without disturbing reading. */ }
    finally { syncing = false; }
  }
  async function pollNotes() {
    await syncNotes();
    if (active) timer = Zotero.getMainWindow()?.setTimeout(pollNotes, 5000);
  }
  function addWindow(win) {
    if (entries.has(win)) return;
    const nodes = [];
    const menu = win.document.getElementById('zotero-itemmenu-pdf2zh');
    const popup = menu?.querySelector('menupopup');
    if (popup) {
      const labels = [menu, ...popup.querySelectorAll('menuitem')].map(node => [node, node.getAttribute('label')]);
      menu.setAttribute('label', 'Kinbo');
      for (const [node, label] of labels.slice(1)) node.setAttribute('label', (label || '').replace(/^PDF2zh[:：]\s*/, ''));
      win.document.getElementById('pdf2zh-body-only-compare')?.remove();
      const previous = win.document.getElementById('pdf2zh-body-only-reading');
      if (previous && previous.parentNode !== popup) previous.remove();
      const separator = win.document.createXULElement('menuseparator');
      popup.appendChild(separator); nodes.push(separator);
      const node = win.document.createXULElement('menuitem');
      node.id = 'pdf2zh-body-only-reading'; node.setAttribute('label', '深度结构化阅读');
      node.addEventListener('command', () => openReading(win)); popup.appendChild(node); nodes.push(node);
      entries.set(win, { nodes, labels });
    }
  }
  function removeWindow(win) {
    const entry = entries.get(win);
    for (const node of entry?.nodes || []) node.remove();
    for (const [node, label] of entry?.labels || []) node.setAttribute('label', label || '');
    entries.delete(win);
  }
  return { addWindow, removeWindow, openReading, syncNotes,
    start() {
      if (typeof BodyOnlyLocalServer === 'string' && !preference('bodyOnlyServerMigrated_0_3_0')) {
        Zotero.Prefs.set(prefix + 'new_serverip', BodyOnlyLocalServer, true);
        Zotero.Prefs.set(prefix + 'bodyOnlyServerMigrated_0_3_0', true, true);
      }
      for (const win of Zotero.getMainWindows()) addWindow(win);
      if (!active) { active = true; pollNotes(); }
    },
    stop() { active = false; if (timer) Zotero.getMainWindow()?.clearTimeout(timer); timer = null; noteTools = null; for (const win of [...entries.keys()]) removeWindow(win); },
  };
})();
