#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Prepare and start a real fresh Mac backend without a model call or a user profile."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import setup_fresh
from install import VERSION


def main():
    if sys.platform != 'darwin':
        print(json.dumps({'status': 'skipped', 'reason': 'Fresh macOS setup requires macOS'}))
        return
    domain = f'gui/{os.getuid()}'
    if subprocess.run(['/bin/launchctl', 'print', domain], capture_output=True).returncode:
        print(json.dumps({'status': 'skipped', 'reason': 'No logged-in macOS GUI launchd domain'}))
        return
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    label = f'org.kinbo.backend.{port}'
    with tempfile.TemporaryDirectory(prefix='kinbo fresh 研究-') as directory:
        folder = Path(directory).resolve()
        key = 'uv_macos_arm64' if os.uname().machine == 'arm64' else 'uv_macos_x64'
        manifest = json.loads((ROOT / 'downloads.json').read_text())
        archive = setup_fresh.checked_asset(manifest[key], folder)
        member = manifest[key]['name'].removesuffix('.tar.gz') + '/uv'
        uv = folder / 'uv'
        with tarfile.open(archive, 'r:gz') as tar:
            uv.write_bytes(tar.extractfile(member).read())
        uv.chmod(0o755)
        subprocess.run([str(uv), '--version'], check=True)
        target = folder / 'app'
        root = target / 'server'
        try:
            subprocess.run([sys.executable, str(ROOT / 'setup_fresh.py'), '--uv', str(uv),
                            '--install-dir', str(target), '--defer-engine', '--start', '--port', str(port)],
                           check=True, timeout=300)
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/capabilities', timeout=3) as response:
                assert json.load(response)['version'] == VERSION
            launch = json.loads((root / '.body-only-launch.json').read_text())
            assert launch['server_python'] == str(target / '.server-venv/bin/python')
            assert (target / 'zotero-pdf2zh-body-only.xpi').is_file()
            print(json.dumps({'status': 'passed', 'realFreshBackend': True, 'pinnedUVVerified': True,
                              'privatePythonVenv': True, 'realLaunchd': True, 'backendVersion': VERSION,
                              'userBackendUsed': False, 'externalModelCalls': 0, 'translationEngineDeferred': True}))
        finally:
            subprocess.run(['/bin/launchctl', 'bootout', f'{domain}/{label}'], capture_output=True, timeout=15)
            pidfile = root / f'body-only-logs/server-{port}.pid'
            if pidfile.exists():
                try:
                    os.kill(int(pidfile.read_text()), signal.SIGTERM)
                except ProcessLookupError:
                    pass
            plist = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
            plist.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
