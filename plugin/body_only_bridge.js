/* SPDX-License-Identifier: AGPL-3.0-only
 * Body-only enhancements by ZhangLinqi-07, 2026-10-21. */
var BodyOnlyBridge = (() => {
  const entries = new Map();
  const prefix = 'extensions.zotero.pdf2zh.';
  const supported = new Set(['openailiked', 'openaicompatible', 'openai', 'gemini', 'deepseek', 'siliconflow', 'modelscope', 'zhipu', 'grok', 'groq']);
  function preference(name) { return Zotero.Prefs.get(prefix + name, true); }
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
    return { item, path };
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
      if (!capability.response?.deepReading) throw new Error('请先启动 0.3.0 或更新版本的增强服务');
      const { item, path } = await selectedPDF(win);
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
      const result = await post(base + '/api/reading/documents', { fileName: filename, fileContent: win.btoa(binary) });
      Zotero.launchURL(base + '/?reading=' + encodeURIComponent(result.document.id) + (provider ? '&api=' + encodeURIComponent(provider) : '') + '#reading');
    } catch (_) {
      // Never display an HTTP exception that may contain the API request body.
      win.alert('无法打开深度阅读。请确认本机 PDF 可用，增强服务已启动，并且 PDF2zh 的服务器地址指向 0.3.0 或更新版本。也可以在服务控制页直接选择 PDF。');
    }
  }
  function addWindow(win) {
    if (entries.has(win)) return;
    const nodes = [];
    const menu = win.document.getElementById('zotero-itemmenu');
    if (menu) {
      const node = win.document.createXULElement('menuitem');
      node.id = 'pdf2zh-body-only-reading'; node.setAttribute('label', '深度结构化阅读');
      node.addEventListener('command', () => openReading(win)); menu.appendChild(node); nodes.push(node);
      const compare = win.document.createXULElement('menuitem');
      compare.id = 'pdf2zh-body-only-compare'; compare.setAttribute('label', '整页双语对照，保留原有双栏');
      compare.addEventListener('command', () => Zotero.pdf2zh?.hooks.onDialogEvents('comparePDF'));
      menu.appendChild(compare); nodes.push(compare);
    }
    entries.set(win, nodes);
  }
  function removeWindow(win) { for (const node of entries.get(win) || []) node.remove(); entries.delete(win); }
  return { addWindow, removeWindow, openReading,
    start() {
      if (typeof BodyOnlyLocalServer === 'string' && !preference('bodyOnlyServerMigrated_0_3_0')) {
        Zotero.Prefs.set(prefix + 'new_serverip', BodyOnlyLocalServer, true);
        Zotero.Prefs.set(prefix + 'bodyOnlyServerMigrated_0_3_0', true, true);
      }
      for (const win of Zotero.getMainWindows()) addWindow(win);
    },
    stop() { for (const win of [...entries.keys()]) removeWindow(win); },
  };
})();
