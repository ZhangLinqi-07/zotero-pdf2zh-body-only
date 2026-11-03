/* SPDX-License-Identifier: AGPL-3.0-only
 * Compatibility boundary for Zotero Reader internals. Not a stable Reader API. */
var KinboChatReader = (() => {
  function fail(message) { const error = new Error(message); error.kinboSafe = true; return error; }
  function element(doc, tag) { return doc.createElementNS('http://www.w3.org/1999/xhtml', tag); }
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
  function clearHighlights(panel) {
    for (const node of panel.highlights) node.remove();
    panel.highlights.length = 0;
    if (panel.highlightTimer) panel.win.clearTimeout(panel.highlightTimer);
    panel.highlightTimer = null;
  }
  async function navigate(panel, target) {
    const { pdf } = readerView(panel.reader);
    if (target.page > pdf.numPages) throw fail('该引用页码超出 PDF 范围');
    clearHighlights(panel);
    const data = target.quote ? await pageContent(panel.reader, target.page) : { chars: [] };
    if (panel.closed) return false;
    const rects = quoteRects(data.chars, target.quote);
    await panel.reader.navigate(rects.length ? { position: { pageIndex: target.page - 1, rects } } : { pageIndex: target.page - 1 });
    if (!rects.length) return false;
    if (panel.closed) return false;
    const { app, win } = readerView(panel.reader);
    const pageView = app.pdfViewer?.getPageView(target.page - 1);
    if (!pageView?.div || !pageView.viewport?.convertToViewportRectangle) return true;
    for (const rect of rects) {
      const [x1, y1, x2, y2] = pageView.viewport.convertToViewportRectangle(inRealm(rect, win));
      const mark = element(pageView.div.ownerDocument, 'div');
      mark.setAttribute('data-kinbo-quote', 'true');
      mark.style.cssText = `position:absolute;pointer-events:none;z-index:8;background:rgba(255,199,42,.45);left:${Math.min(x1,x2)}px;top:${Math.min(y1,y2)}px;width:${Math.abs(x2-x1)}px;height:${Math.abs(y2-y1)}px;`;
      pageView.div.appendChild(mark); panel.highlights.push(mark);
    }
    panel.highlightTimer = panel.win.setTimeout(() => clearHighlights(panel), 5000);
    return true;
  }
  function mountInfo(reader) {
    const frame = reader?._iframe, host = frame?.parentElement;
    if (!host) return null;
    const doc = host.ownerDocument;
    return { reader, frame, host, doc, win: doc.defaultView, hostStyle: host.style.cssText, frameStyle: frame.style.cssText, returnFocus: doc.activeElement };
  }
  function mount(panel) {
    panel.host.style.display = 'flex'; panel.host.style.flexDirection = 'row'; panel.host.style.minWidth = '0';
    panel.frame.style.flex = '1 1 0'; panel.frame.style.minWidth = '0';
  }
  function place(panel, side) {
    panel.aside.setAttribute('data-side', side);
    if (side === 'left') panel.host.insertBefore(panel.aside, panel.frame);
    else panel.host.appendChild(panel.aside);
  }
  function restore(panel) { panel.host.style.cssText = panel.hostStyle; panel.frame.style.cssText = panel.frameStyle; }
  function toolbarDocument(reader) { return reader?._iframeWindow?.document || reader?._iframe?.contentDocument; }
  function ownerWindow(reader) { return reader?._iframe?.ownerDocument?.defaultView || Zotero.getMainWindow?.(); }
  function isAttached(reader) { return reader?._iframe?.isConnected !== false; }
  function isPDF(reader) { return !!reader && (!reader._type || reader._type === 'pdf'); }
  function allReaders() { return Zotero.Reader?._readers || []; }
  async function ready(reader) { if (reader?._initPromise) await reader._initPromise; }
  function onUnload(panel, close) {
    const windows = new Set([panel.win, panel.reader?._iframeWindow]);
    for (const win of windows) win?.addEventListener?.('unload', close);
    return () => { for (const win of windows) win?.removeEventListener?.('unload', close); };
  }
  function isNodeConnected(node) { try { return node.isConnected !== false; } catch (_) { return false; } }
  function releaseButton(button, handler) {
    // A closed Reader window leaves Gecko dead wrappers in the toolbar registry.
    // Its DOM is already gone; release the registry without interrupting shutdown.
    try { button.removeEventListener('click', handler); button.remove(); } catch (_) {}
  }
  return { readerView, extractPages, quoteRects, navigate, clearHighlights, mountInfo, mount, place, restore,
    toolbarDocument, ownerWindow, isAttached, isPDF, allReaders, ready, onUnload, isNodeConnected, releaseButton };
})();
