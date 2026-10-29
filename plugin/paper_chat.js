/* SPDX-License-Identifier: AGPL-3.0-only
 * Kinbo paper conversation and reader integration, independently implemented. */
var KinboPaperChat = (() => {
  const pluginID = 'pdf2zh@guaguastandup.com';
  const prefRoot = 'extensions.zotero.pdf2zh.paperChat.';
  const htmlNS = 'http://www.w3.org/1999/xhtml';
  const panels = new Map(), toolbarButtons = new Set();
  let options = null, started = false, observerID = null;
  const toolbarRetries = new Map();

  function element(doc, tag, text, className) {
    const node = doc.createElementNS(htmlNS, tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
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
  function readerView(reader) {
    const view = reader?._internalReader?._primaryView;
    const win = view?._iframeWindow;
    const app = win?.PDFViewerApplication || win?.wrappedJSObject?.PDFViewerApplication;
    if (!app?.pdfDocument) throw fail('PDF 尚未就绪，请等待论文加载完成');
    return { view, win, app, pdf: app.pdfDocument };
  }
  function inRealm(value, win) {
    if (typeof Components !== 'undefined' && Components.utils?.cloneInto) return Components.utils.cloneInto(value, win);
    return win?.JSON?.parse ? win.JSON.parse(JSON.stringify(value)) : value;
  }
  function charText(char) {
    return String(char.u || '') + (char.paragraphBreakAfter ? '\n\n' : char.lineBreakAfter ? '\n' : char.spaceAfter ? ' ' : '');
  }
  async function pageContent(reader, number) {
    const { pdf, win } = readerView(reader);
    if (typeof pdf.getPageData === 'function') {
      const data = await pdf.getPageData(inRealm({ pageIndex: number - 1 }, win));
      if (Array.isArray(data?.chars)) return { text: data.chars.map(charText).join(''), chars: data.chars };
    }
    const page = await pdf.getPage(number);
    const data = await page.getTextContent();
    return { text: (data.items || []).map(item => String(item.str || '') + (item.hasEOL ? '\n' : ' ')).join(''), chars: [] };
  }
  async function extractPages(reader, progress) {
    const { pdf } = readerView(reader);
    const count = Number(pdf.numPages);
    if (!Number.isInteger(count) || count < 1) throw fail('无法读取 PDF 页数');
    const pages = [];
    let textBytes = 0;
    for (let page = 1; page <= count; page++) {
      if (progress) progress(page, count);
      const content = await pageContent(reader, page);
      textBytes += content.text.length;
      // No excerpting or silent truncation. The backend also validates its own limit.
      if (textBytes > 4000000) throw fail('论文文字超过对话输入上限，未发送任何模型请求');
      pages.push({ page, text: content.text });
    }
    if (!pages.some(page => page.text.trim())) throw fail('PDF 没有可读取的文字，请先完成 OCR');
    return pages;
  }
  function canonical(value) { return String(value).normalize('NFC').replace(/[\s\u00ad]/g, ''); }
  function quoteRects(chars, quote) {
    const needle = canonical(quote);
    if (!needle) return [];
    let text = '';
    const indices = [];
    chars.forEach((char, index) => {
      const part = canonical(char.u || '');
      text += part;
      for (let cursor = 0; cursor < part.length; cursor++) indices.push(index);
    });
    const at = text.indexOf(needle);
    if (at < 0 || text.indexOf(needle, at + 1) !== -1) return [];
    const unique = new Map();
    for (let cursor = indices[at]; cursor <= indices[at + needle.length - 1]; cursor++) {
      const rect = chars[cursor]?.rect;
      if (Array.isArray(rect) && rect.length === 4 && rect.every(Number.isFinite)) unique.set(rect.join(','), Array.from(rect));
    }
    return [...unique.values()];
  }
  function citation(href) {
    const match = /^kinbo:\/\/page\/(\d+)(?:\?quote=([^#]*))?$/.exec(String(href));
    if (!match) return null;
    let quote = '';
    try { quote = decodeURIComponent(match[2] || ''); } catch (_) { return null; }
    const page = Number(match[1]);
    return Number.isSafeInteger(page) && page >= 1 ? { page, quote } : null;
  }
  function clearHighlights(panel) {
    for (const node of panel.highlights) node.remove();
    panel.highlights.length = 0;
    if (panel.highlightTimer) panel.win.clearTimeout(panel.highlightTimer);
  }
  async function navigate(panel, target) {
    const { pdf } = readerView(panel.reader);
    if (target.page > pdf.numPages) throw fail('该引用页码超出 PDF 范围');
    clearHighlights(panel);
    const data = target.quote ? await pageContent(panel.reader, target.page) : { chars: [] };
    const rects = quoteRects(data.chars, target.quote);
    await panel.reader.navigate(rects.length ? { position: { pageIndex: target.page - 1, rects } } : { pageIndex: target.page - 1 });
    panel.status.textContent = rects.length ? '已定位原文，临时高亮会自动消失' : '已跳到对应 PDF 页，请核对原文';
    if (!rects.length) return;
    const { app, win } = readerView(panel.reader);
    const pageView = app.pdfViewer?.getPageView(target.page - 1);
    if (!pageView?.div || !pageView.viewport?.convertToViewportRectangle) return;
    for (const rect of rects) {
      const [x1, y1, x2, y2] = pageView.viewport.convertToViewportRectangle(inRealm(rect, win));
      const mark = element(pageView.div.ownerDocument, 'div');
      mark.setAttribute('data-kinbo-quote', 'true');
      mark.style.cssText = `position:absolute;pointer-events:none;z-index:8;background:rgba(255,199,42,.45);left:${Math.min(x1,x2)}px;top:${Math.min(y1,y2)}px;width:${Math.abs(x2-x1)}px;height:${Math.abs(y2-y1)}px;`;
      pageView.div.appendChild(mark); panel.highlights.push(mark);
    }
    panel.highlightTimer = panel.win.setTimeout(() => clearHighlights(panel), 5000);
  }
  function appendInline(doc, parent, text) {
    // Build DOM from text. Model HTML, images and arbitrary URL schemes never execute.
    const tokens = /\[([^\]\n]+)\]\(([^\s)]+)\)|`([^`\n]+)`|\*\*([^*\n]+)\*\*/g;
    let end = 0, match;
    while ((match = tokens.exec(text))) {
      parent.appendChild(doc.createTextNode(text.slice(end, match.index)));
      if (match[1]) {
        const href = match[2];
        const link = element(doc, 'a', match[1]);
        if (citation(href) || /^https?:\/\//i.test(href)) link.setAttribute('href', href);
        else link.setAttribute('title', '此链接不可打开');
        parent.appendChild(link);
      } else parent.appendChild(element(doc, match[3] ? 'code' : 'strong', match[3] || match[4]));
      end = tokens.lastIndex;
    }
    parent.appendChild(doc.createTextNode(text.slice(end)));
  }
  function renderText(doc, parent, content) {
    let code = null;
    for (const line of String(content || '').split('\n')) {
      if (/^\s*```/.test(line)) {
        if (code) code = null;
        else { code = element(doc, 'pre', ''); parent.appendChild(code); }
        continue;
      }
      if (code) { code.appendChild(doc.createTextNode(line + '\n')); continue; }
      const heading = /^(#{1,6})\s+(.+)$/.exec(line);
      const node = element(doc, heading ? 'h' + Math.min(heading[1].length + 1, 6) : 'p');
      appendInline(doc, node, heading ? heading[2] : line || '\u00a0');
      parent.appendChild(node);
    }
  }
  function setBusy(panel, busy) {
    panel.busy = !!busy;
    panel.send.disabled = panel.busy || !panel.session;
    panel.cancel.disabled = !panel.busy;
    panel.clear.disabled = panel.busy || !panel.session;
    panel.mode.disabled = panel.busy;
    panel.provider.disabled = panel.busy;
    panel.model.disabled = panel.busy;
  }
  function renderSources(doc, parent, sources) {
    if (!Array.isArray(sources) || !sources.length) return;
    const section = element(doc, 'div', undefined, 'kinbo-chat-sources');
    section.appendChild(element(doc, 'b', '联网来源'));
    for (const source of sources) {
      const href = source.url || source.uri;
      if (!/^https?:\/\//i.test(href || '')) continue;
      const row = element(doc, 'p'), link = element(doc, 'a', source.title || href);
      link.setAttribute('href', href); row.appendChild(link); section.appendChild(row);
    }
    parent.appendChild(section);
  }
  function renderSession(panel, session) {
    if (panel.closed) return;
    panel.session = session;
    const signature = JSON.stringify([session.messages, session.error, session.reasoning, session.sources]);
    if (signature !== panel.rendered) {
      panel.rendered = signature;
      const nearBottom = panel.messages.scrollHeight - panel.messages.scrollTop - panel.messages.clientHeight < 90;
      panel.messages.replaceChildren();
      for (const message of session.messages || []) {
        const article = element(panel.doc, 'article', undefined, 'kinbo-chat-message ' + (message.role === 'user' ? 'kinbo-chat-user' : 'kinbo-chat-assistant'));
        article.appendChild(element(panel.doc, 'b', message.role === 'user' ? '你' : 'Kinbo'));
        if (message.reasoning) {
          const details = element(panel.doc, 'details');
          details.appendChild(element(panel.doc, 'summary', '公开推理摘要'));
          const body = element(panel.doc, 'div'); renderText(panel.doc, body, message.reasoning); details.appendChild(body); article.appendChild(details);
        }
        renderText(panel.doc, article, message.content || message.text || '');
        renderSources(panel.doc, article, message.sources);
        if (message.incomplete) article.appendChild(element(panel.doc, 'p', '回答尚未完成，已有内容已保留', 'kinbo-chat-error'));
        panel.messages.appendChild(article);
      }
      if (session.reasoning) {
        const details = element(panel.doc, 'details'); details.appendChild(element(panel.doc, 'summary', '本次公开推理摘要'));
        const body = element(panel.doc, 'div'); renderText(panel.doc, body, session.reasoning); details.appendChild(body); panel.messages.appendChild(details);
      }
      renderSources(panel.doc, panel.messages, session.sources);
      if (session.error) panel.messages.appendChild(element(panel.doc, 'p', String(session.error), 'kinbo-chat-error'));
      if (nearBottom || !panel.didRender) panel.messages.scrollTop = panel.messages.scrollHeight;
      panel.didRender = true;
    }
    setBusy(panel, session.busy);
    panel.status.textContent = session.busy ? '正在回答，可停止本次生成' : session.error ? '本次回答未完成，已有对话已保留' : '对话保存在本机，发送时才请求所选模型';
    if (session.emptyPages?.length) panel.status.textContent += '。其中 ' + session.emptyPages.length + ' 页没有可读取文字，需先做 OCR 才能讨论这些页';
    if (session.busy) schedulePoll(panel);
  }
  function schedulePoll(panel) {
    if (panel.closed || panel.pollTimer) return;
    panel.pollTimer = panel.win.setTimeout(async () => {
      panel.pollTimer = null;
      if (panel.closed || !panel.session) return;
      try { renderSession(panel, (await request('/sessions/' + panel.session.id)).session); }
      catch (error) { panel.status.textContent = safeError(error); schedulePoll(panel); }
    }, 1000);
  }
  function selectOptions(select, values, wanted) {
    select.replaceChildren();
    for (const [value, label] of values) {
      const option = element(select.ownerDocument, 'option', label); option.value = value; select.appendChild(option);
    }
    if (values.some(value => value[0] === wanted)) select.value = wanted;
  }
  async function updateMode(panel) {
    const isCodex = panel.mode.value === 'codex';
    panel.provider.hidden = isCodex;
    panel.login.hidden = !isCodex;
    panel.network.disabled = !isCodex;
    panel.effort.disabled = !isCodex;
    panel.network.checked = isCodex && !!pref('webSearch', false);
    panel.modelList.replaceChildren();
    save('mode', panel.mode.value);
    if (!isCodex) {
      const selected = (panel.config.profiles || []).find(profile => profile.id === panel.provider.value);
      panel.model.value = selected?.model || '';
      panel.model.readOnly = true;
      panel.status.textContent = selected ? '复用已有翻译 API，发送时调用 ' + selected.model : '请先在 Kinbo 翻译设置中配置自己的 API';
      return;
    }
    panel.model.readOnly = false;
    panel.model.value = pref('codexModel');
    panel.status.textContent = panel.config.codex?.authenticated ? '已连接本机 Codex 登录' : panel.config.codex?.message || '请登录本机 Codex 后发送问题';
    try {
      const response = await request('/models?mode=codex');
      const models = response.models || response.data || [];
      panel.codexModels = models;
      for (const model of models) {
        const option = element(panel.doc, 'option'); option.value = model.model || model.id; option.label = model.displayName || option.value; panel.modelList.appendChild(option);
      }
      if (!panel.model.value) panel.model.value = (models.find(model => model.isDefault)?.model || models.find(model => model.isDefault)?.id || models[0]?.model || models[0]?.id || '');
      updateEffort(panel);
    } catch (error) { panel.status.textContent = safeError(error); }
  }
  function updateEffort(panel) {
    const model = (panel.codexModels || []).find(model => (model.model || model.id) === panel.model.value);
    const efforts = model?.supportedReasoningEfforts || [];
    const values = [['', '模型默认思考强度'], ...efforts.map(value => [value.reasoningEffort || value.effort || value, value.description || value.reasoningEffort || value.effort || value])];
    selectOptions(panel.effort, values, pref('effort'));
    panel.effort.disabled = panel.mode.value !== 'codex';
  }
  function applySide(panel, side) {
    panel.side = side === 'left' ? 'left' : 'right';
    panel.sideButton.textContent = panel.side === 'left' ? '移到右侧' : '移到左侧';
    if (panel.side === 'left') panel.host.insertBefore(panel.aside, panel.reader._iframe);
    else panel.host.appendChild(panel.aside);
    save('side', panel.side);
  }
  function selection(panel, selected) {
    panel.selection = selected || null;
    panel.selectionBox.hidden = !selected?.text;
    panel.selectionText.textContent = selected?.text ? '第 ' + selected.page + ' 页选文\n' + selected.text : '';
    panel.question.focus();
  }
  async function send(panel) {
    if (panel.busy || !panel.session) return;
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
      panel.question.value = ''; selection(panel, null); renderSession(panel, result.session);
    } catch (error) { setBusy(panel, false); panel.status.textContent = safeError(error); }
  }
  async function login(panel, startLogin) {
    try {
      const response = await request('/login', startLogin ? {} : undefined);
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
    } catch (error) { panel.status.textContent = safeError(error); }
  }
  function close(panel) {
    if (!panel || panel.closed) return;
    panel.closed = true;
    for (const timer of [panel.pollTimer, panel.loginTimer]) if (timer) panel.win.clearTimeout(timer);
    clearHighlights(panel);
    panel.aside.remove();
    panel.host.style.cssText = panel.hostStyle;
    panel.reader._iframe.style.cssText = panel.frameStyle;
    panel.win.removeEventListener('unload', panel.onUnload);
    panels.delete(panel.reader);
  }
  const css = `
    .kinbo-paper-chat{display:flex;flex-direction:column;flex:0 0 360px;width:360px;min-width:270px;max-width:65%;height:100%;min-height:0;background:var(--material-background,#f9fafc);color:var(--fill-primary,#202936);border-inline-start:1px solid #bdc5d0;font:13px/1.5 system-ui,sans-serif;box-sizing:border-box}
    .kinbo-paper-chat *{box-sizing:border-box}.kinbo-paper-chat header{display:flex;gap:6px;align-items:center;padding:10px;border-bottom:1px solid #ccd3dd}.kinbo-paper-chat header b{flex:1}.kinbo-paper-chat button,.kinbo-paper-chat select,.kinbo-paper-chat input,.kinbo-paper-chat textarea{font:inherit;color:inherit;background:var(--material-background,#fff);border:1px solid #aab5c4;border-radius:5px;padding:5px 7px}.kinbo-paper-chat button{cursor:pointer}.kinbo-paper-chat button:disabled{opacity:.5;cursor:default}.kinbo-paper-chat button.kinbo-send{background:#345e8a;color:#fff;border-color:#345e8a}.kinbo-chat-messages{flex:1;min-height:80px;overflow:auto;padding:12px;user-select:text}.kinbo-chat-message{padding:10px 0;border-bottom:1px solid #dce1e8;overflow-wrap:anywhere}.kinbo-chat-user{color:var(--fill-primary,#263f59)}.kinbo-chat-message p{margin:5px 0;white-space:pre-wrap}.kinbo-paper-chat pre{white-space:pre-wrap;overflow-wrap:anywhere;background:rgba(100,120,150,.1);padding:8px}.kinbo-paper-chat a{color:#2a659f;text-decoration:underline;cursor:pointer}.kinbo-chat-error{color:#b33131}.kinbo-chat-controls{padding:10px;border-top:1px solid #ccd3dd;overflow:auto;max-height:55%;display:flex;flex-direction:column;gap:7px}.kinbo-chat-row{display:flex;gap:6px;align-items:center}.kinbo-chat-row>*{min-width:0;flex:1}.kinbo-chat-row button{flex:0 0 auto}.kinbo-paper-chat textarea{width:100%;resize:vertical;min-height:58px}.kinbo-paper-chat .kinbo-question{min-height:78px}.kinbo-chat-status{font-size:12px;color:var(--fill-secondary,#566475);padding:0 10px 8px}.kinbo-selection{border-inline-start:3px solid #668aae;padding:6px;background:rgba(80,120,170,.08)}.kinbo-selection p{max-height:100px;overflow:auto;white-space:pre-wrap;margin:0}.kinbo-paper-chat details>summary{cursor:pointer}.kinbo-paper-chat label{display:block}.kinbo-paper-chat label input[type=checkbox]{margin-inline-end:6px}.kinbo-paper-chat [hidden]{display:none!important}
  `;
  async function open(reader, selected) {
    if (!started || !reader?._iframe?.parentElement) return;
    if (panels.has(reader)) { const panel = panels.get(reader); if (selected) selection(panel, selected); return panel; }
    const host = reader._iframe.parentElement, doc = host.ownerDocument, win = doc.defaultView;
    const panel = { reader, host, doc, win, hostStyle: host.style.cssText, frameStyle: reader._iframe.style.cssText,
      highlights: [], closed: false, session: null, busy: false };
    const aside = panel.aside = element(doc, 'aside', undefined, 'kinbo-paper-chat'); aside.setAttribute('aria-label', 'Kinbo 论文对话');
    aside.appendChild(element(doc, 'style', css));
    const header = element(doc, 'header'); header.appendChild(element(doc, 'b', 'Kinbo 论文对话'));
    panel.sideButton = element(doc, 'button', '移到左侧'); header.appendChild(panel.sideButton);
    const closeButton = element(doc, 'button', '关闭'); header.appendChild(closeButton); aside.appendChild(header);
    panel.messages = element(doc, 'div', '准备当前论文的完整文字', 'kinbo-chat-messages'); panel.messages.setAttribute('aria-live', 'polite'); aside.appendChild(panel.messages);
    const controls = element(doc, 'div', undefined, 'kinbo-chat-controls'); aside.appendChild(controls);
    panel.selectionBox = element(doc, 'div', undefined, 'kinbo-selection'); panel.selectionBox.hidden = true;
    panel.selectionText = element(doc, 'p'); panel.selectionBox.appendChild(panel.selectionText);
    const removeSelection = element(doc, 'button', '移除选文'); panel.selectionBox.appendChild(removeSelection); controls.appendChild(panel.selectionBox);
    panel.question = element(doc, 'textarea', undefined, 'kinbo-question'); panel.question.placeholder = '向这篇论文提问，Ctrl+Enter 发送'; panel.question.setAttribute('aria-label', '论文问题'); controls.appendChild(panel.question);
    const actions = element(doc, 'div', undefined, 'kinbo-chat-row');
    panel.send = element(doc, 'button', '发送', 'kinbo-send'); panel.send.disabled = true; actions.appendChild(panel.send);
    panel.cancel = element(doc, 'button', '停止'); panel.cancel.disabled = true; actions.appendChild(panel.cancel);
    panel.clear = element(doc, 'button', '清空对话'); panel.clear.disabled = true; actions.appendChild(panel.clear); controls.appendChild(actions);
    const settings = element(doc, 'details'); settings.appendChild(element(doc, 'summary', '模型与设置')); controls.appendChild(settings);
    const modeRow = element(doc, 'div', undefined, 'kinbo-chat-row');
    panel.mode = element(doc, 'select'); panel.mode.setAttribute('aria-label', '模型接入方式'); selectOptions(panel.mode, [['api', '已有翻译 API'], ['codex', 'Codex 登录']], pref('mode', 'api')); modeRow.appendChild(panel.mode);
    panel.login = element(doc, 'button', '登录 Codex'); modeRow.appendChild(panel.login); settings.appendChild(modeRow);
    panel.loginDetails = element(doc, 'div'); settings.appendChild(panel.loginDetails);
    panel.provider = element(doc, 'select'); panel.provider.setAttribute('aria-label', '翻译 API'); settings.appendChild(panel.provider);
    panel.model = element(doc, 'input'); panel.model.placeholder = '模型名称'; panel.model.setAttribute('aria-label', '模型名称');
    panel.modelList = element(doc, 'datalist'); panel.modelList.id = 'kinbo-models-' + Math.random().toString(36).slice(2); panel.model.setAttribute('list', panel.modelList.id); settings.appendChild(panel.model); settings.appendChild(panel.modelList);
    panel.effort = element(doc, 'select'); panel.effort.setAttribute('aria-label', '思考强度'); selectOptions(panel.effort, [['', '模型默认思考强度']], ''); settings.appendChild(panel.effort);
    const networkLabel = element(doc, 'label'); panel.network = element(doc, 'input'); panel.network.type = 'checkbox'; panel.network.checked = !!pref('webSearch', false); networkLabel.appendChild(panel.network); networkLabel.appendChild(doc.createTextNode('Codex 联网搜索')); settings.appendChild(networkLabel);
    panel.customPrompt = element(doc, 'textarea'); panel.customPrompt.placeholder = '自定义回答要求'; panel.customPrompt.value = pref('prompt'); panel.customPrompt.setAttribute('aria-label', '自定义回答要求'); settings.appendChild(panel.customPrompt);
    settings.appendChild(element(doc, 'p', 'PDF 文字会随提问交给所选服务。扫描页和图片内部内容需要先做 OCR。'));
    panel.status = element(doc, 'div', '正在连接本地服务', 'kinbo-chat-status'); panel.status.setAttribute('role', 'status'); aside.appendChild(panel.status);
    host.style.display = 'flex'; host.style.flexDirection = 'row'; host.style.minWidth = '0';
    reader._iframe.style.flex = '1 1 0'; reader._iframe.style.minWidth = '0';
    panels.set(reader, panel); applySide(panel, pref('side', 'right'));
    panel.onUnload = () => close(panel); win.addEventListener('unload', panel.onUnload);
    panel.sideButton.addEventListener('click', () => applySide(panel, panel.side === 'left' ? 'right' : 'left'));
    closeButton.addEventListener('click', () => close(panel)); removeSelection.addEventListener('click', () => selection(panel, null));
    panel.send.addEventListener('click', () => send(panel));
    panel.question.addEventListener('keydown', event => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); send(panel); } });
    panel.mode.addEventListener('change', () => updateMode(panel)); panel.provider.addEventListener('change', () => updateMode(panel));
    panel.model.addEventListener('change', () => updateEffort(panel)); panel.login.addEventListener('click', () => login(panel, true));
    panel.network.addEventListener('change', () => save('webSearch', panel.network.checked));
    panel.customPrompt.addEventListener('change', () => save('prompt', panel.customPrompt.value));
    panel.cancel.addEventListener('click', async () => { try { renderSession(panel, (await request('/sessions/' + panel.session.id + '/cancel', {})).session); } catch (error) { panel.status.textContent = safeError(error); } });
    panel.clear.addEventListener('click', async () => { try { renderSession(panel, (await request('/sessions/' + panel.session.id + '/clear', {})).session); } catch (error) { panel.status.textContent = safeError(error); } });
    panel.onLinkClick = event => {
      // The host document is XUL. Walk XHTML ancestors explicitly, avoiding
      // document-default namespaces changing CSS selector matching.
      let link = event.target;
      while (link && link !== aside && !(link.localName === 'a' && link.namespaceURI === htmlNS)) link = link.parentNode;
      if (!link || link === aside) return;
      event.preventDefault();
      const href = link.getAttribute('href') || '', target = citation(href);
      if (target) navigate(panel, target).catch(error => { panel.status.textContent = error?.kinboSafe ? safeError(error) : '无法定位这条原文引用，请核对 PDF 页码或重新打开论文'; });
      else if (/^https?:\/\//i.test(href)) Zotero.launchURL(href);
    };
    aside.addEventListener('click', panel.onLinkClick, false, true);
    if (selected) selection(panel, selected);
    try {
      await options.syncAPI?.(options.baseURL());
      const result = panel.config = await request('/config');
      if (panel.closed) return panel;
      const profiles = result.profiles || [];
      selectOptions(panel.provider, profiles.map(profile => [profile.id, profile.label + ' · ' + profile.model]), result.active);
      if (!profiles.length && result.codex?.available) panel.mode.value = 'codex';
      await updateMode(panel);
      const pages = await extractPages(reader, (page, count) => { panel.status.textContent = '正在读取完整论文 ' + page + ' / ' + count + ' 页'; });
      if (panel.closed) return panel;
      const item = Zotero.Items.get(reader.itemID);
      if (!item?.key || !item.libraryID) throw fail('无法确定当前 PDF 附件');
      const parent = item.parentID && Zotero.Items.get(item.parentID);
      const response = await request('/sessions', { attachmentKey: item.key, libraryID: item.libraryID,
        title: parent?.getField('title') || item.getField('title') || '论文', pages });
      renderSession(panel, response.session);
    } catch (error) { panel.status.textContent = safeError(error); panel.messages.textContent = '论文对话尚未就绪，关闭面板后可重新打开。'; }
    return panel;
  }
  function toolbarButton(doc, reader) {
    const button = element(doc, 'button', 'Kinbo 对话');
    button.setAttribute('data-kinbo-chat-toggle', 'true');
    button.setAttribute('title', '打开 Kinbo 论文对话边栏');
    button.setAttribute('aria-label', '打开 Kinbo 论文对话边栏');
    button.style.cssText = 'white-space:nowrap;flex:none;min-width:78px;width:auto;height:26px;padding:2px 8px;margin:0 4px;font-size:12px;color:inherit;background:transparent;border:1px solid currentColor;border-radius:4px;-moz-window-dragging:no-drag;';
    button.addEventListener('click', () => { const panel = panels.get(reader); if (panel) close(panel); else return open(reader); });
    for (const prior of toolbarButtons) if (prior.isConnected === false) toolbarButtons.delete(prior);
    toolbarButtons.add(button);
    return button;
  }
  function attachToolbar(reader) {
    if (!started || !reader || (reader._type && reader._type !== 'pdf')) return true;
    const doc = reader._iframeWindow?.document || reader._iframe?.contentDocument;
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
    const win = reader?._iframe?.ownerDocument?.defaultView || Zotero.getMainWindow?.();
    if (!win?.setTimeout || attempt >= 40 || reader?._iframe?.isConnected === false) return;
    const timer = win.setTimeout(() => { toolbarRetries.delete(reader); scheduleToolbar(reader, attempt + 1); }, 250);
    toolbarRetries.set(reader, { win, timer });
  }
  function refreshToolbars() {
    for (const reader of Zotero.Reader?._readers || []) scheduleToolbar(reader);
  }
  function toolbar(event) {
    const doc = event.doc || event.reader?._iframe?.ownerDocument;
    if (!doc || !event.reader) return;
    if (doc.querySelector?.('[data-kinbo-chat-toggle]')) return;
    event.append(toolbarButton(doc, event.reader));
  }
  async function openFromWindow(win) {
    if (!started) throw fail('论文对话尚未加载，请重新启用 Kinbo 插件');
    const tabID = win.Zotero_Tabs?.selectedID;
    let reader = tabID && Zotero.Reader.getByTabID?.(tabID);
    if (!reader) {
      let item = win.ZoteroPane?.getSelectedItems()?.[0];
      if (!item) throw fail('请先打开一篇 PDF，或在文库中选中论文');
      if (!item.isAttachment()) item = await item.getBestAttachment();
      if (!item || item.attachmentContentType !== 'application/pdf') throw fail('所选论文没有可读取的 PDF 附件');
      reader = await Zotero.Reader.open(item.id);
    }
    if (!reader || (reader._type && reader._type !== 'pdf')) throw fail('论文对话需要打开 PDF 阅读器');
    if (reader._initPromise) await reader._initPromise;
    for (let attempt = 0; attempt < 100; attempt++) {
      try { readerView(reader); scheduleToolbar(reader); return await open(reader); } catch (error) {
        if (!error?.kinboSafe || attempt === 99) throw error;
      }
      await new Promise(resolve => win.setTimeout(resolve, 100));
    }
  }
  function selectionPopup(event) {
    const annotation = event.params?.annotation;
    if (!annotation?.text?.trim() || !event.reader) return;
    const doc = event.doc || event.reader._iframe?.ownerDocument;
    if (!doc) return;
    const button = element(doc, 'button', '向 Kinbo 提问');
    button.addEventListener('click', () => open(event.reader, { text: annotation.text, page: (annotation.position?.pageIndex || 0) + 1 }));
    for (const prior of toolbarButtons) if (prior.isConnected === false) toolbarButtons.delete(prior);
    event.append(button); toolbarButtons.add(button);
  }
  return {
    start(config) {
      if (started) return;
      options = config;
      if (!Zotero.Reader?.registerEventListener || typeof options?.baseURL !== 'function') return;
      started = true;
      Zotero.Reader.registerEventListener('renderToolbar', toolbar, pluginID);
      Zotero.Reader.registerEventListener('renderTextSelectionPopup', selectionPopup, pluginID);
      observerID = Zotero.Notifier?.registerObserver({ notify(event, type) {
        if (type === 'tab' && ['add', 'select'].includes(event)) refreshToolbars();
      } }, ['tab'], 'kinbo-paper-chat-toolbars');
      refreshToolbars();
    },
    stop() {
      if (!started) return;
      started = false;
      Zotero.Reader.unregisterEventListener('renderToolbar', toolbar);
      Zotero.Reader.unregisterEventListener('renderTextSelectionPopup', selectionPopup);
      if (observerID !== null) Zotero.Notifier?.unregisterObserver(observerID);
      observerID = null;
      for (const { win, timer } of toolbarRetries.values()) win.clearTimeout(timer);
      toolbarRetries.clear();
      for (const panel of [...panels.values()]) close(panel);
      for (const button of toolbarButtons) button.remove();
      toolbarButtons.clear(); options = null;
    },
    open, openFromWindow,
    // Pure helpers are exposed for deterministic mocked-reader validation.
    helpers: { citation, quoteRects, extractPages, renderText, safeError },
    _test: { citation, quoteRects, extractPages, renderText, safeError, navigate },
  };
})();
