#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise the real drain/restart transaction in a disposable service directory."""
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from test_backend_update import pack
from utils.kinbo_update_worker import digest, write_json

SERVER = '''from pathlib import Path
import os, sys, json
from flask import Flask
from utils.kinbo_update import KinboUpdater
root = Path(__file__).resolve().parent
version = "VERSION"
app = Flask(__name__)
port = int(sys.argv[1])
updater = KinboUpdater(app, root, version, port, lambda: (root / "busy").exists())
@app.get("/api/capabilities")
def caps():
    return {"version": version, "updateInstance": os.environ.get("KINBO_UPDATE_INSTANCE", "")}
with (root / "pids.txt").open("a") as handle: handle.write(str(os.getpid()) + "\\n")
app.run(host="127.0.0.1", port=port, threaded=True)
'''


def main():
    with tempfile.TemporaryDirectory(prefix='kinbo-update-integration-') as directory:
        root = Path(directory)
        files = {'server.py': SERVER.replace('VERSION', '0.4.1').encode(), 'run_body_only.py': b'# launcher\n'}
        for name in ('kinbo_update.py', 'kinbo_update_worker.py'):
            files['utils/' + name] = (ROOT / 'payload/utils' / name).read_bytes()
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        write_json(root / '.body-only-installed.json', {'version': '0.4.1', 'backup': '.body-only-backups/fixture',
                   'files': [{'path': name, 'existed': False, 'after_sha256': digest(content)} for name, content in files.items()]})
        (root / 'config').mkdir()
        (root / 'config/config.toml').write_bytes(b'PRIVATE_KEY_SENTINEL')
        (root / 'reading').mkdir()
        (root / 'reading/private-note.md').write_bytes(b'PRIVATE_NOTE_SENTINEL')
        (root / 'busy').touch()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def get(path, headers=None):
            with opener.open(urllib.request.Request(base + path, headers=headers or {}), timeout=2) as response:
                return json.load(response)
        with (root / 'test.log').open('wb') as log:
            process = subprocess.Popen([sys.executable, str(root / 'server.py'), str(port)], cwd=root,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                for _ in range(60):
                    try:
                        if get('/api/capabilities')['version'] == '0.4.1': break
                    except OSError: pass
                    time.sleep(.1)
                headers = {'X-Kinbo-Client': 'zotero'}
                token = get('/api/kinbo/update', headers)['token']
                files['server.py'] = SERVER.replace('VERSION', '0.4.2').encode()
                content, sha, _ = pack(files)
                data = json.dumps({'backendVersion': '0.4.2', 'sha256': sha,
                                   'bundle': base64.b64encode(content).decode()}).encode()
                req = urllib.request.Request(base + '/api/kinbo/update', data=data, headers={**headers,
                        'X-Kinbo-Update-Token': token, 'Content-Type': 'application/json'})
                with opener.open(req, timeout=5) as response: assert response.status == 202
                time.sleep(1.5)
                assert get('/api/capabilities')['version'] == '0.4.1'
                assert get('/api/kinbo/update', headers)['update']['state'] == 'waiting'
                (root / 'busy').unlink()
                completed = False
                for _ in range(150):
                    process.poll()  # Reap the old POSIX server so its PID is no longer alive.
                    try:
                        state = get('/api/kinbo/update', headers)
                        if state['version'] == '0.4.2' and state['update']['state'] == 'completed':
                            completed = True
                            break
                    except OSError: pass
                    time.sleep(.1)
                assert completed, (root / 'test.log').read_text(encoding='utf-8', errors='replace')
                assert (root / 'config/config.toml').read_bytes() == b'PRIVATE_KEY_SENTINEL'
                assert (root / 'reading/private-note.md').read_bytes() == b'PRIVATE_NOTE_SENTINEL'
                print(json.dumps({'status': 'passed', 'idleWaitVerified': True, 'realRestart': True,
                                  'version': '0.4.2', 'configurationPreserved': True, 'notesPreserved': True}))
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)
                for pid in (root / 'pids.txt').read_text().splitlines():
                    if int(pid) == process.pid: continue
                    try:
                        if os.name == 'nt':
                            subprocess.run(['taskkill', '/PID', str(int(pid)), '/T', '/F'], capture_output=True, timeout=10)
                        else:
                            os.kill(int(pid), 15)
                    except (ProcessLookupError, OSError): pass
                time.sleep(.5)


if __name__ == '__main__':
    main()
