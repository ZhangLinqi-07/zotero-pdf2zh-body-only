# SPDX-License-Identifier: AGPL-3.0-only
"""Manage a per-user launchd agent for an existing Kinbo loopback backend."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile


def managed_python(root):
    # Resolving a venv's bin/python symlink loses the venv and its packages.
    settings = json.loads((root / '.body-only-launch.json').read_text(encoding='utf-8'))
    for candidate in (root.parent / '.server-venv/bin/python', root / '.server-venv/bin/python',
                      root / '.venv/bin/python', Path(settings['server_python']).expanduser()):
        if candidate.is_absolute() and candidate.is_file():
            return str(candidate.absolute())
    raise ValueError('Missing managed Python')


def configure(root, port, host='127.0.0.1', start=False):
    if sys.platform != 'darwin' or host not in {'127.0.0.1', 'localhost'}:
        return {'state': 'unsupported', 'message': 'macOS 自动启动仅适用于本机后台'}
    label = f'org.kinbo.backend.{port}'
    try:
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError('Invalid port')
        root = Path(root).expanduser().resolve()
        if not all((root / name).is_file() for name in ('server.py', 'run_body_only.py', '.body-only-installed.json')):
            raise ValueError('Missing managed backend')
        python = managed_python(root)
        logs = root / 'body-only-logs'
        logs.mkdir(exist_ok=True)
        agent = {'Label': label,
                 'ProgramArguments': [python, str(root / 'run_body_only.py'), '--server-dir', str(root), '--port', str(port), '--python', python],
                 'WorkingDirectory': str(root), 'RunAtLoad': True,
                 'KeepAlive': {'SuccessfulExit': False}, 'ThrottleInterval': 30,
                 # The existing update worker restarts the server independently.
                 'AbandonProcessGroup': True,
                 'EnvironmentVariables': {'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'},
                 'StandardOutPath': str(logs / f'launchd-{port}.log'),
                 'StandardErrorPath': str(logs / f'launchd-{port}-error.log')}
        folder = Path.home() / 'Library/LaunchAgents'
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (label + '.plist')
        for other in folder.glob('org.kinbo.backend.*.plist'):
            if other == target:
                continue
            arguments = plistlib.loads(other.read_bytes()).get('ProgramArguments', [])
            if '--server-dir' in arguments and arguments[arguments.index('--server-dir') + 1:][:1] == [str(root)]:
                return {'state': 'conflict', 'message': '该后台已在其他端口配置自动启动，请核对 Zotero 中原有的服务器地址'}
        if target.exists():
            previous = plistlib.loads(target.read_bytes())
            if previous.get('ProgramArguments') != agent['ProgramArguments']:
                return {'state': 'conflict', 'message': '该端口已有其他 Kinbo 自动启动配置，请确认原后台目录'}
        data = plistlib.dumps(agent)
        if not target.exists() or target.read_bytes() != data:
            with tempfile.NamedTemporaryFile(dir=folder, delete=False) as output:
                temporary = Path(output.name)
                output.write(data)
            try:
                temporary.chmod(0o644)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        if start:
            service = f'gui/{os.getuid()}/{label}'
            def run(*args):
                return subprocess.run(['/bin/launchctl', *args], capture_output=True, timeout=15)
            if run('print', service).returncode:
                if run('bootstrap', f'gui/{os.getuid()}', str(target)).returncode:
                    raise OSError('Agent registration failed')
            # No -k: a running backend and its active tasks are never killed.
            if run('kickstart', service).returncode:
                raise OSError('Agent start failed')
        return {'state': 'enabled', 'label': label, 'message': '已启用 macOS 登录后自动启动 Kinbo 后台'}
    except (OSError, ValueError, KeyError, TypeError, plistlib.InvalidFileException, subprocess.TimeoutExpired):
        return {'state': 'failed', 'label': label,
                'message': 'macOS 后台自动启动失败，请确认目录权限，并在系统设置的登录项中允许 Kinbo 后台运行'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-dir', required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    result = configure(args.server_dir, args.port, start=True)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['state'] == 'enabled' else 1)
