# SPDX-License-Identifier: AGPL-3.0-only
"""Privileged loopback update API and an atomic admission gate for active work."""
import base64
import binascii
import hmac
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import uuid

from flask import g, jsonify, request
from .kinbo_update_worker import MAX_BUNDLE, check_target, validate_bundle, version_key, write_json, atomic, process_alive


class KinboUpdater:
    def __init__(self, app, root, version, port, busy, command=None, exit_process=os._exit):
        self.root, self.version, self.port = Path(root).resolve(), version, port
        self.busy, self.exit_process = busy, exit_process
        self.command = command or [sys.executable, str(self.root / 'server.py'), *sys.argv[1:]]
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.inflight, self.draining, self.pending = 0, False, None
        self.folder = self.root / '.kinbo-updates'
        self.state_path = self.folder / 'state.json'
        app.before_request(self.admit)
        app.teardown_request(self.release)
        app.add_url_rule('/api/kinbo/update', 'kinbo_update_status', self.status, methods=['GET'])
        app.add_url_rule('/api/kinbo/update', 'kinbo_update_submit', self.submit, methods=['POST'])

    def admit(self):
        if request.method in {'GET', 'HEAD', 'OPTIONS'} or request.path == '/api/kinbo/update':
            return None
        with self.lock:
            if self.draining:
                return jsonify(status='error', message='Kinbo 正在更新，请等待后台恢复后重试'), 503
            self.inflight += 1
            g.kinbo_update_admitted = True

    def release(self, _error):
        if g.pop('kinbo_update_admitted', False):
            with self.lock:
                self.inflight -= 1

    def privileged(self, mutation=False):
        try:
            local = ipaddress.ip_address(request.remote_addr).is_loopback
        except (ValueError, TypeError):
            local = False
        host = request.host.split(':')[0]
        # No Origin is sent by privileged Zotero HTTP. Browser pages, DNS
        # rebinding and CORS preflights cannot obtain or use this token.
        return (local and host in {'127.0.0.1', 'localhost'} and not request.headers.get('Origin')
                and request.headers.get('X-Kinbo-Client') == 'zotero'
                and (not mutation or hmac.compare_digest(request.headers.get('X-Kinbo-Update-Token', ''), self.token)))

    def current(self):
        try:
            return json.loads(self.state_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {'state': 'idle', 'message': '后台已就绪'}

    def status(self):
        if not self.privileged():
            return jsonify(status='error', message='更新接口仅供本机 Zotero 插件使用'), 403
        return jsonify(status='success', version=self.version, token=self.token, update=self.current())

    def submit(self):
        if not self.privileged(True):
            return jsonify(status='error', message='无效的本机更新请求'), 403
        if not request.content_length or request.content_length > MAX_BUNDLE * 4 // 3 + 4096:
            return jsonify(status='error', message='更新包大小无效'), 413
        try:
            data = request.get_json(silent=True) or {}
            version = data['backendVersion']
            if version_key(version) <= version_key(self.version):
                return jsonify(status='success', message='当前后台已是相同或更高版本')
            content = base64.b64decode(data['bundle'], validate=True)
            metadata, files = validate_bundle(content, data['sha256'], version)
            check_target(self.root, files)
            with self.lock:
                state = self.current()
                if self.pending or (state.get('state') in {'installing', 'restarting'} and state.get('workerPID', 0) > 0 and process_alive(state['workerPID'])):
                    return jsonify(status='success', update=state), 202
                staging = self.folder / uuid.uuid4().hex
                staging.mkdir(parents=True)
                atomic(staging / 'backend.zip', content)
                # Execute the currently trusted worker, never a worker loaded
                # from the incoming ZIP before its validation/installation.
                atomic(staging / 'worker.py', Path(__file__).with_name('kinbo_update_worker.py').read_bytes())
                plan = {'root': str(self.root), 'state': str(self.state_path), 'version': version,
                        'previousVersion': self.version, 'sha256': data['sha256'], 'parentPID': os.getpid(),
                        'port': self.port, 'command': self.command, 'nonce': uuid.uuid4().hex}
                write_json(staging / 'plan.json', plan)
                self.pending = staging / 'plan.json'
                write_json(self.state_path, {'state': 'waiting', 'backendVersion': version,
                                            'message': '更新包已校验，正在等待翻译、阅读和对话任务完成'})
                threading.Thread(target=self.wait_idle, daemon=True).start()
            return jsonify(status='success', update=self.current()), 202
        except (ValueError, KeyError, TypeError, binascii.Error) as error:
            return jsonify(status='error', message=str(error) if isinstance(error, ValueError) else '无效的更新包'), 400
        except OSError:
            return jsonify(status='error', message='后台更新包无法写入，请检查服务目录权限'), 500

    def wait_idle(self):
        # New work remains available while existing tasks run. Once all request
        # admissions and jobs are idle, close admission under the same lock.
        while self.pending:
            time.sleep(1)
            with self.lock:
                if self.inflight or self.busy():
                    continue
                self.draining = True
                plan = self.pending
            try:
                worker = subprocess.Popen([sys.executable, str(plan.with_name('worker.py')), '--plan', str(plan)],
                    cwd=str(self.root), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=os.name != 'nt', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                write_json(self.state_path, {'state': 'installing', 'backendVersion': json.loads(plan.read_text(encoding='utf-8'))['version'],
                                             'workerPID': worker.pid, 'message': '任务已完成，正在同步后台'})
                time.sleep(1)  # Let the accepted response reach Zotero before releasing the service port.
                self.exit_process(75)
                return
            except Exception:
                with self.lock:
                    self.pending, self.draining = None, False
                write_json(self.state_path, {'state': 'failed', 'message': '后台更新进程无法启动，当前版本继续运行'})
                return


def register_updater(translator, root, version, port):
    def busy():
        from utils.task_manager import task_manager
        if any(task.get('active', True) for task in task_manager.get_active_tasks_list()):
            return True
        with translator.reading.lock:
            if any(job.get('state') == 'running' for job in translator.reading.jobs.values()):
                return True
        with translator.paper_chat.lock:
            return any(session.get('busy') for session in translator.paper_chat.sessions.values())
    return KinboUpdater(translator.app, root, version, port, busy)
