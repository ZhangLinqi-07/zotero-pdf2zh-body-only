#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Reproducibly add the readable body-only bridge to the pinned upstream XPI."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import urllib.parse

ROOT = Path(__file__).resolve().parent
PLUGIN_VERSION = '4.1.7.10'
DEVELOPMENT_VERSION = '4.1.7.11pre2'
UPDATE_URL = 'https://raw.githubusercontent.com/ZhangLinqi-07/zotero-pdf2zh-body-only/main/updates.json'
MAX_ZOTERO_VERSION = '10.0.*'


def build(source, destination, server_url=None, development=False):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('Choose a different output path for the enhanced XPI')
    manifest = json.loads((ROOT / 'downloads.json').read_text(encoding='utf-8'))
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest['plugin']['sha256']:
        raise ValueError('Build requires the unmodified upstream Zotero PDF2zh 4.1.7 XPI')
    with zipfile.ZipFile(source) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if not name.endswith('/')}
    metadata = json.loads(files['manifest.json'])
    metadata.update(name='Zotero PDF2zh Body Only', version=DEVELOPMENT_VERSION if development else PLUGIN_VERSION,
                    description='PDF translation, shared-API structured reading, formula protection and full-page bilingual layout.',
                    homepage_url='https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only')
    metadata['applications']['zotero'].update(update_url=UPDATE_URL, strict_max_version=MAX_ZOTERO_VERSION)
    files['manifest.json'] = json.dumps(metadata, ensure_ascii=False, indent=2).encode('utf-8')
    bootstrap = files['bootstrap.js'].decode('utf-8')
    bootstrap = bootstrap.replace('var chromeHandle;', 'var chromeHandle;\nvar bodyOnlyBridge;')
    original = '    Zotero.pdf2zh.hooks.onStartup();'
    if bootstrap.count(original) != 1:
        raise ValueError('Unsupported upstream bootstrap entry')
    bootstrap = bootstrap.replace(original,
        '    const bodyOnlyReady = Zotero.pdf2zh.hooks.onStartup();\n'
        '    Promise.resolve(bodyOnlyReady).then(() => {\n'
        '    const bridgeContext = { Zotero, Services, BodyOnlyRootURI: rootURI, IOUtils: typeof IOUtils !== "undefined" ? IOUtils : Zotero.getMainWindow()?.IOUtils };\n'
        '    Services.scriptloader.loadSubScript(`${rootURI}content/scripts/body-only.js`, bridgeContext);\n'
        '    bodyOnlyBridge = bridgeContext.BodyOnlyBridge;\n    bodyOnlyBridge.start();\n'
        '    }).catch(() => Zotero.logError(new Error("PDF2zh Body Only bridge initialization failed")));')
    if server_url:
        parsed = urllib.parse.urlsplit(server_url)
        if parsed.scheme not in {'http', 'https'} or parsed.hostname not in {'localhost', '127.0.0.1', '::1'} or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('A local build override must point to a loopback service')
        bootstrap = bootstrap.replace('    bodyOnlyBridge = bridgeContext.BodyOnlyBridge;',
            '    bridgeContext.BodyOnlyLocalServer = ' + json.dumps(server_url.rstrip('/')) + ';\n    bodyOnlyBridge = bridgeContext.BodyOnlyBridge;')
    bootstrap = bootstrap.replace('    Zotero.pdf2zh?.hooks.onMainWindowLoad(window);',
        '    await Zotero.pdf2zh?.hooks.onMainWindowLoad(window);\n    bodyOnlyBridge?.addWindow(window);')
    bootstrap = bootstrap.replace('    Zotero.pdf2zh?.hooks.onMainWindowUnload(window);',
        '    bodyOnlyBridge?.removeWindow(window);\n    Zotero.pdf2zh?.hooks.onMainWindowUnload(window);')
    bootstrap = bootstrap.replace('    Zotero.pdf2zh?.hooks.onShutdown();',
        '    bodyOnlyBridge?.stop();\n    Zotero.pdf2zh?.hooks.onShutdown();')
    files['bootstrap.js'] = ('// Body-only modifications by ZhangLinqi-07, 2026-10-21. SPDX-License-Identifier: AGPL-3.0-only\n' + bootstrap).encode('utf-8')
    files['prefs.js'] = files['prefs.js'].replace(b'http://localhost:8890', b'http://127.0.0.1:8891')
    files['content/scripts/body-only.js'] = (ROOT / 'plugin/body_only_bridge.js').read_bytes()
    files['content/scripts/body-only-note.js'] = (ROOT / 'plugin/reading_note.js').read_bytes()
    files['content/scripts/kinbo-paper-chat.js'] = (ROOT / 'plugin/paper_chat.js').read_bytes()
    for source, target in [('marked.js', 'body-only-marked.js'), ('purify.js', 'body-only-purify.js')]:
        files['content/scripts/' + target] = (ROOT / 'payload/web/vendor' / source).read_bytes()
    for license in (ROOT / 'payload/web/vendor').glob('*LICENSE*'):
        files['licenses/' + license.name] = license.read_bytes()
    files['LICENSE.body-only'] = (ROOT / 'LICENSE').read_bytes()
    files['NOTICE.body-only.md'] = (ROOT / 'NOTICE.md').read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 21, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, files[name])
    return {'file': destination.name, 'version': metadata['version'], 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-xpi', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--server-url', help='Optional, once-only server preference migration for a local installation')
    parser.add_argument('--development', action='store_true', help='Build the unreleased integration version without changing the published update channel')
    options = parser.parse_args()
    print(json.dumps(build(options.upstream_xpi, options.output, options.server_url, options.development)))
