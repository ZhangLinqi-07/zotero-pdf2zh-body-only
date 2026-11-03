/* SPDX-License-Identifier: AGPL-3.0-only
 * Kinbo XHTML view. No service calls, preferences or Reader internals. */
var KinboChatView = (() => {
  const htmlNS = 'http://www.w3.org/1999/xhtml', svgNS = 'http://www.w3.org/2000/svg';
  function element(doc, tag, text, className) {
    const node = doc.createElementNS(htmlNS, tag);
    // Zotero's chrome form styles explicitly support this opt-out. Kinbo owns
    // its controls' tokens and focus instead of inheriting the host's gradients.
    if (['button', 'select', 'input', 'textarea'].includes(tag)) node.setAttribute('no-native', '');
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function icon(doc, path) {
    const svg = doc.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
    const line = doc.createElementNS(svgNS, 'path'); line.setAttribute('d', path); svg.appendChild(line);
    return svg;
  }
  function iconButton(doc, label, path) {
    const button = element(doc, 'button', undefined, 'kinbo-icon-button');
    button.setAttribute('aria-label', label); button.setAttribute('title', label);
    button.appendChild(icon(doc, path)); return button;
  }
  function field(doc, label, control) {
    const node = element(doc, 'label', label); node.appendChild(control); return node;
  }
  function selectOptions(select, values, wanted) {
    select.replaceChildren();
    for (const [value, label] of values) {
      const option = element(select.ownerDocument, 'option', label); option.value = value; select.appendChild(option);
    }
    if (values.some(value => value[0] === wanted)) select.value = wanted;
  }
  function citation(href) {
    const match = /^kinbo:\/\/page\/(\d+)(?:\?quote=([^#]*))?$/.exec(String(href));
    if (!match) return null;
    let quote = '';
    try { quote = decodeURIComponent(match[2] || ''); } catch (_) { return null; }
    const page = Number(match[1]);
    return Number.isSafeInteger(page) && page >= 1 ? { page, quote } : null;
  }
  function appendInline(doc, parent, text) {
    // Model HTML, images and arbitrary URL schemes never execute.
    const tokens = /\[([^\]\n]+)\]\(([^\s)]+)\)|`([^`\n]+)`|\*\*([^*\n]+)\*\*/g;
    let end = 0, match;
    while ((match = tokens.exec(text))) {
      parent.appendChild(doc.createTextNode(text.slice(end, match.index)));
      if (match[1]) {
        const href = match[2], link = element(doc, 'a', match[1]);
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
      appendInline(doc, node, heading ? heading[2] : line || '\u00a0'); parent.appendChild(node);
    }
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
    if (section.children.length > 1) parent.appendChild(section);
  }
  function setBusy(panel, busy) {
    panel.busy = !!busy;
    panel.send.disabled = panel.busy || !panel.session;
    panel.send.hidden = panel.busy;
    panel.cancel.disabled = !panel.busy; panel.cancel.hidden = !panel.busy;
    panel.clear.disabled = panel.busy || !panel.session;
    for (const name of ['mode', 'provider', 'model', 'customPrompt']) panel[name].disabled = panel.busy;
    panel.network.disabled = panel.busy || panel.mode.value !== 'codex';
    panel.effort.disabled = panel.busy || panel.mode.value !== 'codex';
    panel.messages.setAttribute('aria-busy', String(panel.busy));
  }
  function selection(panel, selected) {
    panel.selection = selected || null;
    panel.selectionBox.hidden = !selected?.text;
    panel.selectionHeading.textContent = selected?.text ? '第 ' + selected.page + ' 页选文' : '';
    panel.selectionText.textContent = selected?.text || '';
    panel.question.focus();
  }
  function modelSummary(panel) {
    const model = panel.model.value || (panel.mode.value === 'codex' ? 'Codex 默认模型' : '已有翻译 API');
    panel.settingsSummary.textContent = '模型与设置 · ' + model;
  }
  function reasoning(doc, parent, text, label) {
    const details = element(doc, 'details'); details.appendChild(element(doc, 'summary', label));
    const body = element(doc, 'div'); renderText(doc, body, text); details.appendChild(body); parent.appendChild(details);
  }
  function renderSession(panel, session) {
    if (panel.closed) return;
    panel.session = session;
    panel.retry.hidden = !session.error;
    const signature = JSON.stringify([session.messages, session.error, session.reasoning, session.sources, session.busy]);
    if (signature !== panel.rendered) {
      panel.rendered = signature;
      const nearBottom = panel.messages.scrollHeight - panel.messages.scrollTop - panel.messages.clientHeight < 90;
      panel.messages.replaceChildren();
      if (!session.messages?.length && !session.busy && !session.error) {
        const empty = element(panel.doc, 'div', undefined, 'kinbo-chat-empty');
        empty.appendChild(element(panel.doc, 'h2', '从一个问题开始'));
        empty.appendChild(element(panel.doc, 'p', '讨论整篇论文，或在 PDF 中选中文字再提问。回答中的页码可返回原文。'));
        const starter = element(panel.doc, 'button', '这篇论文的核心贡献是什么？', 'kinbo-starter');
        starter.setAttribute('data-kinbo-starter', 'true'); empty.appendChild(starter); panel.messages.appendChild(empty);
      }
      for (const message of session.messages || []) {
        const article = element(panel.doc, 'article', undefined, 'kinbo-chat-message ' + (message.role === 'user' ? 'kinbo-chat-user' : 'kinbo-chat-assistant'));
        article.appendChild(element(panel.doc, 'b', message.role === 'user' ? '你' : 'Kinbo', 'kinbo-chat-role'));
        if (message.reasoning) reasoning(panel.doc, article, message.reasoning, '公开推理摘要');
        renderText(panel.doc, article, message.content || message.text || ''); renderSources(panel.doc, article, message.sources);
        if (message.incomplete) article.appendChild(element(panel.doc, 'p', '回答尚未完成，已有内容已保留', 'kinbo-chat-error'));
        panel.messages.appendChild(article);
      }
      if (session.reasoning) reasoning(panel.doc, panel.messages, session.reasoning, '本次公开推理摘要');
      renderSources(panel.doc, panel.messages, session.sources);
      if (session.busy) panel.messages.appendChild(element(panel.doc, 'p', '正在回答 · 可停止生成', 'kinbo-chat-activity'));
      if (session.error) panel.messages.appendChild(element(panel.doc, 'p', String(session.error), 'kinbo-chat-error'));
      if (nearBottom || !panel.didRender) panel.messages.scrollTop = panel.messages.scrollHeight;
      panel.didRender = true;
    }
    setBusy(panel, session.busy);
    panel.status.textContent = session.busy ? '正在回答，可停止本次生成' : session.error ? '本次回答未完成，已有对话已保留' : '对话保存在本机，发送时才请求所选模型';
    if (session.emptyPages?.length) panel.status.textContent += '。其中 ' + session.emptyPages.length + ' 页没有可读取文字，需先做 OCR 才能讨论这些页';
  }
  function create(panel) {
    const { doc } = panel;
    const aside = panel.aside = element(doc, 'aside', undefined, 'kinbo-paper-chat'); aside.setAttribute('aria-label', 'Kinbo 论文对话');
    if (typeof KinboChatStyles === 'string') aside.appendChild(element(doc, 'style', KinboChatStyles));
    const header = element(doc, 'header', undefined, 'kinbo-chat-header');
    const brand = element(doc, 'div', undefined, 'kinbo-chat-brand'); brand.appendChild(icon(doc, 'M4 4v16m0-8 8-8m-8 8 8 8M15 4h5v16h-5'));
    brand.appendChild(element(doc, 'h1', 'Kinbo')); brand.appendChild(element(doc, 'span', '论文对话')); header.appendChild(brand);
    panel.sideButton = iconButton(doc, '移到左侧', 'M4 5h16v14H4zM9 5v14M16 9l-3 3 3 3'); header.appendChild(panel.sideButton);
    panel.clear = iconButton(doc, '清空本篇对话历史', 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7m4-7v7'); header.appendChild(panel.clear);
    panel.closeButton = iconButton(doc, '关闭论文对话', 'm6 6 12 12M18 6 6 18'); header.appendChild(panel.closeButton); aside.appendChild(header);
    panel.clearConfirmation = element(doc, 'div', undefined, 'kinbo-chat-confirm'); panel.clearConfirmation.hidden = true;
    panel.clearConfirmation.appendChild(element(doc, 'p', '清空本篇历史？此操作无法撤销。'));
    panel.confirmClear = element(doc, 'button', '清空本篇历史'); panel.cancelClear = element(doc, 'button', '取消');
    panel.clearConfirmation.appendChild(panel.confirmClear); panel.clearConfirmation.appendChild(panel.cancelClear); aside.appendChild(panel.clearConfirmation);
    const context = element(doc, 'div', undefined, 'kinbo-chat-context'); panel.paperTitle = element(doc, 'h2', '当前论文'); context.appendChild(panel.paperTitle);
    context.appendChild(element(doc, 'p', '完整文字层 · 历史保存在本机', 'kinbo-chat-caption')); aside.appendChild(context);
    panel.messages = element(doc, 'div', '正在准备当前论文的完整文字…', 'kinbo-chat-messages'); panel.messages.setAttribute('role', 'region'); panel.messages.setAttribute('aria-label', '论文对话记录'); aside.appendChild(panel.messages);
    const controls = element(doc, 'div', undefined, 'kinbo-chat-controls'); aside.appendChild(controls);
    panel.selectionBox = element(doc, 'div', undefined, 'kinbo-selection'); panel.selectionBox.hidden = true;
    const selectionRow = element(doc, 'div', undefined, 'kinbo-selection-heading'); panel.selectionHeading = element(doc, 'b'); selectionRow.appendChild(panel.selectionHeading);
    panel.removeSelection = iconButton(doc, '移除选文', 'm6 6 12 12M18 6 6 18'); selectionRow.appendChild(panel.removeSelection); panel.selectionBox.appendChild(selectionRow);
    panel.selectionText = element(doc, 'p'); panel.selectionBox.appendChild(panel.selectionText); controls.appendChild(panel.selectionBox);
    panel.question = element(doc, 'textarea', undefined, 'kinbo-question'); panel.question.placeholder = '向这篇论文提问…'; panel.question.setAttribute('aria-label', '论文问题');
    controls.appendChild(field(doc, '论文问题', panel.question));
    const actions = element(doc, 'div', undefined, 'kinbo-chat-actions'); panel.networkLabel = element(doc, 'label', undefined, 'kinbo-chat-network');
    panel.network = element(doc, 'input'); panel.network.type = 'checkbox'; panel.networkLabel.appendChild(panel.network); panel.networkLabel.appendChild(doc.createTextNode('联网搜索'));
    actions.appendChild(panel.networkLabel); panel.send = element(doc, 'button', '发送', 'kinbo-send'); actions.appendChild(panel.send);
    panel.cancel = element(doc, 'button', '停止生成'); actions.appendChild(panel.cancel); controls.appendChild(actions);
    controls.appendChild(element(doc, 'span', 'Ctrl / ⌘ + Enter 发送', 'kinbo-chat-shortcut'));
    panel.settings = element(doc, 'details', undefined, 'kinbo-chat-settings'); panel.settingsSummary = element(doc, 'summary', '模型与设置'); panel.settings.appendChild(panel.settingsSummary); controls.appendChild(panel.settings);
    panel.mode = element(doc, 'select'); panel.mode.setAttribute('aria-label', '模型接入方式'); panel.settings.appendChild(field(doc, '接入方式', panel.mode));
    panel.login = element(doc, 'button', '登录 Codex'); panel.settings.appendChild(panel.login); panel.loginDetails = element(doc, 'div'); panel.settings.appendChild(panel.loginDetails);
    panel.provider = element(doc, 'select'); panel.provider.setAttribute('aria-label', '翻译 API'); panel.providerField = field(doc, '已有翻译 API', panel.provider); panel.settings.appendChild(panel.providerField);
    panel.model = element(doc, 'input'); panel.model.placeholder = '模型名称'; panel.model.setAttribute('aria-label', '模型名称'); panel.settings.appendChild(field(doc, '模型', panel.model));
    panel.modelList = element(doc, 'datalist'); panel.modelList.id = 'kinbo-models-' + Math.random().toString(36).slice(2); panel.model.setAttribute('list', panel.modelList.id); panel.settings.appendChild(panel.modelList);
    panel.effort = element(doc, 'select'); panel.effort.setAttribute('aria-label', '思考强度'); panel.settings.appendChild(field(doc, '思考强度', panel.effort));
    panel.customPrompt = element(doc, 'textarea'); panel.customPrompt.placeholder = '例如：用中文回答，并标明证据页码'; panel.customPrompt.setAttribute('aria-label', '自定义回答要求'); panel.settings.appendChild(field(doc, '回答要求', panel.customPrompt));
    panel.settings.appendChild(element(doc, 'p', 'PDF 文字会随提问交给所选服务。扫描页和图片内部内容需要先做 OCR。联网搜索仅供 Codex 使用。'));
    panel.retry = element(doc, 'button', '重新连接'); panel.retry.hidden = true; controls.appendChild(panel.retry);
    panel.status = element(doc, 'div', '正在连接本地服务', 'kinbo-chat-status'); panel.status.setAttribute('role', 'status'); aside.appendChild(panel.status);
    setBusy(panel, false); return panel;
  }
  function watchTheme(panel) {
    const root = panel.doc.documentElement, media = panel.win.matchMedia?.('(prefers-color-scheme: dark)');
    const update = () => {
      const explicit = root?.getAttribute('data-theme') || root?.getAttribute('data-color-scheme') || root?.style.colorScheme;
      panel.aside.setAttribute('data-theme', ['dark', 'light'].includes(explicit) ? explicit : media?.matches ? 'dark' : 'light');
    };
    update(); media?.addEventListener?.('change', update);
    const observer = panel.win.MutationObserver && root ? new panel.win.MutationObserver(update) : null;
    observer?.observe(root, { attributes: true, attributeFilter: ['data-theme', 'data-color-scheme', 'style'] });
    return () => { media?.removeEventListener?.('change', update); observer?.disconnect(); };
  }
  return { element, selectOptions, citation, renderText, renderSession, setBusy, selection, modelSummary, create, watchTheme };
})();
