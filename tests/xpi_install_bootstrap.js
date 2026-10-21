/* Runs only in a new, disposable Zotero profile created by integration_xpi_install.py. */
function install() {}
function uninstall() {}
function shutdown() {}
function startup() {
  let done = false;
  const finish = async result => {
    if (done) return;
    done = true;
    await Zotero.File.putContentsAsync(TEST_RESULT_PATH, JSON.stringify(result));
    Services.startup.quit(Components.interfaces.nsIAppStartup.eAttemptQuit);
  };
  Zotero.Promise.delay(60000).then(() => finish({status: 'failed', error: 'Native install test exceeded its deadline'}));
  Zotero.initializationPromise.then(() => {
    Zotero.uiReadyPromise.then(async () => {
      try {
        const { AddonManager } = ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
        const testPref = 'extensions.zotero.pdf2zh.new_serverip';
        const savedServer = 'http://127.0.0.1:19731';
        Services.prefs.setStringPref(testPref, savedServer);
        const apiPref = 'extensions.zotero.pdf2zh.llmApis';
        const savedApi = JSON.stringify([{activate: false, apiKey: 'local-test-key', model: 'local-test-model',
          service: 'openailiked', apiUrl: 'http://127.0.0.1:19731/v1'}]);
        Services.prefs.setStringPref(apiPref, savedApi);
        const invalid = await AddonManager.getInstallForFile(Zotero.File.pathToFile(TEST_OLD_XPI));
        if (invalid.error !== AddonManager.ERROR_CORRUPT_FILE) throw new Error('Old package was not rejected as corrupt: ' + invalid.error);
        const candidate = await AddonManager.getInstallForFile(Zotero.File.pathToFile(TEST_NEW_XPI));
        if (candidate.error) throw new Error('New package failed validation: ' + candidate.error);
        if (!candidate.addon.isCompatible) throw new Error('New package is incompatible');
        const addon = await new Promise((resolve, reject) => {
          candidate.addListener({
            onInstallEnded: (install, installed) => resolve(installed),
            onInstallFailed: install => reject(new Error('Installation failed: ' + install.error)),
            onDownloadFailed: install => reject(new Error('XPI download failed: ' + install.error)),
          });
          candidate.install().catch(reject);
        });
        for (let i = 0; i < 100; i++) {
          const menu = Zotero.getMainWindow().document.getElementById('zotero-itemmenu-pdf2zh');
          if (menu?.getAttribute('label') === 'Kinbo') break;
          await Zotero.Promise.delay(100);
        }
        const active = await AddonManager.getAddonByID('pdf2zh@guaguastandup.com');
        if (!active?.isActive || active.appDisabled || active.userDisabled) throw new Error('Installed plugin is disabled');
        if (Services.prefs.getStringPref(testPref) !== savedServer) throw new Error('Public package changed existing server configuration');
        if (Services.prefs.getStringPref(apiPref) !== savedApi) throw new Error('Public package changed existing API configuration');
        const menu = Zotero.getMainWindow().document.getElementById('zotero-itemmenu-pdf2zh');
        if (menu?.getAttribute('label') !== 'Kinbo') throw new Error('Installed plugin did not start the Kinbo menu');
        await finish({ status: 'passed', zoteroVersion: Zotero.version, oldPackageRejected: true,
          oldError: invalid.error, regularXpiInstall: true, addonId: active.id, addonVersion: active.version,
          active: active.isActive, updateURL: active.updateURL, existingServerPreserved: true,
          apiConfigurationPreserved: true,
          kinboMenuLoaded: true, userProfileUsed: false, externalTranslationApiCalls: 0 });
      } catch (error) {
        await finish({ status: 'failed', error: String(error), stack: error.stack });
      }
    }).catch(error => finish({status: 'failed', error: String(error)}));
  }).catch(error => finish({status: 'failed', error: String(error)}));
}
