/* SPDX-License-Identifier: AGPL-3.0-only
 * Body-only enhancements by ZhangLinqi-07, 2026-10-21. */
var BodyOnlyBridge = (() => {
  const entries = new Map();
  const prefix = 'extensions.zotero.pdf2zh.';
  let active = false, timer = null, syncing = false, noteTools = null;
  const readingWindows = new Map(), preparing = new Set();
  function progressWindow(text) {
    const popup = new Zotero.ProgressWindow({ closeOnClick: true });
    popup.changeHeadline('Kinbo 深度结构化阅读');
    const progress = new popup.ItemProgress('chrome://zotero/skin/16/universal/item-type-note.svg', text);
    progress.setProgress(0); popup.show();
    return { popup, progress };
  }
  function finishWindow(jobID, text, error = false) {
    const view = readingWindows.get(jobID);
    if (!view) return;
    view.progress.setText(text);
    if (error) view.progress.setError(); else view.progress.setProgress(100);
    view.popup.startCloseTimer(error ? 12000 : 8000);
    readingWindows.delete(jobID);
  }
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
    let view, preparingKey, acquired = false;
    try {
      const base = baseURL();
      const capability = await Zotero.HTTP.request('GET', base + '/api/capabilities', { responseType: 'json', timeout: 10000 });
      if (!capability.response?.zoteroNotes || !capability.response?.pdfReading) throw new Error('请先启动 0.3.2 或更新版本的增强服务');
      const { item, parent, path } = await selectedPDF(win);
      preparingKey = parent.libraryID + '/' + item.key;
      if (preparing.has(preparingKey)) return;
      preparing.add(preparingKey);
      acquired = true;
      view = progressWindow('正在准备论文并读取已有翻译 API');
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
      const started = await post(base + '/api/reading/jobs', { documentId: result.document.id, provider: provider || undefined });
      const prior = readingWindows.get(started.job.id);
      if (prior) prior.popup.close();
      readingWindows.set(started.job.id, view);
      view.progress.setText('已开始深度阅读，完成后会自动保存为论文子笔记');
      view.progress.setProgress(started.job.progress || 0);
    } catch (_) {
      // Never display an HTTP exception that may contain the API request body.
      if (view) { view.progress.setError(); view.progress.setText('阅读未能启动，请检查共享 API 和增强服务'); view.popup.startCloseTimer(12000); }
      win.alert('无法开始深度阅读。请确认自己的 API 支持 PDF 文件，PDF 已有父条目且资料库可编辑，增强服务已启动，并且 PDF2zh 的服务器地址指向 0.3.2 或更新版本。');
    }
    finally { if (acquired) preparing.delete(preparingKey); }
  }
  async function stopReading(win) {
    try {
      const base = baseURL(), { item } = await selectedPDF(win), identity = clientID();
      const response = await Zotero.HTTP.request('GET', base + '/api/reading/jobs', { responseType: 'json', timeout: 10000 });
      for (const job of response.response?.jobs || []) {
        if (job.state !== 'running' || job.zoteroTarget?.clientID !== identity || job.zoteroTarget?.attachmentKey !== item.key) continue;
        await post(base + '/api/reading/jobs/' + job.id + '/cancel', { clientID: identity });
        readingWindows.get(job.id)?.progress.setText('已请求停止，当前响应结束后保存已有笔记');
      }
    } catch (_) { win.alert('未能停止续写，请确认增强服务仍在运行，并选中正在阅读的论文。'); }
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
          if (!readingWindows.has(job.id)) readingWindows.set(job.id, progressWindow('阅读笔记已保存'));
          finishWindow(job.id, (job.state === 'partial' ? '未完成的阅读稿已保存，请检查笔记中的提示' : '阅读完成，子笔记已保存') + ' · ' + parent.getField('title'));
        } catch (_) {
          const view = readingWindows.get(job.id);
          if (view) view.progress.setText('阅读完成，笔记暂未保存，正在等待可编辑的原论文条目');
          try { await post(base + '/api/reading/jobs/' + job.id + '/zotero-note', { clientID: identity, state: 'error' }); } catch (_) {}
        }
      }
      for (const [id, view] of readingWindows) {
        try {
          const response = await Zotero.HTTP.request('GET', base + '/api/reading/jobs/' + id, { responseType: 'json', timeout: 10000 });
          const job = response.response.job;
          if (['failed', 'interrupted'].includes(job.state)) finishWindow(id, job.message || '阅读未完成，请检查 API 和本地服务', true);
          else if (job.state === 'cancelled') finishWindow(id, job.message || '阅读已停止');
          else if (job.noteState === 'saved') finishWindow(id, '阅读完成，子笔记已保存');
          else { view.progress.setProgress(job.progress || 0); view.progress.setText(job.message || '正在深度阅读'); }
        } catch (_) { view.progress.setText('等待本地服务恢复连接，已完成的结果会自动保存'); }
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
      const stop = win.document.createXULElement('menuitem'); stop.id = 'pdf2zh-body-only-stop-reading';
      stop.setAttribute('label', '停止本篇后续续写'); stop.addEventListener('command', () => stopReading(win));
      popup.appendChild(stop); nodes.push(stop);
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
    stop() { active = false; if (timer) Zotero.getMainWindow()?.clearTimeout(timer); timer = null; noteTools = null; for (const view of readingWindows.values()) view.popup.close(); readingWindows.clear(); for (const win of [...entries.keys()]) removeWindow(win); },
  };
})();
