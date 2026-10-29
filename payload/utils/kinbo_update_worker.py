# SPDX-License-Identifier: AGPL-3.0-only
"""Standalone update worker. No third-party imports or shell commands."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile

MAX_BUNDLE = 12 * 1024 * 1024
MAX_EXPANDED = 32 * 1024 * 1024
COMPATIBILITY = {'upstream_version': '4.1.7', 'pdf2zh_next': '2.9.0', 'babeldoc': '0.6.2'}


def digest(data):
    return hashlib.sha256(data.decode('utf-8-sig').replace('\r\n', '\n').encode('utf-8')).hexdigest()


def atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.kinbo-', delete=False) as handle:
        handle.write(content)
        temporary = handle.name
    os.replace(temporary, path)


def write_json(path, data):
    atomic(path, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def allowed(name):
    return name in {'server.py', 'index.html', 'run_body_only.py', 'README.body-only.md',
                    'NOTICE.body-only.md', 'LICENSE.body-only'} or bool(re.fullmatch(
        r'(?:utils/[A-Za-z_][A-Za-z0-9_]*\.py|prompts/[A-Za-z0-9_-]+\.txt|'
        r'web/(?:vendor/)?[A-Za-z0-9_.-]+\.(?:js|css|json|txt))', name))


def inside(root, name):
    root = Path(root).resolve()
    parts = PurePosixPath(name).parts
    if (not parts or '..' in parts or '\\' in name or ':' in name or name.startswith('/')
            or not allowed(name)):
        raise ValueError('更新包包含未授权路径')
    target = root.joinpath(*parts)
    for current in (target, *target.parents):
        if current == root:
            break
        if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
            raise ValueError('更新目标包含链接，已停止更新')
    if not target.resolve().is_relative_to(root):
        raise ValueError('更新目标超出服务目录')
    return target


def version_key(value):
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:pre(\d+))?', str(value))
    if not match:
        raise ValueError('无效的后台版本')
    major, minor, patch, preview = match.groups()
    return int(major), int(minor), int(patch), preview is None, int(preview or 0)


def validate_bundle(content, expected_sha, expected_version):
    version_key(expected_version)
    if len(content) > MAX_BUNDLE or hashlib.sha256(content).hexdigest() != expected_sha:
        raise ValueError('后台更新包校验失败，尚未修改文件')
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if (len(names) != len({name.casefold() for name in names}) or len(names) > 160
                    or sum(item.file_size for item in infos) > MAX_EXPANDED
                    or any(item.flag_bits & 1 or item.is_dir() or stat.S_ISLNK(item.external_attr >> 16) for item in infos)):
                raise ValueError('无效的后台更新包结构')
            if any(name != 'kinbo-backend.json' and not allowed(name) for name in names):
                raise ValueError('后台更新包包含个人数据或未授权文件')
            if archive.getinfo('kinbo-backend.json').file_size > 256 * 1024:
                raise ValueError('后台更新清单过大')
            metadata = json.loads(archive.read('kinbo-backend.json'))
            if (metadata.get('schema') != 1 or metadata.get('backendVersion') != expected_version
                    or metadata.get('compatibility') != COMPATIBILITY or not isinstance(metadata.get('files'), dict)):
                raise ValueError('后台依赖发生变化或版本不匹配，请使用完整安装器升级')
            if set(names) != set(metadata['files']) | {'kinbo-backend.json'}:
                raise ValueError('后台更新包文件清单不完整')
            required = {'server.py', 'run_body_only.py', 'utils/kinbo_update.py', 'utils/kinbo_update_worker.py'}
            if not required.issubset(metadata['files']):
                raise ValueError('后台更新包缺少必需文件')
            files = {}
            for name, entry in metadata['files'].items():
                data = archive.read(name)
                if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                    raise ValueError('后台更新文件校验失败')
                if name.endswith('.py'):
                    compile(data, name, 'exec')
                files[name] = data
            return metadata, files
    except (KeyError, TypeError, json.JSONDecodeError, zipfile.BadZipFile, SyntaxError, UnicodeError):
        raise ValueError('后台更新包损坏或源码无效') from None


def check_target(root, files):
    root = Path(root).resolve()
    state_path = root / '.body-only-installed.json'
    if not state_path.is_file() or not (root / 'server.py').is_file():
        raise ValueError('目标不是受管理的 Kinbo 后台目录')
    state = json.loads(state_path.read_text(encoding='utf-8'))
    known = {entry['path']: entry for entry in state.get('files', [])}
    for name in files:
        target = inside(root, name)
        if target.exists() and (name not in known or digest(target.read_bytes()) != known[name]['after_sha256']):
            raise ValueError('后台源码有本机改动，自动更新已停止，请先审查改动')
    return state


def apply_files(root, metadata, files):
    root = Path(root).resolve()
    previous = check_target(root, files)
    backup = root / '.body-only-backups' / ('update-' + uuid.uuid4().hex)
    backup.mkdir(parents=True)
    old_state = (root / '.body-only-installed.json').read_bytes()
    old_info = (root / '.kinbo-backend.json').read_bytes() if (root / '.kinbo-backend.json').exists() else None
    records = []
    for name, content in files.items():
        target = inside(root, name)
        record = {'path': name, 'existed': target.exists(), 'after_sha256': digest(content)}
        if target.exists():
            original = target.read_bytes()
            record['before_sha256'] = digest(original)
            destination = backup / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(original)
        records.append(record)
    backup.joinpath('installed-state.json').write_bytes(old_state)
    if old_info is not None:
        backup.joinpath('backend-info.json').write_bytes(old_info)
    write_json(backup / 'manifest.json', {'version': metadata['backendVersion'], 'files': records})
    transaction = {'backup': backup, 'records': records, 'old_state': old_state, 'old_info': old_info}
    try:
        for name, content in files.items():
            atomic(inside(root, name), content)
        # Keep unchanged generated launch/config records so future installers can
        # validate the whole managed installation, without changing those files.
        retained = []
        for entry in previous.get('files', []):
            if entry['path'] in files:
                continue
            target = (root / entry['path']).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                raise ValueError('原安装记录包含无效路径')
            content = target.read_bytes()
            destination = backup / entry['path']
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            retained.append({'path': entry['path'], 'existed': True,
                             'before_sha256': digest(content), 'after_sha256': digest(content)})
        write_json(root / '.body-only-installed.json', {'version': metadata['backendVersion'],
                   'backup': str(backup.relative_to(root)), 'files': retained + records})
        write_json(root / '.kinbo-backend.json', metadata)
        return transaction
    except Exception:
        rollback_files(root, transaction)
        raise


def rollback_files(root, transaction):
    root = Path(root).resolve()
    for entry in reversed(transaction['records']):
        target = inside(root, entry['path'])
        if entry['existed']:
            atomic(target, (transaction['backup'] / entry['path']).read_bytes())
        elif target.is_file():
            target.unlink()
    atomic(root / '.body-only-installed.json', transaction['old_state'])
    if transaction['old_info'] is not None:
        atomic(root / '.kinbo-backend.json', transaction['old_info'])
    elif (root / '.kinbo-backend.json').exists():
        (root / '.kinbo-backend.json').unlink()


def process_alive(pid):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def launch(command, root, nonce):
    logs = Path(root) / 'body-only-logs'
    logs.mkdir(exist_ok=True)
    env = dict(os.environ, KINBO_UPDATE_INSTANCE=nonce, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    with (logs / 'kinbo-update-server.log').open('ab') as log:
        return subprocess.Popen(command, cwd=str(root), env=env, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=os.name != 'nt',
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def stop_child(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=10)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        raise RuntimeError('新版进程未能退出，未覆盖仍在运行的代码') from None


def healthy(port, version, nonce, timeout=45):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with opener.open(f'http://127.0.0.1:{port}/api/capabilities', timeout=2) as response:
                data = json.load(response)
            if data.get('version') == version and data.get('updateInstance') == nonce:
                return True
        except (OSError, ValueError):
            pass
        time.sleep(.25)
    return False


def run_plan(path):
    path = Path(path).resolve()
    plan = json.loads(path.read_text(encoding='utf-8'))
    root, state = Path(plan['root']).resolve(), Path(plan['state']).resolve()
    if not path.is_relative_to(root / '.kinbo-updates') or state != root / '.kinbo-updates/state.json':
        raise ValueError('无效的后台更新计划路径')
    def status(name, message, **extra):
        write_json(state, {'state': name, 'message': message, 'backendVersion': plan['version'], **extra})
    try:
        metadata, files = validate_bundle(path.with_name('backend.zip').read_bytes(), plan['sha256'], plan['version'])
        check_target(root, files)
        deadline = time.monotonic() + 30
        while process_alive(plan['parentPID']) and time.monotonic() < deadline:
            time.sleep(.1)
        if process_alive(plan['parentPID']):
            status('failed', '旧后台未正常退出，未修改程序文件')
            return
        status('installing', '正在备份并更新后台源码')
        transaction = apply_files(root, metadata, files)
    except Exception:
        if not process_alive(plan['parentPID']):
            try:
                nonce = uuid.uuid4().hex
                launch(plan['command'], root, nonce)
                restored = healthy(plan['port'], plan['previousVersion'], nonce)
                status('rolled_back' if restored else 'failed', '更新未完成，已保留旧版源码和个人数据')
            except Exception:
                status('failed', '更新未完成，请使用原启动器恢复服务')
        else:
            status('failed', '后台更新预检失败，尚未修改文件')
        return
    process = None
    try:
        status('restarting', '正在启动并检查新版后台')
        process = launch(plan['command'], root, plan['nonce'])
        if not healthy(plan['port'], plan['version'], plan['nonce']):
            raise RuntimeError('新后台健康检查未通过')
        status('completed', '插件与后台已同步更新', previousVersion=plan['previousVersion'])
    except Exception:
        try:
            if process is not None:
                stop_child(process)
            rollback_files(root, transaction)
            rollback_nonce = uuid.uuid4().hex
            launch(plan['command'], root, rollback_nonce)
            restored = healthy(plan['port'], plan['previousVersion'], rollback_nonce)
            status('rolled_back' if restored else 'failed',
                   '新版启动失败，已恢复旧版后台' if restored else '已恢复旧版文件，后台启动失败，请运行原启动器')
        except Exception:
            status('failed', '后台恢复未完成，请保留备份并检查本机服务')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    args = parser.parse_args()
    run_plan(args.plan)
