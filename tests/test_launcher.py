# SPDX-License-Identifier: AGPL-3.0-only
import os
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_body_only

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_healthy_new_backend_is_reused_without_a_second_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'server.py').touch()
            responses = [io.BytesIO(json.dumps(value).encode()) for value in
                         [{'status': 'success'}, {'pdfReading': True, 'version': '0.4.4'}]]
            with patch.object(sys, 'argv', ['run_body_only.py', '--server-dir', directory, '--port', '8892']), \
                 patch.object(run_body_only.urllib.request, 'urlopen', side_effect=responses), \
                 patch.object(run_body_only.subprocess, 'Popen') as launch:
                run_body_only.main()
            launch.assert_not_called()

    def test_existing_launcher_exits_cleanly_without_starting_server(self):
        with tempfile.TemporaryDirectory(prefix='kinbo launcher ') as directory:
            server = Path(directory)
            (server / 'server.py').write_text('raise RuntimeError("must not start")\n')
            logs = server / 'body-only-logs'
            logs.mkdir()
            path = logs / 'service-8893.lock'
            path.write_bytes(b'0')
            with path.open('r+b') as lock:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = subprocess.run(
                    [sys.executable, str(ROOT / 'run_body_only.py'),
                     '--server-dir', str(server), '--port', '8893'],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('already running', result.stdout)
                self.assertFalse((logs / 'server-8893.pid').exists())


if __name__ == '__main__':
    unittest.main()
