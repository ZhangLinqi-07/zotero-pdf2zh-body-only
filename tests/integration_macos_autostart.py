#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise real launchd with a disposable stdlib server; never use a user backend."""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'payload'))
from utils import macos_autostart


def main():
    if sys.platform != 'darwin':
        print(json.dumps({'status': 'skipped', 'reason': 'Real launchd requires macOS'}))
        return
    domain = f'gui/{os.getuid()}'
    if subprocess.run(['/bin/launchctl', 'print', domain], capture_output=True).returncode:
        print(json.dumps({'status': 'skipped', 'reason': 'No logged-in macOS GUI launchd domain'}))
        return
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    service = f'{domain}/org.kinbo.backend.{port}'
    with tempfile.TemporaryDirectory(prefix='kinbo 研究-launchd-isolated-') as folder:
        home = Path(folder).resolve()
        root = home / 'app/server'; root.mkdir(parents=True)
        shutil.copy2(ROOT / 'run_body_only.py', root / 'run_body_only.py')
        (root / '.body-only-installed.json').write_text('{}')
        (root / '.body-only-launch.json').write_text(json.dumps({'server_python': sys.executable}))
        sentinel = root / 'private-config-fixture.txt'; sentinel.write_text('SYNTHETIC_PRESERVE_SENTINEL')
        (root / 'server.py').write_text('''import argparse, http.server, json
from socketserver import TCPServer
parser = argparse.ArgumentParser(); parser.add_argument('--port', type=int); args, _ = parser.parse_known_args()
class LocalServer(http.server.HTTPServer):
 def server_bind(self):
  TCPServer.server_bind(self); self.server_name = '127.0.0.1'; self.server_port = self.server_address[1]
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
  self.wfile.write(json.dumps({'status': 'success', 'version': '0.4.5', 'pdfReading': True}).encode())
 def log_message(self, *args): pass
LocalServer(('127.0.0.1', args.port), Handler).serve_forever()
''')
        try:
            with patch.object(Path, 'home', return_value=home):
                result = macos_autostart.configure(root, port, start=True)
            if result['state'] != 'enabled':
                raise AssertionError(result['message'])
            deadline = time.monotonic() + 20
            local = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            while True:
                try:
                    with local.open(f'http://127.0.0.1:{port}/api/capabilities', timeout=1) as response:
                        assert json.load(response)['pdfReading']
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        pidfile = root / f'body-only-logs/server-{port}.pid'
                        print('Disposable backend PID file present:', pidfile.exists(), flush=True)
                        if pidfile.exists():
                            pid = pidfile.read_text().strip()
                            for command in (['/bin/ps', '-p', pid, '-o', 'pid,ppid,stat,comm'],
                                            ['/usr/sbin/lsof', '-nP', '-a', '-p', pid, '-iTCP'],
                                            ['/usr/bin/sample', pid, '1', '1']):
                                diagnostic = subprocess.run(command, capture_output=True, text=True, timeout=10)
                                print(diagnostic.stdout[:9000] + diagnostic.stderr[-1000:], flush=True)
                        logs = '\n'.join(log.read_text(errors='replace')[-2500:] for log in (root / 'body-only-logs').glob('*.log'))
                        state = subprocess.run(['/bin/launchctl', 'print', service], capture_output=True, text=True).stdout
                        raise AssertionError('Real launchd backend did not become reachable\n' + logs + '\n' + state[-4000:])
                    time.sleep(.2)
            pidfile = root / f'body-only-logs/server-{port}.pid'
            pid = int(pidfile.read_text())
            with patch.object(Path, 'home', return_value=home):
                assert macos_autostart.configure(root, port, start=True)['state'] == 'enabled'
            time.sleep(.5)
            assert int(pidfile.read_text()) == pid, 'Waking a healthy backend restarted its process'
            assert sentinel.read_text() == 'SYNTHETIC_PRESERVE_SENTINEL'
            print(json.dumps({'status': 'passed', 'realLaunchd': True, 'portPreserved': True,
                              'existingProcessPreserved': True, 'personalFixturePreserved': True,
                              'userBackendUsed': False, 'externalModelCalls': 0}))
        finally:
            subprocess.run(['/bin/launchctl', 'bootout', service], capture_output=True, timeout=15)
            pidfile = root / f'body-only-logs/server-{port}.pid'
            if pidfile.exists():
                try:
                    os.kill(int(pidfile.read_text()), signal.SIGTERM)
                except ProcessLookupError:
                    pass


if __name__ == '__main__':
    main()
