# SPDX-License-Identifier: AGPL-3.0-only
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
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
