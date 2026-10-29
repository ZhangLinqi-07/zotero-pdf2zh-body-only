# SPDX-License-Identifier: AGPL-3.0-only
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, Mock
import urllib.request
import zipfile

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'payload'))
from utils import kinbo_update_worker as worker
from utils.kinbo_update import KinboUpdater
from scripts.build_backend_bundle import build_bytes
import install
import restore


def pack(files, version='0.4.2', extra=None):
    metadata = {'schema': 1, 'backendVersion': version, 'compatibility': worker.COMPATIBILITY,
                'files': {name: {'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
                          for name, content in files.items()}}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr('kinbo-backend.json', json.dumps(metadata))
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    content = output.getvalue()
    return content, hashlib.sha256(content).hexdigest(), metadata


class BackendUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for path in (ROOT / 'upstream').rglob('*'):
            if path.is_file():
                target = self.root / path.relative_to(ROOT / 'upstream')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        install.install(self.root)
        self.files = {'server.py': b'print("new server")\n', 'run_body_only.py': b'# launcher\n',
                      'utils/kinbo_update.py': b'# updater\n', 'utils/kinbo_update_worker.py': b'# worker\n'}
        self.content, self.sha, self.metadata = pack(self.files)

    def test_real_package_is_deterministic_and_contains_no_runtime_data(self):
        first, info = build_bytes()
        self.assertEqual(first, build_bytes()[0])
        metadata, files = worker.validate_bundle(first, info['sha256'], install.VERSION)
        self.assertEqual(metadata['backendVersion'], install.VERSION)
        self.assertTrue(all(worker.allowed(name) for name in files))
        self.assertFalse(any(name.startswith(('config/', 'reading/', 'translated/')) for name in files))

    def test_checksum_traversal_private_files_and_dependency_changes_are_rejected(self):
        with self.assertRaises(ValueError):
            worker.validate_bundle(self.content, '0' * 64, '0.4.2')
        for name in ('../outside.py', 'config/config.toml', 'reading/private.json', 'utils/../secret.py'):
            content, sha, _ = pack(self.files, extra={name: b'private'})
            with self.assertRaises(ValueError):
                worker.validate_bundle(content, sha, '0.4.2')
        incompatible = dict(self.metadata, compatibility={'upstream_version': '99'})
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('kinbo-backend.json', json.dumps(incompatible))
        content = output.getvalue()
        with self.assertRaisesRegex(ValueError, '依赖'):
            worker.validate_bundle(content, hashlib.sha256(content).hexdigest(), '0.4.2')

    def test_local_edits_prevent_overwrite_and_links_cannot_escape_root(self):
        (self.root / 'server.py').write_bytes(b'# personal modification')
        with self.assertRaisesRegex(ValueError, '本机改动'):
            worker.check_target(self.root, self.files)
        with self.assertRaises(ValueError):
            worker.inside(self.root, '../server.py')

    def test_update_restore_stack_and_personal_data_are_preserved(self):
        private = {'config/config.toml': b'PRIVATE_API', 'translated/private.pdf': b'PRIVATE_PDF',
                   'reading/note.md': b'PRIVATE_NOTE'}
        for name, content in private.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        original = (self.root / 'server.py').read_bytes()
        old_state = (self.root / install.STATE).read_bytes()
        transaction = worker.apply_files(self.root, self.metadata, self.files)
        self.assertEqual((self.root / 'server.py').read_bytes(), self.files['server.py'])
        worker.rollback_files(self.root, transaction)
        self.assertEqual((self.root / install.STATE).read_bytes(), old_state)
        worker.apply_files(self.root, self.metadata, self.files)
        restore.restore(self.root)
        self.assertEqual((self.root / 'server.py').read_bytes(), original)
        self.assertEqual((self.root / install.STATE).read_bytes(), old_state)
        for name, content in private.items():
            self.assertEqual((self.root / name).read_bytes(), content)

    def test_privileged_api_rejects_remote_web_origins_and_bad_tokens(self):
        app = Flask(__name__)
        updater = KinboUpdater(app, self.root, '0.4.1', 8891, lambda: False)
        client = app.test_client()
        headers = {'X-Kinbo-Client': 'zotero'}
        self.assertEqual(client.get('/api/kinbo/update').status_code, 403)
        for extra in ({'Origin': 'https://evil.test'}, {'Host': 'evil.test'}):
            self.assertEqual(client.get('/api/kinbo/update', headers={**headers, **extra}).status_code, 403)
        self.assertEqual(client.get('/api/kinbo/update', headers=headers, environ_base={'REMOTE_ADDR': '192.0.2.1'}).status_code, 403)
        status = client.get('/api/kinbo/update', headers=headers).json
        self.assertEqual(status['token'], updater.token)
        self.assertEqual(client.post('/api/kinbo/update', headers=headers, json={}).status_code, 403)
        headers['X-Kinbo-Update-Token'] = status['token']
        data = {'backendVersion': '0.4.2', 'sha256': self.sha, 'bundle': base64.b64encode(self.content).decode()}
        with patch('utils.kinbo_update.threading.Thread'):
            self.assertEqual(client.post('/api/kinbo/update', headers=headers, json=data).status_code, 202)
            self.assertEqual(client.post('/api/kinbo/update', headers=headers, json=data).status_code, 202)

    def test_idle_gate_blocks_mutations_but_releases_request_counters(self):
        app = Flask(__name__)
        updater = KinboUpdater(app, self.root, '0.4.1', 8891, lambda: False)
        @app.post('/work')
        def work():
            self.assertEqual(updater.inflight, 1)
            return {'ok': True}
        client = app.test_client()
        self.assertEqual(client.post('/work').status_code, 200)
        self.assertEqual(updater.inflight, 0)
        updater.draining = True
        self.assertEqual(client.post('/work').status_code, 503)
        self.assertEqual(updater.inflight, 0)

    def test_worker_rolls_back_if_new_service_fails_health_check(self):
        staging = self.root / '.kinbo-updates/fixture'
        staging.mkdir(parents=True)
        (staging / 'backend.zip').write_bytes(self.content)
        original = (self.root / 'server.py').read_bytes()
        plan = {'root': str(self.root), 'state': str(self.root / '.kinbo-updates/state.json'),
                'version': '0.4.2', 'previousVersion': '0.4.1', 'sha256': self.sha, 'parentPID': 123,
                'port': 8891, 'command': ['python', 'server.py'], 'nonce': 'test'}
        worker.write_json(staging / 'plan.json', plan)
        with patch.object(worker, 'process_alive', return_value=False), patch.object(worker, 'launch') as launch, \
             patch.object(worker, 'healthy', side_effect=[False, True]), patch.object(worker, 'stop_child'):
            worker.run_plan(staging / 'plan.json')
        self.assertEqual(launch.call_count, 2)
        self.assertEqual((self.root / 'server.py').read_bytes(), original)
        self.assertEqual(json.loads((self.root / '.kinbo-updates/state.json').read_text(encoding='utf-8'))['state'], 'rolled_back')

    def test_versions_keep_preview_order(self):
        self.assertLess(worker.version_key('0.4.1pre2'), worker.version_key('0.4.1'))
        self.assertLess(worker.version_key('0.4.1'), worker.version_key('0.4.2pre1'))


if __name__ == '__main__':
    unittest.main()
