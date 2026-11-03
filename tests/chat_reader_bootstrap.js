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
      check(addon.name === 'Kinbo', 'Installed plugin did not use the Kinbo product name');
      report.regularXpiInstall = true; report.addonVersion = addon.version; report.addonName = addon.name; report.zoteroVersion = Zotero.version;
      at('import-synthetic-pdf');
      // uiReadyPromise can resolve before the initial empty-library item load.
      // Creating items during that load races relation hydration on a fresh profile.
      await Zotero.Libraries.get(Zotero.Libraries.userLibraryID).waitForDataLoad('item');
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
      let sessionPages = null, lastMessage = null;
      const session = { id: '1'.repeat(32), busy: false, messages: [{ role: 'assistant', content: 'Synthetic retained history.' }] };
      const facade = Object.create(Zotero);
      facade.HTTP = { request: async (method, url, settings) => {
        check(url.startsWith('http://127.0.0.1:19731/api/paper-chat/'), 'Unexpected test request ' + url);
        report.mockSessionRequests++;
        let body;
        if (url.endsWith('/config')) body = { status: 'success', active: 'fixture',
          profiles: [{ id: 'fixture', label: 'Local mock', model: 'synthetic-model' }], codex: { available: false, authenticated: false } };
        else if (url.endsWith('/sessions') && method === 'POST') {
          sessionPages = JSON.parse(settings.body).pages;
          body = { status: 'success', session: { ...session, messages: [...session.messages] } };
        } else if (url.endsWith('/messages') && method === 'POST') {
          lastMessage = JSON.parse(settings.body); session.messages.push({ role: 'user', content: lastMessage.question }); session.busy = true;
          body = { status: 'success', session: { ...session, messages: [...session.messages] } };
        } else if (url.endsWith('/cancel')) {
          session.busy = false; body = { status: 'success', session: { ...session, messages: [...session.messages] } };
        } else if (url.endsWith('/models?mode=codex')) {
          body = { status: 'success', models: [{ id: 'native-synthetic-model', isDefault: true, supportedReasoningEfforts: [{ reasoningEffort: 'high' }] }] };
        } else if (url.endsWith('/sessions/' + session.id)) {
          body = { status: 'success', session: { ...session, messages: [...session.messages] } };
        } else throw new Error('No model or external request is allowed in the native reader test');
        return { status: 200, response: body };
      } };
      const scope = { Zotero: facade, Services, Components, ChromeUtils };
      for (const source of CHAT_TEST_SOURCES) Services.scriptloader.loadSubScript(Services.io.newFileURI(Zotero.File.pathToFile(source)).spec, scope);
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
      await waitFor(() => reader._iframeWindow.document.querySelector('[data-kinbo-chat-toggle]'), 'Existing native reader has no Kinbo toolbar entry');
      report.nativeToolbarEntry = true;
      check(Zotero.getMainWindow().document.getElementById('kinbo-paper-chat-tools'), 'The persistent Tools menu entry is missing');
      const mainWindow = Zotero.getMainWindow(), readingMenu = mainWindow.document.getElementById('pdf2zh-body-only-reading');
      check(readingMenu, 'The library deep-reading entry is missing');
      check(!mainWindow.document.getElementById('pdf2zh-body-only-chat') && !mainWindow.document.getElementById('pdf2zh-body-only-stop-reading'), 'Redundant context menu actions remain');
      const readingPopup = readingMenu.parentNode;
      for (const id of ['pdf2zh-body-only-model', 'kinbo-backend-update']) {
        const menu = mainWindow.document.getElementById(id);
        check(menu?.parentNode?.id === 'menu_ToolsPopup', 'Management action was not preserved in Tools: ' + id);
        check(menu.getAttribute('image')?.endsWith('.svg'), 'Management menu icon is missing: ' + id);
      }
      check(readingMenu.getAttribute('image')?.endsWith('kinbo-read.svg'), 'Reading icon is missing');
      const originalHTTP = Zotero.HTTP.request;
      let readingRunning = false, readingStarted = false, readingCancelled = false;
      Zotero.HTTP.request = async (method, url, settings) => {
        if (url === 'http://127.0.0.1:19731/api/capabilities') return { response: { zoteroNotes: true, pdfReading: true, readingSearch: true, fullPageImageReading: true } };
        if (url === 'http://127.0.0.1:19731/api/reading/config') return { response: { options: { backend: 'codex' } } };
        if (url === 'http://127.0.0.1:19731/api/reading/documents') return { status: 200, response: { status: 'success', document: { id: 'synthetic-document' } } };
        if (url === 'http://127.0.0.1:19731/api/reading/jobs' && method === 'POST') {
          readingStarted = true; readingRunning = true;
          return { status: 200, response: { status: 'success', job: { id: 'synthetic-reading', progress: 0 } } };
        }
        if (url === 'http://127.0.0.1:19731/api/reading/jobs') return { response: { jobs: readingRunning ? [{ id: 'synthetic-reading', state: 'running', zoteroTarget: {
          clientID: Zotero.Prefs.get('extensions.zotero.pdf2zh.bodyOnlyNoteClient', true), attachmentKey: attachment.key,
        } }] : [] } };
        if (url === 'http://127.0.0.1:19731/api/reading/jobs/synthetic-reading/cancel') {
          readingCancelled = true; readingRunning = false; return { status: 200, response: { status: 'success' } };
        }
        return originalHTTP.call(Zotero.HTTP, method, url, settings);
      };
      try {
        readingPopup.dispatchEvent(new mainWindow.Event('popupshowing', { bubbles: true }));
        await waitFor(() => readingMenu.getAttribute('label') === '深度阅读', 'Idle reading entry has an incorrect label');
        readingMenu.dispatchEvent(new mainWindow.Event('command', { bubbles: true }));
        await waitFor(() => readingStarted, 'Single reading action did not start the mock reading job');
        await waitFor(() => readingMenu.getAttribute('label') === '停止阅读', 'Running reading was not reflected in the single menu entry');
        check(readingMenu.getAttribute('image').endsWith('kinbo-stop.svg'), 'Stop icon did not replace the reading icon');
        readingMenu.dispatchEvent(new mainWindow.Event('command', { bubbles: true }));
        await waitFor(() => readingCancelled && readingMenu.getAttribute('label') === '深度阅读', 'Single reading action did not cancel and restore its label');
        check(readingMenu.getAttribute('image').endsWith('kinbo-read.svg'), 'Reading icon was not restored');
        report.nativeReadingMenuStart = true; report.nativeReadingMenuToggle = true;
      } finally { Zotero.HTTP.request = originalHTTP; }
      report.nativeMenuEntries = true;
      const host = reader._iframe.parentElement, hostStyle = host.style.cssText, frameStyle = reader._iframe.style.cssText;
      const panel = await chat.open(reader, { text: quote, page: 2 });
      check(panel && !panel.closed && host.contains(panel.aside), 'Native reader sidebar was not attached');
      check(panel.session?.id === '1'.repeat(32), 'Sidebar did not establish the local mock session');
      check(sessionPages?.length === 2 && sessionPages[1].text.includes('KINBO_FINAL_PAGE_SENTINEL'), 'Sidebar session did not receive full pages');
      check(panel.selectionText.textContent.includes(quote), 'Selection context did not appear in native DOM');
      report.nativeSidebar = true; report.selectionContext = true;
      check(panel.messages.textContent.includes('Synthetic retained history.'), 'Existing history was not rendered');
      report.historyRendered = true;
      at('native-theme-and-layout');
      // Hidden automation windows do not reliably advance compositor transitions.
      // Capture stable state colors, as reduced-motion users would see them.
      panel.aside.style.setProperty('--kinbo-duration', '0ms');
      const root = panel.doc.documentElement;
      const previousTheme = root.getAttribute('data-theme');
      root.setAttribute('data-theme', 'light');
      await waitFor(() => panel.aside.getAttribute('data-theme') === 'light', 'Native light theme was not applied');
      report.lightBackground = panel.win.getComputedStyle(panel.aside).backgroundColor;
      const questionStyle = panel.win.getComputedStyle(panel.question);
      report.lightQuestion = { background: questionStyle.backgroundColor, border: questionStyle.borderColor, appearance: questionStyle.appearance };
      root.setAttribute('data-theme', 'dark');
      await waitFor(() => panel.aside.getAttribute('data-theme') === 'dark', 'Native dark theme did not update');
      report.darkBackground = panel.win.getComputedStyle(panel.aside).backgroundColor;
      const darkQuestionStyle = panel.win.getComputedStyle(panel.question);
      report.darkQuestion = { background: darkQuestionStyle.backgroundColor, border: darkQuestionStyle.borderColor, appearance: darkQuestionStyle.appearance };
      // Flush style, then settle Kinbo's 150ms control color feedback before
      // comparing colors or capturing; the mutation observer alone isn't paint.
      await Zotero.Promise.delay(200);
      report.darkIconColor = panel.win.getComputedStyle(panel.removeSelection).color;
      check(report.lightBackground !== report.darkBackground, 'Light and dark tokens resolved to the same background');
      check(report.lightQuestion.background === 'rgb(255, 255, 255)' && report.darkQuestion.background === 'rgb(38, 42, 47)',
        'Zotero chrome styles overrode the Kinbo input surface tokens');
      check(report.darkIconColor === panel.win.getComputedStyle(panel.aside).color, 'Native icon button color did not follow the active theme');
      report.nativeThemes = true;
      const capture = async name => {
        const canvas = panel.doc.createElementNS('http://www.w3.org/1999/xhtml', 'canvas');
        canvas.width = panel.win.innerWidth; canvas.height = panel.win.innerHeight;
        canvas.getContext('2d').drawWindow(panel.win, 0, 0, canvas.width, canvas.height, 'rgb(32,35,39)');
        const file = Zotero.File.pathToFile(CHAT_TEST_OUTPUT_DIR); file.append(name + '.png.b64');
        await Zotero.File.putContentsAsync(file.path, canvas.toDataURL('image/png').split(',')[1]);
      };
      await capture('native-dark');
      root.setAttribute('data-theme', 'light');
      await waitFor(() => panel.aside.getAttribute('data-theme') === 'light', 'Native light theme restoration failed');
      panel.win.getComputedStyle(panel.aside).backgroundColor;
      await Zotero.Promise.delay(200);
      await capture('native-light');
      if (previousTheme === null) root.removeAttribute('data-theme'); else root.setAttribute('data-theme', previousTheme);
      const box = panel.aside.getBoundingClientRect();
      report.sidebarWidth = box.width;
      check(box.width <= 337 && box.width > 100, 'Native sidebar did not respect compact width');
      check(panel.aside.scrollWidth <= box.width + 1, 'Native sidebar overflowed horizontally');
      report.nativeCompactLayout = true;
      at('native-selection-send-and-cancel');
      panel.question.value = 'Explain this selected sentence'; panel.send.click();
      await waitFor(() => panel.busy, 'Native question did not start the mock generation');
      check(lastMessage?.selection?.text === quote && lastMessage.selection.page === 2, 'Native selection protocol changed');
      check(panel.cancel.hidden === false && panel.send.hidden, 'Generating state did not expose Stop');
      panel.cancel.click(); await waitFor(() => !panel.busy, 'Native cancellation failed');
      report.nativeSelectionSend = true; report.nativeCancel = true;
      panel.mode.value = 'codex'; panel.mode.dispatchEvent(new panel.win.Event('change', { bubbles: true }));
      await waitFor(() => panel.model.value === 'native-synthetic-model', 'Native model selection failed');
      report.nativeModelSelection = true;
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
      at('native-reopen-and-window-switch');
      const restored = await chat.open(reader);
      check(restored.messages.textContent.includes('Explain this selected sentence'), 'Reopened sidebar lost history');
      report.nativeHistoryRestored = true;
      const otherReader = await Zotero.Reader.open(attachment.id, null, { openInWindow: true, allowDuplicate: true });
      await waitFor(() => otherReader._internalReader?._primaryView?._iframeWindow?.PDFViewerApplication?.pdfDocument,
        'Detached native reader did not initialize', 120);
      const otherPanel = await chat.open(otherReader);
      check(otherPanel && otherPanel.win !== restored.win, 'Detached Reader did not receive its own sidebar');
      otherPanel.win.focus(); restored.win.focus();
      check(!otherPanel.closed && !restored.closed, 'Switching native windows closed a conversation');
      otherReader.close();
      await waitFor(() => otherPanel.closed, 'Reader window close did not dispose its panel');
      await waitFor(() => !Zotero.Reader._readers.includes(otherReader), 'Closed Reader remained in the native registry');
      check(!restored.closed, 'Closing one Reader window closed the other panel');
      report.nativeWindowSwitch = true;
      chat.stop(); check(restored.closed && !host.contains(restored.aside), 'Stop left a sidebar in the native DOM');
      at('native-disable-and-uninstall');
      await addon.disable();
      await waitFor(() => !reader._iframeWindow.document.querySelector('[data-kinbo-chat-toggle]'), 'Disabling left native toolbar injection behind');
      check(!Zotero.getMainWindow().document.getElementById('kinbo-paper-chat-tools'), 'Disabling left Tools menu injection behind');
      check(!host.querySelector('*|aside.kinbo-paper-chat'), 'Disabling left a sidebar behind');
      await addon.uninstall(); report.nativeDisableCleanup = true; report.nativeUninstall = true;
      at('complete');
      await finish();
    } catch (error) { await finish(error); }
  }).catch(error => finish(error));
}
