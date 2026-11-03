/* SPDX-License-Identifier: AGPL-3.0-only. Disposable profile only. */
function install() {}
function uninstall() {}
function shutdown() {}
function startup() {
  let completed = false;
  const finish = async error => {
    if (completed) return;
    completed = true;
    await Zotero.File.putContentsAsync(CHAT_TEST_RESULT, JSON.stringify({
      status: error ? 'failed' : 'passed', nativeColdStartup: !error, userProfileUsed: false,
      error: error ? String(error) : undefined, externalModelCalls: 0,
    }));
    Services.startup.quit(Components.interfaces.nsIAppStartup.eAttemptQuit);
  };
  Zotero.Promise.delay(50000).then(() => finish(new Error('Cold startup did not become ready')));
  Zotero.initializationPromise.then(() => Zotero.uiReadyPromise).then(async () => {
    const document = Zotero.getMainWindow().document;
    for (let index = 0; index < 100; index++) {
      if (document.getElementById('zotero-itemmenu-pdf2zh')?.getAttribute('label') === 'Kinbo' &&
          document.getElementById('kinbo-paper-chat-tools')) {
        if (document.querySelectorAll('[id="zotero-itemmenu-pdf2zh"]').length !== 1) throw new Error('Duplicate cold-start menus');
        await finish(); return;
      }
      await Zotero.Promise.delay(100);
    }
    throw new Error('Cold startup did not inject Kinbo after UI readiness');
  }).catch(finish);
}
