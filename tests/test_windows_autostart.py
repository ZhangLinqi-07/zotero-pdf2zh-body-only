# SPDX-License-Identifier: AGPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'payload'))
from utils import windows_autostart


class WindowsAutostartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Kinbo user's folder ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'pythonw.exe').touch()
        (self.root / 'run_body_only.py').touch()
        (self.root / '.body-only-launch.json').write_text(json.dumps(
            {'server_python': str(self.root / 'python.exe')}))

    def test_configures_correct_port_and_quotes_paths_without_storing_credentials(self):
        with patch.object(windows_autostart.sys, 'platform', 'win32'), \
             patch.object(windows_autostart.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            result = windows_autostart.configure(self.root, 8893)
        self.assertEqual(result['state'], 'enabled')
        command = run.call_args.args[0]
        script = command[-1]
        self.assertIn('Kinbo Backend (8893)', script)
        self.assertIn('--port 8893', script)
        self.assertIn("user''s folder", script)
        self.assertIn('-AtLogOn', script)
        self.assertIn('-LogonType Interactive -RunLevel Limited', script)
        self.assertIn('-MultipleInstances IgnoreNew', script)
        self.assertIn('-ExecutionTimeLimit ([TimeSpan]::Zero)', script)
        self.assertIn('-RestartCount 3', script)
        self.assertNotIn('-Password', script)

    def test_other_platforms_and_remote_bindings_do_not_register_tasks(self):
        for platform, host in [('linux', '127.0.0.1'), ('darwin', 'localhost'), ('win32', '0.0.0.0')]:
            with self.subTest(platform=platform, host=host), \
                 patch.object(windows_autostart.sys, 'platform', platform), \
                 patch.object(windows_autostart.subprocess, 'run') as run:
                self.assertEqual(windows_autostart.configure(self.root, 8891, host)['state'], 'unsupported')
                run.assert_not_called()

    def test_registration_failure_is_visible_without_exposing_raw_errors(self):
        for outcome in [Mock(returncode=1), OSError('PRIVATE_SENTINEL')]:
            with patch.object(windows_autostart.sys, 'platform', 'win32'), \
                 patch.object(windows_autostart.subprocess, 'run') as run:
                if isinstance(outcome, Exception):
                    run.side_effect = outcome
                else:
                    run.return_value = outcome
                result = windows_autostart.configure(self.root, 8893)
                self.assertEqual(result['state'], 'failed')
                self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))

    def test_unmanaged_directory_does_not_create_a_task(self):
        (self.root / '.body-only-launch.json').unlink()
        with patch.object(windows_autostart.sys, 'platform', 'win32'), \
             patch.object(windows_autostart.subprocess, 'run') as run:
            self.assertEqual(windows_autostart.configure(self.root, 8893)['state'], 'failed')
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
