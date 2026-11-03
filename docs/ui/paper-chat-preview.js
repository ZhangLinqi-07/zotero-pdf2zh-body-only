/* SPDX-License-Identifier: AGPL-3.0-only */
(() => {
  const $ = id => document.getElementById(id), view = KinboChatView;
  const panel = view.create({ doc: document, win: window, session: null, closed: false });
  const workspace = $('workspace'); workspace.appendChild(panel.aside);
  panel.paperTitle.textContent = 'Evidence before explanation';
  view.selectOptions(panel.mode, [['api', '已有翻译 API'], ['codex', 'Codex 登录']], 'codex');
  view.selectOptions(panel.provider, [['demo', '演示 API · example-model']], 'demo');
  view.selectOptions(panel.effort, [['', '模型默认思考强度'], ['high', '高']], '');
  for (const name of ['example-model', 'example-reasoning']) { const option = document.createElement('option'); option.value = name; panel.modelList.appendChild(option); }
  panel.model.value = 'example-model'; panel.login.hidden = true; panel.providerField.hidden = true;
  const quote = 'Every generated claim should remain connected to its source passage.';
  const messages = [
    { role: 'user', content: '这篇论文如何区分证据和解释？' },
    { role: 'assistant', content: '论文把两者分开：**证据**是可以返回原文核对的陈述；**解释**是在证据之上提出的分析。\n每条判断应保留到来源段落的路径，而不是只给出一个独立的结论。\n[第 2 页 · 查看原句](kinbo://page/2?quote=' + encodeURIComponent(quote) + ')' },
  ];
  let session;
  function show(state) {
    panel.rendered = null; panel.settings.open = state === 'model';
    panel.clearConfirmation.hidden = true;
    view.selection(panel, state === 'selection' ? { page: 2, text: quote } : null);
    panel.question.value = state === 'selection' ? '这句话对实际阅读有什么要求？' : '';
    session = { id: 'preview-only', messages: state === 'empty' ? [] : structuredClone(messages), busy: state === 'generating' };
    if (state === 'generating') session.messages.pop();
    if (state === 'failed') { session.error = '连接中断。已有回答已保留，请检查后台后重新连接。'; session.messages[1].incomplete = true; }
    if (state === 'search') {
      session.messages[1].content += '\n联网证据与 PDF 原文分开列出，只有实际返回来源时才显示来源。';
      session.messages[1].sources = [{ title: '演示来源：Zotero 官方开发文档', url: 'https://www.zotero.org/support/dev/zotero_7_for_developers' }];
      panel.network.checked = true;
    } else panel.network.checked = false;
    view.modelSummary(panel); view.renderSession(panel, session);
    $('evidence').classList.toggle('preview-evidence', state === 'citation');
    if (state === 'citation') panel.status.textContent = '已定位第 2 页原文 · 此处为合成演示';
  }
  $('preview-state').addEventListener('change', event => show(event.target.value));
  $('preview-theme').addEventListener('change', event => { document.documentElement.dataset.theme = event.target.value; panel.aside.dataset.theme = event.target.value; });
  $('preview-narrow').addEventListener('change', event => workspace.classList.toggle('preview-narrow', event.target.checked));
  panel.closeButton.addEventListener('click', () => { panel.aside.hidden = true; $('preview-open').hidden = false; });
  $('preview-open').addEventListener('click', () => { panel.aside.hidden = false; $('preview-open').hidden = true; panel.question.focus(); });
  panel.sideButton.addEventListener('click', () => {
    const left = panel.aside.dataset.side !== 'left'; panel.aside.dataset.side = left ? 'left' : 'right';
    if (left) workspace.prepend(panel.aside); else workspace.append(panel.aside);
    panel.sideButton.setAttribute('aria-label', left ? '移到右侧' : '移到左侧');
  });
  panel.removeSelection.addEventListener('click', () => view.selection(panel, null));
  panel.clear.addEventListener('click', () => { panel.clearConfirmation.hidden = false; panel.cancelClear.focus(); });
  panel.cancelClear.addEventListener('click', () => { panel.clearConfirmation.hidden = true; panel.clear.focus(); });
  panel.confirmClear.addEventListener('click', () => { $('preview-state').value = 'empty'; show('empty'); });
  panel.cancel.addEventListener('click', () => { session.busy = false; session.error = '已停止生成，已有内容保留（演示）'; view.renderSession(panel, session); });
  panel.retry.addEventListener('click', () => { $('preview-state').value = 'normal'; show('normal'); });
  panel.mode.addEventListener('change', () => { const api = panel.mode.value === 'api'; panel.providerField.hidden = !api; panel.model.readOnly = api; panel.network.checked = false; view.setBusy(panel, false); });
  panel.model.addEventListener('change', () => view.modelSummary(panel));
  const send = () => {
    if (panel.busy || !panel.question.value.trim()) return;
    session.messages.push({ role: 'user', content: panel.question.value.trim() }, { role: 'assistant', content: '这是本地交互预览。实际插件会通过原有后台协议回答，并保留原文引用。' });
    panel.question.value = ''; view.selection(panel, null); view.renderSession(panel, session);
  };
  panel.send.addEventListener('click', send);
  panel.question.addEventListener('keydown', event => { if (!event.isComposing && event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); send(); } });
  panel.aside.addEventListener('click', event => {
    const starter = event.target.closest('[data-kinbo-starter]');
    if (starter) { panel.question.value = starter.textContent; panel.question.focus(); }
    const link = event.target.closest('a');
    if (link?.getAttribute('href')?.startsWith('kinbo://')) {
      event.preventDefault(); $('evidence').classList.add('preview-evidence'); panel.status.textContent = '已定位第 2 页原文 · 此处为合成演示';
    }
  });
  show('normal');
})();
