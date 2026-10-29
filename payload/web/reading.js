/* SPDX-License-Identifier: AGPL-3.0-only */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let currentDocument = null, currentJob = null, configured = false, searchReady = false, polling = null, busy = false, loginPolling = null, readingProfiles = [];
  async function api(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok || data.status === 'error') throw new Error(data.message || '操作失败');
    return data;
  }
  const post = data => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  function status(text, kind = '') { $('readingStatus').textContent = text; $('readingStatus').className = 'reading-status ' + kind; }
  function startState() {
    $('startReading').disabled = !currentDocument || !configured || !searchReady || busy;
    $('cancelReading').hidden = !busy;
    $('cancelReading').disabled = !!currentJob?.cancelRequested;
  }
  function option(select, label, value) { const item = document.createElement('option'); item.textContent = label; item.value = value; select.append(item); }
  async function loadLayout() {
    try {
      const result = await api('/api/layout-settings');
      $('preserveColumns').checked = result.settings.preserveColumns;
      $('mathMode').value = result.settings.mathMode;
      const report = result.lastReport;
      $('layoutStatus').textContent = report
        ? `最近一次保护了 ${report.protectedFormulaParagraphs} 个公式段落，${report.compactInlineParagraphs || 0} 个短文本已在原位重排，${report.continuedParagraphs ?? (report.continuations || []).length} 个段落使用完整译文续页。`
        : '整页对照保留原有栏布局。公式保护优先保留公式位置，无法排入的译文使用完整译文续页。';
    } catch (error) { $('layoutStatus').textContent = error.message; }
  }
  async function saveLayout() {
    try {
      await api('/api/layout-settings', post({ preserveColumns: $('preserveColumns').checked, mathMode: $('mathMode').value }));
      $('layoutStatus').textContent = '已保存，之后发起的翻译会使用这些排版选项。含公式的正文仍需翻译，排版溢出使用完整译文续页。';
    } catch (error) { $('layoutStatus').textContent = error.message; }
  }
  async function loadConfig(useSavedBackend = false) {
    const [data, capabilities] = await Promise.all([api('/api/reading/config'), api('/api/capabilities')]);
    searchReady = capabilities.readingSearch === true && capabilities.fullPageImageReading === true;
    const select = $('readingProvider'), previous = select.value;
    select.replaceChildren();
    readingProfiles = data.profiles;
    for (const profile of readingProfiles) option(select, `${profile.label} · ${profile.model || '默认模型'}${profile.configured === false ? ' · 尚未登录' : ''}`, profile.id);
    if (!readingProfiles.length) option(select, '尚未配置可用于深度阅读的模型', '');
    const requested = new URL(location.href).searchParams.get('api');
    const desired = useSavedBackend ? data.selected : requested || previous || data.selected;
    const selected = readingProfiles.find(p => p.id === desired) || readingProfiles.find(p => p.id === data.selected) || readingProfiles[0];
    select.value = selected?.id || '';
    configured = !!selected && selected.configured !== false;
    const search = $('readingSearchProvider');
    search.replaceChildren();
    option(search, '自动复用阅读 API', 'auto');
    for (const profile of data.profiles.filter(p => p.id !== 'codex')) option(search, `${profile.label} · ${profile.model}`, profile.id);
    search.value = data.options.searchProvider || 'auto';
    $('sharedApiStatus').textContent = !searchReady ? '当前后台尚未加载全部页面图像阅读，请重启到 0.3.6 或更新版本。无需重新填写 API。' : configured
      ? '深度阅读可使用已有翻译 API 或已登录的 Codex，按所选模型后端运行。'
      : '深度阅读需要配置自己的 API 或登录 Codex。';
    $('readingBackend').value = data.options.backend || 'api';
    for (const name of ['pdfProtocol', 'documentMode', 'requestTimeout', 'inputPrice', 'outputPrice', 'unitCny']) {
      $(name).value = data.options[name] ?? '';
    }
    const compatible = data.profiles.find(p => p.id === 'openaicompatible');
    if (compatible) { $('sharedEndpoint').value = compatible.endpoint; $('sharedModel').value = compatible.model; }
    $('apiConfiguration').open = !configured;
    startState(); describeDocument();
  }
  async function loadCodex() {
    const [data, backend, reading] = await Promise.all([api('/api/paper-chat/config'), api('/api/model-backend'), api('/api/reading/config')]);
    const account = data.codex || {};
    $('codexAccountStatus').textContent = account.message || '尚未登录 Codex';
    $('loginCodex').disabled = account.authenticated === true;
    $('translationBackend').value = backend.settings.translationBackend;
    $('readingBackend').value = reading.options.backend || 'api';
    const select = $('codexModel');
    select.replaceChildren(); option(select, '使用 Codex 默认模型', '');
    if (account.available && account.authenticated) {
      const result = await api('/api/paper-chat/models?mode=codex');
      for (const model of result.models || []) option(select, model.displayName || model.model || model.id, model.model || model.id);
    }
    const saved = reading.options.codexModel || backend.settings.model || '';
    if (saved && ![...select.options].some(item => item.value === saved)) option(select, saved, saved);
    select.value = saved;
  }
  async function loginCodex() {
    try {
      const result = await api('/api/paper-chat/login', post({}));
      const login = result.login || result;
      const info = $('codexLoginInfo'); info.replaceChildren(); info.hidden = false;
      info.append(document.createTextNode(login.message || '请完成 Codex 登录'));
      const address = login.verificationUri || login.verificationUrl;
      if (address) {
        const url = new URL(address);
        if (url.protocol === 'https:' && ['auth.openai.com', 'auth0.openai.com'].includes(url.hostname)) {
          const link = document.createElement('a'); link.href = address; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = ' 打开官方登录页面'; info.append(link);
        }
      }
      if (login.userCode) info.append(document.createTextNode(' 登录代码 ' + login.userCode));
      clearTimeout(loginPolling);
      const check = async () => {
        try {
          const response = await api('/api/paper-chat/login'), state = response.login || response;
          if (state.authenticated) { info.textContent = 'Codex 登录完成'; await Promise.all([loadCodex(), loadConfig()]); }
          else if (state.completed) { info.textContent = state.message || '登录未完成，请重试'; }
          else loginPolling = setTimeout(check, 3000);
        } catch (error) { info.textContent = error.message; }
      };
      if (!login.authenticated) loginPolling = setTimeout(check, 3000); else await loadCodex();
    } catch (error) { status(error.message, 'error'); }
  }
  async function saveModelBackend() {
    try {
      const model = $('codexModel').value;
      await api('/api/model-backend', post({ translationBackend: $('translationBackend').value, model }));
      await api('/api/reading/config', post({ backend: $('readingBackend').value, codexModel: model }));
      await loadConfig(true); status('模型后端已保存，对之后发起的翻译和深度阅读生效。', 'success');
    } catch (error) { status(error.message, 'error'); }
  }
  async function saveConfig() {
    const data = { pdfProtocol: $('pdfProtocol').value, documentMode: $('documentMode').value, requestTimeout: Number($('requestTimeout').value), searchProvider: $('readingSearchProvider').value };
    for (const name of ['inputPrice', 'outputPrice', 'unitCny']) data[name] = $(name).value.trim() === '' ? null : Number($(name).value);
    const endpoint = $('sharedEndpoint').value.trim(), model = $('sharedModel').value.trim(), key = $('sharedKey').value.trim();
    if (endpoint || model || key) Object.assign(data, { endpoint, model, apiKey: key });
    try {
      await api('/api/reading/config', post(data));
      $('sharedKey').value = '';
      await loadConfig(); status('共享 API 与阅读选项已保存。配置保存在本机服务，密钥不写入浏览器存储。', 'success');
    } catch (error) { status(error.message, 'error'); }
  }
  function describeDocument() {
    if (!currentDocument) { $('readingDocumentInfo').textContent = '选择 PDF 后，原始文件将完整提交给支持 PDF 的 API。'; return; }
    const mode = $('documentMode').value;
    if ($('readingProvider').value === 'codex') {
      $('readingDocumentInfo').textContent = `${currentDocument.filename}，共 ${currentDocument.pages} 页。全部页面渲染为 144 dpi 图像，与完整提示词交给 Codex，保留联网核验和自动子笔记。`;
      return;
    }
    const input = mode === 'images' ? '全部页面转为整页图像后与完整提示词一次提交。' : mode === 'pdf' ? '完整 PDF 与阅读提示词一起提交。' : '自动模式下 DeepSeek Flash 使用全部页面图像，其余 API 使用完整 PDF。';
    $('readingDocumentInfo').textContent = `${currentDocument.filename}，共 ${currentDocument.pages} 页。${input}不选页或分段摘要。输出长度与思考强度采用接口默认设置，达到输出上限后自动续写。`;
  }
  function selectDocument(documentInfo) {
    currentDocument = documentInfo; describeDocument(); startState();
    $('readingNoteStatus').textContent = documentInfo.zoteroTarget ? `阅读完成后自动保存到 Zotero 论文条目下，归属 ${documentInfo.zoteroTarget.title || '所选论文'}。` : '从 Zotero 右键打开论文后，阅读结果会自动保存为该论文的子笔记。当前单独上传的 PDF 仍可下载笔记。';
    const url = new URL(location.href); url.searchParams.set('reading', currentDocument.id); url.hash = 'reading'; history.replaceState(null, '', url);
  }
  async function upload(file) {
    if (!file) return;
    if (file.size > 50 * 1024 * 1024) { status('请选择不超过 50 MB 的 PDF', 'error'); return; }
    status('正在本机准备完整 PDF，此步骤不调用 API');
    try { const form = new FormData(); form.append('file', file); const result = await api('/api/reading/documents', { method: 'POST', body: form }); selectDocument(result.document); status('论文已准备好，点击开始深度阅读后才调用所选 API。'); }
    catch (error) { status(error.message, 'error'); }
  }
  async function readExisting(filename) {
    if (!filename) return;
    try { const result = await api('/api/reading/documents', post({ existingFile: filename })); selectDocument(result.document); if (typeof switchTab === 'function') switchTab('reading'); status('已选择这篇 PDF，准备开始深度阅读。'); }
    catch (error) { status(error.message, 'error'); }
  }
  async function loadExisting() {
    try {
      const result = await api('/translatedInfo'); const select = $('readingExisting'); select.replaceChildren(); option(select, '也可选择服务目录中的 PDF', '');
      for (const file of result.files || []) option(select, file.fileName, file.fileName);
    } catch (_) { /* File upload remains available. */ }
  }
  async function renderReport(markdown) {
    const report = $('readingReport');
    if (window.MathJax?.typesetClear) window.MathJax.typesetClear([report]);
    const formulas = [];
    const source = markdown.replace(/\$\$[\s\S]*?\$\$|\$(?:\\.|[^$\\\n])+\$/g, match => {
      const index = formulas.push(match) - 1; return `ZOTEROMATHPLACEHOLDER${index}END`;
    });
    report.innerHTML = DOMPurify.sanitize(marked.parse(source), { USE_PROFILES: { html: true }, FORBID_TAGS: ['img', 'style', 'svg', 'math', 'iframe', 'object', 'embed', 'form', 'input', 'button'] });
    const walker = document.createTreeWalker(report, NodeFilter.SHOW_TEXT), nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      if (!node.textContent.includes('ZOTEROMATHPLACEHOLDER')) continue;
      node.textContent = node.textContent.replace(/ZOTEROMATHPLACEHOLDER(\d+)END/g, (_, index) => formulas[Number(index)] || '');
    }
    report.querySelectorAll('a').forEach(link => { link.rel = 'noopener noreferrer'; link.target = '_blank'; });
    report.hidden = false;
    if (window.MathJax?.startup?.promise) await window.MathJax.startup.promise;
    if (window.MathJax?.typesetPromise) await window.MathJax.typesetPromise([report]);
  }
  async function showJob(job) {
    const changed = currentJob?.id !== job.id || currentJob?.markdown !== job.markdown;
    currentJob = job; busy = job.state === 'running'; startState();
    $('readingProgress').value = job.progress || 0; $('readingProgress').hidden = false;
    status(job.message, job.state === 'failed' || job.state === 'partial' ? 'error' : job.state === 'completed' ? 'success' : '');
    const usage = job.usage || {};
    $('readingUsage').textContent = `模型 ${job.model} · 阅读请求 ${job.apiCalls || 0} 次 · 检索请求 ${job.searchApiCalls || 0} 次 · 阅读输入 token ${usage.prompt_tokens || 0} · 阅读输出 token ${usage.completion_tokens || 0}`;
    if (job.estimatedReadingTokenCny != null) $('readingUsage').textContent += ` · 阅读 token 部分估算 ${job.estimatedReadingTokenCny.toFixed(4)} 元，检索费用另计`;
    else if (job.estimatedCny != null) $('readingUsage').textContent += ` · 原记录估算 ${job.estimatedCny.toFixed(4)} 元`;
    const searchUsage = job.webResearch?.usage;
    if (searchUsage && Object.keys(searchUsage).length && job.webResearch.usageComplete) $('readingUsage').textContent += ` · 检索输入 token ${searchUsage.prompt_tokens || 0} · 检索输出 token ${searchUsage.completion_tokens || 0}`;
    if (job.webResearch?.protocol === 'deepseek') $('readingUsage').textContent += ' · 检索按请求计费';
    if (usage.reasoning_tokens) $('readingUsage').textContent += ` · 输出含思考 token ${usage.reasoning_tokens}`;
    if (job.usageComplete === false) $('readingUsage').textContent += ' · 服务商未返回完整阅读 token 统计，费用请查看账单';
    $('downloadReading').hidden = !job.markdown;
    $('exportReadingHtml').hidden = !job.markdown;
    const target = job.zoteroTarget;
    $('readingNoteStatus').textContent = !target ? '当前阅读未关联 Zotero 条目，可下载笔记。下次从 Zotero 右键打开论文即可自动归档。' : ['failed', 'cancelled', 'interrupted'].includes(job.state) && !job.markdown ? '本次阅读未生成子笔记，请查看任务状态。' : job.noteState === 'saved' ? `已保存为 Zotero 子笔记，归属 ${target.title || '所选论文'}。` : job.noteState === 'error' ? job.noteError : job.noteState === 'pending' ? `阅读已完成，等待 Zotero 插件保存子笔记。请保持 Zotero 开启，归属 ${target.title || '所选论文'}。` : `阅读完成后会自动保存到 ${target.title || '所选论文'} 的子笔记中。`;
    if (job.markdown) { $('downloadReading').href = `/api/reading/jobs/${job.id}/download`; if (changed) await renderReport(job.markdown); }
    if (busy || ['pending', 'error'].includes(job.noteState)) polling = setTimeout(() => pollJob(job.id), busy ? 1200 : 3000);
    else await loadHistory();
  }
  async function pollJob(id) {
    try { await showJob((await api(`/api/reading/jobs/${id}`)).job); }
    catch (error) { busy = false; startState(); status(error.message + '，可刷新阅读记录查看结果。', 'error'); }
  }
  async function startReading() {
    if (!currentDocument || busy) return;
    busy = true; startState(); $('readingReport').hidden = true;
    clearTimeout(polling);
    try { const result = await api('/api/reading/jobs', post({ documentId: currentDocument.id, provider: $('readingProvider').value })); await showJob(result.job); }
    catch (error) { busy = false; startState(); status(error.message, 'error'); }
  }
  async function cancelReading() {
    if (!currentJob || !busy) return;
    try {
      const result = await api(`/api/reading/jobs/${currentJob.id}/cancel`, post({ clientID: currentJob.zoteroTarget?.clientID }));
      clearTimeout(polling); await showJob(result.job);
    } catch (error) { status(error.message, 'error'); }
  }
  async function loadHistory() {
    const data = await api('/api/reading/jobs'), select = $('readingHistory'); select.replaceChildren(); option(select, '查看已有阅读记录', '');
    for (const job of data.jobs) option(select, `${job.filename} · ${{ completed: '已完成', running: '进行中', partial: '未完成', failed: '失败' }[job.state] || job.state}`, job.id);
  }
  function exportHtml() {
    if (!currentJob?.markdown) return;
    const css = `.report{max-width:960px;margin:48px auto;padding:0 28px;font:16px/1.95 system-ui;color:#243447}h2{margin-top:32px}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px}mjx-container{max-width:100%;overflow:auto}pre{white-space:pre-wrap}`;
    const blob = new Blob([`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>论文深度阅读</title><style>${css}</style><article class="report">${$('readingReport').innerHTML}</article></html>`], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = (currentJob.filename || 'paper').replace(/\.pdf$/i, '') + '.深度阅读.html'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 2000);
  }
  window.addEventListener('load', async () => {
    $('preserveColumns').addEventListener('change', saveLayout); $('mathMode').addEventListener('change', saveLayout);
    $('documentMode').addEventListener('change', describeDocument);
    $('readingProvider').addEventListener('change', () => { configured = readingProfiles.some(profile => profile.id === $('readingProvider').value && profile.configured !== false); startState(); describeDocument(); });
    $('loginCodex').addEventListener('click', loginCodex);
    $('refreshCodex').addEventListener('click', () => Promise.all([loadCodex(), loadConfig()]).catch(error => status(error.message, 'error')));
    $('saveModelBackend').addEventListener('click', saveModelBackend);
    $('saveSharedApi').addEventListener('click', saveConfig); $('refreshSharedApi').addEventListener('click', () => loadConfig().catch(error => status(error.message, 'error')));
    $('readingFile').addEventListener('change', event => upload(event.target.files[0]));
    $('readingExisting').addEventListener('change', event => readExisting(event.target.value));
    $('readingHistory').addEventListener('change', event => { if (event.target.value) { clearTimeout(polling); pollJob(event.target.value); } });
    $('startReading').addEventListener('click', startReading); $('cancelReading').addEventListener('click', cancelReading);
    $('exportReadingHtml').addEventListener('click', exportHtml);
    await Promise.allSettled([loadLayout(), loadConfig(), loadCodex(), loadExisting(), loadHistory()]);
    const documentId = new URL(location.href).searchParams.get('reading');
    const jobId = new URL(location.href).searchParams.get('readingJob');
    if (documentId || location.hash === '#reading') {
      if (typeof switchTab === 'function') switchTab('reading');
      if (documentId) try { selectDocument((await api(`/api/reading/documents/${encodeURIComponent(documentId)}`)).document); } catch (error) { status(error.message, 'error'); }
      if (jobId && /^[a-f0-9]{32}$/.test(jobId)) await pollJob(jobId);
    }
    // Add an entry beside PDF previews without interpolating filenames as HTML.
    const addReadingButtons = () => {
      document.querySelectorAll('a[href^="/translatedFile/"]').forEach(link => {
        if (link.dataset.readingEntry) return;
        link.dataset.readingEntry = '1';
        const path = new URL(link.href).pathname, filename = decodeURIComponent(path.slice('/translatedFile/'.length));
        const button = document.createElement('button'); button.className = 'action-btn'; button.textContent = '深度阅读'; button.addEventListener('click', event => { event.stopPropagation(); readExisting(filename); }); link.after(button);
      });
    };
    new MutationObserver(addReadingButtons).observe($('historyList'), { childList: true, subtree: true }); addReadingButtons();
  });
})();
