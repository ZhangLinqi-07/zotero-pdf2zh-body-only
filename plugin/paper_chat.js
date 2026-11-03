/* SPDX-License-Identifier: AGPL-3.0-only
 * Kinbo paper conversation and reader integration, independently implemented. */
var KinboPaperChat = (() => {
  const pluginID = 'pdf2zh@guaguastandup.com';
  const prefRoot = 'extensions.zotero.pdf2zh.paperChat.';
  const htmlNS = 'http://www.w3.org/1999/xhtml';
  const panels = new Map(), toolbarButtons = new Set();
  let options = null, started = false, observerID = null;
  const toolbarRetries = new Map();

  const view = KinboChatView, readerAPI = KinboChatReader;
  const { element, citation, renderText, selectOptions, setBusy, selection } = view;
  const { quoteRects, extractPages, clearHighlights } = readerAPI;
  const buttonListeners = new Map(), pendingWaits = new Set();
  let lifecycle = 0;
  function listen(panel, target, type, handler, options, wantsUntrusted) {
    target.addEventListener(type, handler, options, wantsUntrusted);
    panel.disposers.push(() => target.removeEventListener(type, handler, options));
  }
  function pref(name, fallback = '') {
    try { return Zotero.Prefs.get(prefRoot + name, true) ?? fallback; } catch (_) { return fallback; }
  }
  function save(name, value) { try { Zotero.Prefs.set(prefRoot + name, value, true); } catch (_) {} }
  function safeError(error) {
    return error?.kinboSafe ? String(error.message).replace(/sk-[\w-]+/g, '***').slice(0, 600)
      : '无法连接论文对话服务，请检查 Kinbo 后台地址和版本';
  }
  function fail(message) { const error = new Error(message); error.kinboSafe = true; return error; }
  async function request(path, data) {
    const base = options.baseURL();
    const response = await Zotero.HTTP.request(data === undefined ? 'GET' : 'POST', base + '/api/paper-chat' + path, {
      responseType: 'json', timeout: 120000,
      ...(data === undefined ? {} : { body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } }),
      successCodes: [200, 202, 400, 401, 403, 404, 409, 413, 422, 500, 503],
    });
    const result = response.response;
    if (!result || result.status === 'error' || response.status >= 400) {
      throw fail(result?.message || '论文对话服务暂不可用，请更新并启动 Kinbo 后台');
    }
    return result;
  }
  async function navigate(panel, target) {
    const matched = await readerAPI.navigate(panel, target);
    if (!panel.closed) panel.status.textContent = matched ? '已定位原文，临时高亮会自动消失' : '已跳到对应 PDF 页，请核对原文';
  }
  function renderSession(panel, session) {
    view.renderSession(panel, session);
    if (!panel.closed && session.busy) schedulePoll(panel);
  }
  function schedulePoll(panel) {
    if (!started || panel.closed || panel.pollTimer) return;
    panel.pollTimer = panel.win.setTimeout(async () => {
      panel.pollTimer = null;
      if (panel.closed || !panel.session) return;
      try { renderSession(panel, (await request('/sessions/' + panel.session.id)).session); }
      catch (error) { if (!panel.closed) { panel.status.textContent = safeError(error); schedulePoll(panel); } }
    }, 1000);
  }
  async function updateMode(panel) {
    const revision = panel.modeRevision = (panel.modeRevision || 0) + 1;
    const isCodex = panel.mode.value === 'codex';
    panel.providerField.hidden = isCodex;
    panel.login.hidden = !isCodex;
    panel.networkLabel.setAttribute('title', isCodex ? '使用 Codex 实际检索并记录来源' : '联网搜索仅供 Codex 使用');
    panel.network.disabled = !isCodex;
    panel.effort.disabled = !isCodex;
    panel.network.checked = isCodex && !!pref('webSearch', false);
    panel.modelList.replaceChildren();
    save('mode', panel.mode.value);
    if (!isCodex) {
      const selected = (panel.config.profiles || []).find(profile => profile.id === panel.provider.value);
      panel.model.value = selected?.model || '';
      panel.model.readOnly = true;
      view.modelSummary(panel);
      panel.status.textContent = selected ? '复用已有翻译 API，发送时调用 ' + selected.model : '请先在 Kinbo 翻译设置中配置自己的 API';
      return;
    }
    panel.model.readOnly = false;
    panel.model.value = pref('codexModel');
    view.modelSummary(panel);
    panel.status.textContent = panel.config.codex?.authenticated ? '已连接本机 Codex 登录' : panel.config.codex?.message || '请登录本机 Codex 后发送问题';
    try {
      const response = await request('/models?mode=codex');
      if (panel.closed || panel.modeRevision !== revision) return;
      const models = response.models || response.data || [];
      panel.codexModels = models;
      for (const model of models) {
        const option = element(panel.doc, 'option'); option.value = model.model || model.id; option.label = model.displayName || option.value; panel.modelList.appendChild(option);
      }
      if (!panel.model.value) panel.model.value = (models.find(model => model.isDefault)?.model || models.find(model => model.isDefault)?.id || models[0]?.model || models[0]?.id || '');
      updateEffort(panel);
    } catch (error) { if (!panel.closed && panel.modeRevision === revision) panel.status.textContent = safeError(error); }
  }
  function updateEffort(panel) {
    const model = (panel.codexModels || []).find(model => (model.model || model.id) === panel.model.value);
    const efforts = model?.supportedReasoningEfforts || [];
    const values = [['', '模型默认思考强度'], ...efforts.map(value => [value.reasoningEffort || value.effort || value, value.description || value.reasoningEffort || value.effort || value])];
    selectOptions(panel.effort, values, pref('effort'));
    panel.effort.disabled = panel.busy || panel.mode.value !== 'codex';
    view.modelSummary(panel);
  }
  function applySide(panel, side) {
    panel.side = side === 'left' ? 'left' : 'right';
    const label = panel.side === 'left' ? '移到右侧' : '移到左侧';
    panel.sideButton.setAttribute('aria-label', label); panel.sideButton.setAttribute('title', label);
    readerAPI.place(panel, panel.side); save('side', panel.side);
  }
  async function send(panel) {
    if (panel.closed || panel.busy || !panel.session) return;
    const question = panel.question.value.trim();
    if (!question) { panel.question.focus(); return; }
    if (panel.mode.value === 'api' && !panel.provider.value) { panel.status.textContent = '请先配置并选择自己的翻译 API'; return; }
    setBusy(panel, true);
    try {
      save('codexModel', panel.mode.value === 'codex' ? panel.model.value.trim() : pref('codexModel'));
      save('effort', panel.effort.value); save('prompt', panel.customPrompt.value); save('webSearch', panel.network.checked);
      const result = await request('/sessions/' + panel.session.id + '/messages', {
        question, selection: panel.selection, mode: panel.mode.value, provider: panel.provider.value || undefined,
        model: panel.model.value.trim() || undefined, effort: panel.effort.value || undefined,
        webSearch: panel.mode.value === 'codex' && panel.network.checked, customPrompt: panel.customPrompt.value,
      });
      if (panel.closed) return;
      panel.question.value = ''; selection(panel, null); renderSession(panel, result.session);
    } catch (error) { if (!panel.closed) { setBusy(panel, false); panel.status.textContent = safeError(error); } }
  }
  async function login(panel, startLogin) {
    if (panel.closed || panel.loggingIn) return;
    panel.loggingIn = true;
    if (panel.loginTimer) panel.win.clearTimeout(panel.loginTimer);
    panel.loginTimer = null;
    try {
      const response = await request('/login', startLogin ? {} : undefined);
      if (panel.closed) return;
      const data = response.login || response;
      panel.status.textContent = data.message || (data.authenticated ? 'Codex 已登录' : '正在等待 Codex 登录');
      panel.loginDetails.replaceChildren();
      const uri = data.verificationUri || data.verification_url || data.verificationUrl;
      if (uri && /^https:\/\//i.test(uri)) {
        const link = element(panel.doc, 'a', '打开 Codex 登录页面'); link.setAttribute('href', uri); panel.loginDetails.appendChild(link);
      }
      const userCode = data.userCode || data.user_code;
      if (userCode) panel.loginDetails.appendChild(element(panel.doc, 'p', '登录代码 ' + userCode));
      if (data.authenticated) { panel.config.codex = { ...panel.config.codex, authenticated: true }; return updateMode(panel); }
      if (!panel.closed && data.completed !== true && (data.completed === false || data.pending || data.running || data.state === 'pending' || uri || userCode)) {
        panel.loginTimer = panel.win.setTimeout(() => login(panel, false), 2000);
      }
    } catch (error) { if (!panel.closed) panel.status.textContent = safeError(error); }
    finally { panel.loggingIn = false; }
  }
  function close(panel) {
    if (!panel || panel.closed) return;
    panel.closed = true;
    for (const timer of [panel.pollTimer, panel.loginTimer]) if (timer) panel.win.clearTimeout(timer);
    clearHighlights(panel);
    for (const dispose of panel.disposers.splice(0)) dispose();
    panel.aside.remove(); readerAPI.restore(panel); panels.delete(panel.reader);
    if (panel.returnFocus?.isConnected !== false) panel.returnFocus?.focus?.();
  }
  async function open(reader, selected) {
    const mount = readerAPI.mountInfo(reader);
    if (!started || !mount) return;
    if (panels.has(reader)) { const panel = panels.get(reader); if (selected) selection(panel, selected); return panel; }
    const panel = { ...mount, highlights: [], closed: false, session: null, busy: false, disposers: [] };
    view.create(panel);
    const { aside } = panel;
    selectOptions(panel.mode, [['api', '已有翻译 API'], ['codex', 'Codex 登录']], pref('mode', 'api'));
    selectOptions(panel.effort, [['', '模型默认思考强度']], '');
    panel.network.checked = !!pref('webSearch', false); panel.customPrompt.value = pref('prompt');
    readerAPI.mount(panel); panels.set(reader, panel); applySide(panel, pref('side', 'right'));
    panel.disposers.push(readerAPI.onUnload(panel, () => close(panel)), view.watchTheme(panel));
    listen(panel, panel.sideButton, 'click', () => applySide(panel, panel.side === 'left' ? 'right' : 'left'));
    listen(panel, panel.closeButton, 'click', () => close(panel)); listen(panel, panel.removeSelection, 'click', () => selection(panel, null));
    listen(panel, panel.send, 'click', () => send(panel));
    listen(panel, panel.question, 'keydown', event => { if (!event.isComposing && event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); send(panel); } });
    listen(panel, panel.mode, 'change', () => updateMode(panel)); listen(panel, panel.provider, 'change', () => updateMode(panel));
    listen(panel, panel.model, 'change', () => updateEffort(panel)); listen(panel, panel.login, 'click', () => login(panel, true));
    listen(panel, panel.network, 'change', () => save('webSearch', panel.network.checked));
    listen(panel, panel.customPrompt, 'change', () => save('prompt', panel.customPrompt.value));
    listen(panel, panel.cancel, 'click', async () => { try { renderSession(panel, (await request('/sessions/' + panel.session.id + '/cancel', {})).session); } catch (error) { if (!panel.closed) panel.status.textContent = safeError(error); } });
    listen(panel, panel.clear, 'click', () => { panel.clearConfirmation.hidden = false; panel.cancelClear.focus(); });
    listen(panel, panel.cancelClear, 'click', () => { panel.clearConfirmation.hidden = true; panel.clear.focus(); });
    listen(panel, panel.confirmClear, 'click', async () => {
      if (panel.busy || !panel.session) return;
      panel.clearConfirmation.hidden = true;
      try { renderSession(panel, (await request('/sessions/' + panel.session.id + '/clear', {})).session); panel.question.focus(); }
      catch (error) { if (!panel.closed) panel.status.textContent = safeError(error); }
    });
    panel.onLinkClick = event => {
      // The host document is XUL. Walk XHTML ancestors explicitly, avoiding
      // document-default namespaces changing CSS selector matching.
      let link = event.target;
      if (link?.getAttribute?.('data-kinbo-starter')) { panel.question.value = link.textContent; panel.question.focus(); return; }
      while (link && link !== aside && !(link.localName === 'a' && link.namespaceURI === htmlNS)) link = link.parentNode;
      if (!link || link === aside) return;
      event.preventDefault();
      const href = link.getAttribute('href') || '', target = citation(href);
      if (target) navigate(panel, target).catch(error => { if (!panel.closed) panel.status.textContent = error?.kinboSafe ? safeError(error) : '无法定位这条原文引用，请核对 PDF 页码或重新打开论文'; });
      else if (/^https?:\/\//i.test(href)) Zotero.launchURL(href);
    };
    listen(panel, aside, 'click', panel.onLinkClick, false, true);
    if (selected) selection(panel, selected);
    listen(panel, panel.retry, 'click', () => connect(panel));
    await connect(panel);
    return panel;
  }
  async function connect(panel) {
    if (panel.connecting || panel.closed || !started) return panel;
    panel.connecting = true; panel.retry.hidden = true; panel.retry.disabled = true;
    try {
      await options.syncAPI?.(options.baseURL());
      if (panel.closed) return panel;
      const result = panel.config = await request('/config');
      if (panel.closed) return panel;
      const profiles = result.profiles || [];
      selectOptions(panel.provider, profiles.map(profile => [profile.id, profile.label + ' · ' + profile.model]), result.active);
      if (!profiles.length && result.codex?.available) panel.mode.value = 'codex';
      await updateMode(panel);
      if (panel.closed) return panel;
      const pages = await extractPages(panel.reader, (page, count) => { panel.status.textContent = '正在读取完整论文 ' + page + ' / ' + count + ' 页'; });
      if (panel.closed) return panel;
      const item = Zotero.Items.get(panel.reader.itemID);
      if (!item?.key || !item.libraryID) throw fail('无法确定当前 PDF 附件');
      const parent = item.parentID && Zotero.Items.get(item.parentID);
      const title = parent?.getField('title') || item.getField('title') || '论文';
      panel.paperTitle.textContent = title; panel.paperTitle.setAttribute('title', title);
      const response = await request('/sessions', { attachmentKey: item.key, libraryID: item.libraryID,
        title, pages });
      renderSession(panel, response.session);
    } catch (error) {
      if (!panel.closed) {
        panel.status.textContent = safeError(error);
        if (!panel.session) panel.messages.textContent = '论文对话尚未就绪，请检查后台后重新连接。';
        panel.retry.hidden = false;
      }
    } finally { panel.connecting = false; panel.retry.disabled = false; }
    return panel;
  }
  function toolbarButton(doc, reader) {
    const button = element(doc, 'button', 'Kinbo 对话');
    button.setAttribute('data-kinbo-chat-toggle', 'true');
    button.setAttribute('title', '打开 Kinbo 论文对话边栏');
    button.setAttribute('aria-label', '打开 Kinbo 论文对话边栏');
    button.style.cssText = 'white-space:nowrap;flex:none;min-width:78px;width:auto;height:26px;padding:2px 8px;margin:0 4px;font-size:12px;color:inherit;background:transparent;border:1px solid currentColor;border-radius:4px;-moz-window-dragging:no-drag;';
    trackButton(button, () => { const panel = panels.get(reader); if (panel) close(panel); else return open(reader); });
    return button;
  }
  function trackButton(button, handler) {
    for (const prior of toolbarButtons) if (!readerAPI.isNodeConnected(prior)) {
      readerAPI.releaseButton(prior, buttonListeners.get(prior)); buttonListeners.delete(prior); toolbarButtons.delete(prior);
    }
    button.addEventListener('click', handler); buttonListeners.set(button, handler); toolbarButtons.add(button);
  }
  function attachToolbar(reader) {
    if (!started || !reader || !readerAPI.isPDF(reader)) return true;
    const doc = readerAPI.toolbarDocument(reader);
    if (!doc?.querySelector) return false;
    if (doc.querySelector('[data-kinbo-chat-toggle]')) return true;
    const host = doc.querySelector('.toolbar .end') || doc.querySelector('.toolbar');
    if (!host) return false;
    host.appendChild(toolbarButton(doc, reader));
    return true;
  }
  function scheduleToolbar(reader, attempt = 0) {
    if (!started || toolbarRetries.has(reader)) return;
    try { if (attachToolbar(reader)) return; } catch (_) { /* Reader initialization may still be in progress. */ }
    const win = readerAPI.ownerWindow(reader);
    if (!win?.setTimeout || attempt >= 40 || !readerAPI.isAttached(reader)) return;
    const timer = win.setTimeout(() => { toolbarRetries.delete(reader); scheduleToolbar(reader, attempt + 1); }, 250);
    toolbarRetries.set(reader, { win, timer });
  }
  function refreshToolbars() {
    for (const panel of panels.values()) if (!readerAPI.isAttached(panel.reader)) close(panel);
    for (const reader of readerAPI.allReaders()) scheduleToolbar(reader);
  }
  function toolbar(event) {
    const doc = event.doc || readerAPI.mountInfo(event.reader)?.doc;
    if (!doc || !event.reader) return;
    if (doc.querySelector?.('[data-kinbo-chat-toggle]')) return;
    event.append(toolbarButton(doc, event.reader));
  }
  async function openFromWindow(win) {
    if (!started) throw fail('论文对话尚未加载，请重新启用 Kinbo 插件');
    const epoch = lifecycle;
    const tabID = win.Zotero_Tabs?.selectedID;
    let reader = tabID && Zotero.Reader.getByTabID?.(tabID);
    if (!reader) {
      let item = win.ZoteroPane?.getSelectedItems()?.[0];
      if (!item) throw fail('请先打开一篇 PDF，或在文库中选中论文');
      if (!item.isAttachment()) item = await item.getBestAttachment();
      if (!started || lifecycle !== epoch) return;
      if (!item || item.attachmentContentType !== 'application/pdf') throw fail('所选论文没有可读取的 PDF 附件');
      reader = await Zotero.Reader.open(item.id);
    }
    if (!reader || !readerAPI.isPDF(reader)) throw fail('论文对话需要打开 PDF 阅读器');
    await readerAPI.ready(reader);
    for (let attempt = 0; attempt < 100; attempt++) {
      if (!started || lifecycle !== epoch) return;
      try { readerAPI.readerView(reader); scheduleToolbar(reader); return await open(reader); } catch (error) {
        if (!error?.kinboSafe || attempt === 99) throw error;
      }
      await new Promise(resolve => {
        const wait = { win, resolve };
        wait.timer = win.setTimeout(() => { pendingWaits.delete(wait); resolve(); }, 100); pendingWaits.add(wait);
      });
    }
  }
  function selectionPopup(event) {
    const annotation = event.params?.annotation;
    if (!annotation?.text?.trim() || !event.reader) return;
    const doc = event.doc || readerAPI.mountInfo(event.reader)?.doc;
    if (!doc) return;
    const button = element(doc, 'button', '向 Kinbo 提问');
    trackButton(button, () => open(event.reader, { text: annotation.text, page: (annotation.position?.pageIndex || 0) + 1 }));
    event.append(button);
  }
  return {
    start(config) {
      if (started) return;
      options = config;
      if (!Zotero.Reader?.registerEventListener || typeof options?.baseURL !== 'function') return;
      started = true; lifecycle++;
      Zotero.Reader.registerEventListener('renderToolbar', toolbar, pluginID);
      Zotero.Reader.registerEventListener('renderTextSelectionPopup', selectionPopup, pluginID);
      observerID = Zotero.Notifier?.registerObserver({ notify(event, type) {
        if (type === 'tab' && ['add', 'select'].includes(event)) refreshToolbars();
      } }, ['tab'], 'kinbo-paper-chat-toolbars');
      refreshToolbars();
    },
    stop() {
      if (!started) return;
      started = false; lifecycle++;
      Zotero.Reader.unregisterEventListener('renderToolbar', toolbar);
      Zotero.Reader.unregisterEventListener('renderTextSelectionPopup', selectionPopup);
      if (observerID !== null) Zotero.Notifier?.unregisterObserver(observerID);
      observerID = null;
      for (const { win, timer } of toolbarRetries.values()) win.clearTimeout(timer);
      toolbarRetries.clear();
      for (const wait of pendingWaits) { wait.win.clearTimeout(wait.timer); wait.resolve(); }
      pendingWaits.clear();
      for (const panel of [...panels.values()]) close(panel);
      for (const button of toolbarButtons) readerAPI.releaseButton(button, buttonListeners.get(button));
      buttonListeners.clear();
      toolbarButtons.clear(); options = null;
    },
    open, openFromWindow,
    // Pure helpers are exposed for deterministic mocked-reader validation.
    helpers: { citation, quoteRects, extractPages, renderText, safeError },
    _test: { citation, quoteRects, extractPages, renderText, safeError, navigate },
  };
})();
