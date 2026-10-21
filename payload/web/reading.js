/* SPDX-License-Identifier: AGPL-3.0-only */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let currentDocument = null, currentJob = null, configured = false, polling = null, busy = false;
  async function api(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok || data.status === 'error') throw new Error(data.message || '操作失败');
    return data;
  }
  const post = data => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  function status(text, kind = '') { $('readingStatus').textContent = text; $('readingStatus').className = 'reading-status ' + kind; }
  function startState() { $('startReading').disabled = !currentDocument || !configured || busy; }
  function option(select, label, value) { const item = document.createElement('option'); item.textContent = label; item.value = value; select.append(item); }
  async function loadLayout() {
    try {
      const result = await api('/api/layout-settings');
      $('preserveColumns').checked = result.settings.preserveColumns;
      $('mathMode').value = result.settings.mathMode;
      const report = result.lastReport;
      $('layoutStatus').textContent = report
        ? `最近一次保护了 ${report.protectedFormulaParagraphs} 个公式段落，${report.fallbacks.length} 个难以排入的段落保留原文。`
        : '整页对照保留原有栏布局。公式保护会优先保留公式位置，无法安全排入的段落保留原文。';
    } catch (error) { $('layoutStatus').textContent = error.message; }
  }
  async function saveLayout() {
    try {
      await api('/api/layout-settings', post({ preserveColumns: $('preserveColumns').checked, mathMode: $('mathMode').value }));
      $('layoutStatus').textContent = '已保存，之后发起的翻译会使用这些排版选项。公式优先模式可能保留含较多公式的整段英文。';
    } catch (error) { $('layoutStatus').textContent = error.message; }
  }
  async function loadConfig() {
    const data = await api('/api/reading/config');
    const select = $('readingProvider'), previous = select.value;
    select.replaceChildren();
    for (const profile of data.profiles) option(select, `${profile.label} · ${profile.model}`, profile.id);
    configured = data.profiles.length > 0;
    if (!configured) option(select, '尚未配置可用于深度阅读的 API', '');
    const requested = new URL(location.href).searchParams.get('api');
    select.value = data.profiles.some(p => p.id === requested) ? requested : data.profiles.some(p => p.id === previous) ? previous : data.selected || '';
    $('sharedApiStatus').textContent = configured
      ? '正在复用翻译 API，深度阅读无需再次填写密钥。'
      : '免费翻译仍可使用。深度阅读需要你配置自己的 API。';
    for (const name of ['contextChars', 'maxOutputTokens', 'inputPrice', 'outputPrice', 'unitCny']) {
      $(name).value = data.options[name] ?? '';
    }
    const compatible = data.profiles.find(p => p.id === 'openaicompatible');
    if (compatible) { $('sharedEndpoint').value = compatible.endpoint; $('sharedModel').value = compatible.model; }
    $('apiConfiguration').open = !configured;
    startState(); describeDocument();
  }
  async function saveConfig() {
    const data = { contextChars: Number($('contextChars').value), maxOutputTokens: Number($('maxOutputTokens').value) };
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
    if (!currentDocument) { $('readingDocumentInfo').textContent = '选择一篇 PDF 后，会显示阅读范围和预计调用次数。'; return; }
    const maximum = Number($('contextChars').value) || 60000;
    const chunks = Math.ceil(currentDocument.characters / maximum);
    const calls = chunks === 1 ? 1 : chunks + 1;
    const images = $('readingVision').checked ? `附带最多 8 个重点页面图像，需要模型支持图片。` : '本次仅发送文字，图表按文字和图注核对。';
    $('readingDocumentInfo').textContent = `${currentDocument.filename}，共 ${currentDocument.pages} 页，提取 ${currentDocument.characters.toLocaleString()} 个字符。预计 ${calls} 次 API 请求，输出过长时可能再续写 1 次。${images}${currentDocument.hasText ? '' : '这份 PDF 缺少文本层，请先做 OCR，或对不超过 8 页的文档启用页面图像。'}`;
  }
  function selectDocument(documentInfo) {
    currentDocument = documentInfo; describeDocument(); startState();
    const url = new URL(location.href); url.searchParams.set('reading', currentDocument.id); url.hash = 'reading'; history.replaceState(null, '', url);
  }
  async function upload(file) {
    if (!file) return;
    if (file.size > 50 * 1024 * 1024) { status('请选择不超过 50 MB 的 PDF', 'error'); return; }
    status('正在本机提取论文内容，此步骤不调用 API');
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
    currentJob = job; busy = job.state === 'running'; startState();
    $('readingProgress').value = job.progress || 0; $('readingProgress').hidden = false;
    status(job.message, job.state === 'failed' || job.state === 'partial' ? 'error' : job.state === 'completed' ? 'success' : '');
    const usage = job.usage || {};
    $('readingUsage').textContent = `模型 ${job.model} · 请求 ${job.apiCalls || 0} 次 · 输入 token ${usage.prompt_tokens || 0} · 输出 token ${usage.completion_tokens || 0}` + (job.estimatedCny != null ? ` · 估算 ${job.estimatedCny.toFixed(4)} 元` : ' · 单价未设置时不估算金额');
    if (job.usageComplete === false) $('readingUsage').textContent = `模型 ${job.model} · 请求 ${job.apiCalls || 0} 次 · 服务商未返回完整 token 统计，费用请查看账单`;
    $('downloadReading').hidden = !job.markdown;
    $('exportReadingHtml').hidden = !job.markdown;
    if (job.markdown) { $('downloadReading').href = `/api/reading/jobs/${job.id}/download`; await renderReport(job.markdown); }
    if (busy) polling = setTimeout(() => pollJob(job.id), 1200);
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
    try { const result = await api('/api/reading/jobs', post({ documentId: currentDocument.id, provider: $('readingProvider').value, vision: $('readingVision').checked })); await showJob(result.job); }
    catch (error) { busy = false; startState(); status(error.message, 'error'); }
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
    $('saveSharedApi').addEventListener('click', saveConfig); $('refreshSharedApi').addEventListener('click', () => loadConfig().catch(error => status(error.message, 'error')));
    $('readingFile').addEventListener('change', event => upload(event.target.files[0]));
    $('readingExisting').addEventListener('change', event => readExisting(event.target.value));
    $('readingHistory').addEventListener('change', event => { if (event.target.value) { clearTimeout(polling); pollJob(event.target.value); } });
    $('startReading').addEventListener('click', startReading); $('readingVision').addEventListener('change', describeDocument);
    $('contextChars').addEventListener('input', describeDocument); $('exportReadingHtml').addEventListener('click', exportHtml);
    await Promise.allSettled([loadLayout(), loadConfig(), loadExisting(), loadHistory()]);
    const documentId = new URL(location.href).searchParams.get('reading');
    if (documentId || location.hash === '#reading') {
      if (typeof switchTab === 'function') switchTab('reading');
      if (documentId) try { selectDocument((await api(`/api/reading/documents/${encodeURIComponent(documentId)}`)).document); } catch (error) { status(error.message, 'error'); }
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
