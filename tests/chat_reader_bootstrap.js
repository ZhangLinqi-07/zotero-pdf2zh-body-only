/* SPDX-License-Identifier: AGPL-3.0-only
 * Runs only inside the disposable profile from integration_chat_reader.py. */
function install() {}
function uninstall() {}
function shutdown() {}
function startup() {
  let completed = false, stage = 'startup', chat = null;
  const report = { status: 'running', userProfileUsed: false, actualReader: false,
    actualPDFDocument: false, chatSource: 'packaged-xpi', xpiSHA256: CHAT_TEST_XPI_HASH,
    externalModelCalls: 0, mockSessionRequests: 0 };
  const at = name => { stage = name; Zotero.debug('KINBO_CHAT_STAGE ' + name); };
  const finish = async error => {
    if (completed) return;
    completed = true;
    try { chat?.stop(); } catch (_) {}
    report.status = error ? 'failed' : 'passed';
    report.stage = stage;
    if (error) { report.error = String(error); report.stack = error.stack; }
    await Zotero.File.putContentsAsync(CHAT_TEST_RESULT, JSON.stringify(report, null, 2));
    Services.startup.quit(Components.interfaces.nsIAppStartup.eAttemptQuit);
  };
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const waitFor = async (test, message, maximum = 100) => {
    for (let index = 0; index < maximum; index++) {
      if (test()) return;
      await Zotero.Promise.delay(100);
    }
    throw new Error(message);
  };
  Zotero.Promise.delay(75000).then(() => finish(new Error('Native reader harness exceeded 75 seconds at ' + stage)));
  Zotero.initializationPromise.then(() => Zotero.uiReadyPromise).then(async () => {
    try {
      at('install-xpi');
      const { AddonManager } = ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
      const candidate = await AddonManager.getInstallForFile(Zotero.File.pathToFile(CHAT_TEST_XPI));
      check(!candidate.error, 'Preview XPI validation failed ' + candidate.error);
      await new Promise((resolve, reject) => {
        candidate.addListener({ onInstallEnded: (_, addon) => resolve(addon),
          onInstallFailed: install => reject(new Error('Install failed ' + install.error)),
          onDownloadFailed: install => reject(new Error('Download failed ' + install.error)) });
        candidate.install().catch(reject);
      });
      const addon = await AddonManager.getAddonByID('pdf2zh@guaguastandup.com');
      check(addon?.isActive && !addon.appDisabled && !addon.userDisabled, 'Preview XPI is disabled');
      report.regularXpiInstall = true; report.addonVersion = addon.version; report.zoteroVersion = Zotero.version;
      at('import-synthetic-pdf');
      const parent = new Zotero.Item('journalArticle');
      parent.libraryID = Zotero.Libraries.userLibraryID;
      parent.setField('title', 'Kinbo isolated synthetic reader fixture');
      await parent.saveTx();
      const attachment = await Zotero.Attachments.importFromFile({ file: Zotero.File.pathToFile(CHAT_TEST_PDF), parentItemID: parent.id });
      at('open-native-reader');
      const reader = await Zotero.Reader.open(attachment.id);
      check(reader, 'Zotero.Reader.open did not return a reader');
      report.actualReader = true;
      at('wait-native-pdf-document');
      await waitFor(() => reader._internalReader?._primaryView?._iframeWindow?.PDFViewerApplication?.pdfDocument,
        'Native PDF.js did not become ready', 150);
      const pdfWindow = reader._internalReader._primaryView._iframeWindow;
      const pdf = pdfWindow.PDFViewerApplication.pdfDocument;
      report.actualPDFDocument = true;
      report.nativePageCount = pdf.numPages;
      at('load-chat-source');
      let sessionPages = null;
      const facade = Object.create(Zotero);
      facade.HTTP = { request: async (method, url, settings) => {
        check(url.startsWith('http://127.0.0.1:19731/api/paper-chat/'), 'Unexpected test request ' + url);
        report.mockSessionRequests++;
        let body;
        if (url.endsWith('/config')) body = { status: 'success', active: 'fixture',
          profiles: [{ id: 'fixture', label: 'Local mock', model: 'synthetic-model' }], codex: { available: false, authenticated: false } };
        else if (url.endsWith('/sessions') && method === 'POST') {
          sessionPages = JSON.parse(settings.body).pages;
          body = { status: 'success', session: { id: '1'.repeat(32), busy: false, messages: [] } };
        } else throw new Error('No model or external request is allowed in the native reader test');
        return { status: 200, response: body };
      } };
      const scope = { Zotero: facade, Services, Components, ChromeUtils };
      Services.scriptloader.loadSubScript(Services.io.newFileURI(Zotero.File.pathToFile(CHAT_TEST_SOURCE)).spec, scope);
      chat = scope.KinboPaperChat;
      check(chat?._test?.extractPages, 'Paper chat helper API is unavailable');
      at('extract-real-pdf-pages');
      const pages = await chat._test.extractPages(reader);
      check(pages.length === 2, 'Full PDF page extraction omitted a page');
      check(pages[0].text.includes('KINBO_FIRST_PAGE_SENTINEL'), 'First PDF page marker is missing');
      check(pages[1].text.includes('KINBO_FINAL_PAGE_SENTINEL'), 'Final PDF page marker is missing');
      report.fullPageExtraction = true;
      report.pageTextLengths = pages.map(page => page.text.length);
      at('match-real-pdf-quote');
      check(typeof pdf.getPageData === 'function', 'Native PDF document does not expose getPageData for accurate highlights');
      const data = await pdf.getPageData(Components.utils.cloneInto({ pageIndex: 1 }, pdfWindow));
      const quote = 'Exact evidence sentence appears here only once.';
      const rects = chat._test.quoteRects(data.chars, quote);
      check(rects.length > 0, 'Accurate quotation did not match real PDF character rectangles');
      check(chat._test.quoteRects(data.chars, 'A sentence absent from the source.').length === 0, 'Invented quote matched');
      report.accurateQuoteMatch = true; report.matchedCharacterRects = rects.length;
      at('open-native-sidebar');
      chat.start({ baseURL: () => 'http://127.0.0.1:19731', syncAPI: async () => null });
      const host = reader._iframe.parentElement, hostStyle = host.style.cssText, frameStyle = reader._iframe.style.cssText;
      const panel = await chat.open(reader, { text: quote, page: 2 });
      check(panel && !panel.closed && host.contains(panel.aside), 'Native reader sidebar was not attached');
      check(panel.session?.id === '1'.repeat(32), 'Sidebar did not establish the local mock session');
      check(sessionPages?.length === 2 && sessionPages[1].text.includes('KINBO_FINAL_PAGE_SENTINEL'), 'Sidebar session did not receive full pages');
      check(panel.selectionText.textContent.includes(quote), 'Selection context did not appear in native DOM');
      report.nativeSidebar = true; report.selectionContext = true;
      at('switch-sidebar-side');
      const side = panel.side;
      panel.sideButton.click();
      check(panel.side !== side, 'Native side toggle did not change side');
      check(panel.side === 'left' ? host.firstElementChild === panel.aside : host.lastElementChild === panel.aside,
        'Sidebar is not in the requested native DOM position');
      report.sidebarSideSwitch = true;
      at('navigate-and-highlight-real-quote');
      const link = panel.doc.createElementNS('http://www.w3.org/1999/xhtml', 'a');
      link.setAttribute('href', 'kinbo://page/2?quote=' + encodeURIComponent(quote)); link.textContent = 'Exact evidence';
      panel.messages.appendChild(link);
      report.nativeCitationHref = link.getAttribute('href');
      report.nativeCitationParsed = chat._test.citation(link.getAttribute('href'));
      report.nativeClosestAnchor = link.closest('a') === link;
      report.nativeAnchorNamespace = link.namespaceURI;
      let capturedClick = false;
      panel.aside.addEventListener('click', event => {
        event.preventDefault();
        if (event.target?.localName !== 'a') return;
        capturedClick = true;
        report.nativeClickTarget = event.target?.localName;
        report.nativeClickOriginalTarget = event.originalTarget?.localName;
      }, false, true);
      link.dispatchEvent(new panel.win.MouseEvent('click', { bubbles: true, cancelable: true }));
      report.nativeClickCaptured = capturedClick;
      await Zotero.Promise.delay(400);
      report.syntheticCitationActivated = panel.highlights.length > 0;
      if (!panel.highlights.length) {
        at('direct-handler-native-navigation');
        let targetRead = false, defaultPrevented = false;
        check(typeof panel.onLinkClick === 'function', 'The source citation handler is unavailable');
        panel.onLinkClick({ get target() { targetRead = true; return link; }, preventDefault() { defaultPrevented = true; } });
        report.directHandlerReadTarget = targetRead;
        report.directHandlerPreventedDefault = defaultPrevented;
        await chat._test.navigate(panel, { page: 2, quote });
      }
      await waitFor(() => panel.highlights.length > 0, 'Native quote navigation did not create a temporary overlay. ' + panel.status.textContent, 70);
      check(panel.highlights.every(mark => mark.isConnected), 'Quote overlays were not attached to real PDF page DOM');
      report.nativeQuoteNavigation = true; report.temporaryHighlight = true;
      at('close-sidebar-and-cleanup');
      panel.aside.querySelector('*|header *|button:last-child').click();
      check(panel.closed && !host.contains(panel.aside), 'Closing the sidebar did not remove it');
      check(host.style.cssText === hostStyle && reader._iframe.style.cssText === frameStyle, 'Native reader layout styles were not restored');
      check(panel.highlights.length === 0, 'Closing the sidebar left quote highlights behind');
      report.layoutRestored = true; report.highlightCleanup = true;
      check(report.mockSessionRequests === 2, 'Opening and selecting unexpectedly made an extra request');
      at('complete');
      await finish();
    } catch (error) { await finish(error); }
  }).catch(error => finish(error));
}
