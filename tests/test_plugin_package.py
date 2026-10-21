# SPDX-License-Identifier: AGPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_plugin
from scripts.build_update_manifest import make_update


class PluginPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upstream = self.root / 'upstream.xpi'
        metadata = {'manifest_version': 2, 'version': '4.1.7', 'applications': {'zotero': {
            'id': 'pdf2zh@guaguastandup.com', 'update_url': 'https://upstream.invalid/updates.json',
            'strict_min_version': '6.999', 'strict_max_version': '10.*'}}}
        with zipfile.ZipFile(self.upstream, 'w') as archive:
            archive.writestr('manifest.json', json.dumps(metadata))
            archive.writestr('bootstrap.js', 'var chromeHandle;\nasync function startup() {\n    Zotero.pdf2zh.hooks.onStartup();\n}\n')
            archive.writestr('prefs.js', 'pref("server", "http://localhost:8890");')
        (self.root / 'downloads.json').write_text(json.dumps({'plugin': {'sha256': hashlib.sha256(self.upstream.read_bytes()).hexdigest()}}))
        for name in ('plugin/body_only_bridge.js', 'plugin/reading_note.js',
                     'payload/web/vendor/marked.js', 'payload/web/vendor/purify.js', 'LICENSE', 'NOTICE.md'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('/* Public build fixture */')
        self.public = self.root / 'public.xpi'

    def build(self, output=None, server_url=None):
        with patch.object(build_plugin, 'ROOT', self.root):
            return build_plugin.build(self.upstream, output or self.public, server_url)

    def test_public_package_contains_required_zotero10_fields_and_own_update_channel(self):
        self.build()
        with zipfile.ZipFile(self.public) as archive:
            metadata = json.loads(archive.read('manifest.json'))
            bootstrap = archive.read('bootstrap.js')
        app = metadata['applications']['zotero']
        self.assertEqual(app['id'], 'pdf2zh@guaguastandup.com')
        self.assertEqual(app['update_url'], build_plugin.UPDATE_URL)
        self.assertEqual(app['strict_max_version'], '10.0.*')
        self.assertEqual(app['strict_min_version'], '6.999')
        self.assertEqual(metadata['version'], build_plugin.PLUGIN_VERSION)
        self.assertNotIn(b'BodyOnlyLocalServer =', bootstrap)
        self.build(self.root / 'repeat.xpi')
        self.assertEqual(self.public.read_bytes(), (self.root / 'repeat.xpi').read_bytes())

    def test_update_manifest_matches_the_built_xpi_hash_and_compatibility(self):
        self.build()
        update = make_update(self.public, 'v0.3.5')['addons']['pdf2zh@guaguastandup.com']['updates'][0]
        self.assertEqual(update['version'], build_plugin.PLUGIN_VERSION)
        self.assertEqual(update['update_hash'], 'sha256:' + hashlib.sha256(self.public.read_bytes()).hexdigest())
        self.assertEqual(update['update_link'], 'https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/releases/download/v0.3.5/zotero-pdf2zh-body-only-v0.3.5.xpi')
        self.assertEqual(update['applications']['zotero']['strict_max_version'], '10.0.*')

    def test_local_build_cannot_accidentally_be_published_as_an_update(self):
        # Supply the normal bridge hook so the build's once-only local override
        # is present in this fixture, just as in the real upstream bootstrap.
        self.build(server_url='http://127.0.0.1:8893')
        with self.assertRaisesRegex(ValueError, 'local server'):
            make_update(self.public, 'v0.3.5')

    def test_shipped_update_document_uses_the_current_plugin_version(self):
        data = json.loads((ROOT / 'updates.json').read_text(encoding='utf-8'))
        update = data['addons']['pdf2zh@guaguastandup.com']['updates'][0]
        self.assertEqual(update['version'], build_plugin.PLUGIN_VERSION)
        self.assertEqual(update['applications']['zotero']['strict_max_version'], build_plugin.MAX_ZOTERO_VERSION)
        self.assertRegex(update['update_hash'], r'^sha256:[a-f0-9]{64}$')


if __name__ == '__main__':
    unittest.main()
