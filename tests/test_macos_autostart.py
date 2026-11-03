# SPDX-License-Identifier: AGPL-3.0-only
import json
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'payload'))
from utils import macos_autostart


class MacOSAutostartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Kinbo user's space ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.root = self.home / 'app/server'
        self.root.mkdir(parents=True)
        for name in ('server.py', 'run_body_only.py', '.body-only-installed.json'):
            (self.root / name).write_text('{}')
        self.python = self.root.parent / '.server-venv/bin/python'
        self.python.parent.mkdir(parents=True)
        self.python.touch()
        (self.root / '.body-only-launch.json').write_text(json.dumps({'server_python': 'missing-python'}))
        self.plist = self.home / 'Library/LaunchAgents/org.kinbo.backend.8892.plist'
        self.platform = patch.object(macos_autostart.sys, 'platform', 'darwin')
        self.platform.start(); self.addCleanup(self.platform.stop)
        self.home_patch = patch.object(Path, 'home', return_value=self.home)
        self.home_patch.start(); self.addCleanup(self.home_patch.stop)
        self.uid = patch.object(macos_autostart.os, 'getuid', return_value=501, create=True)
        self.uid.start(); self.addCleanup(self.uid.stop)

    def test_registers_login_agent_with_existing_environment_and_port_without_starting_another_server(self):
        with patch.object(macos_autostart.subprocess, 'run') as run:
            result = macos_autostart.configure(self.root, 8892)
        self.assertEqual(result['state'], 'enabled'); run.assert_not_called()
        agent = plistlib.loads(self.plist.read_bytes())
        self.assertEqual(agent['ProgramArguments'], [str(self.python), str(self.root / 'run_body_only.py'),
                                                    '--server-dir', str(self.root), '--port', '8892', '--python', str(self.python)])
        self.assertTrue(agent['RunAtLoad'])
        self.assertEqual(agent['KeepAlive'], {'SuccessfulExit': False})
        self.assertGreaterEqual(agent['ThrottleInterval'], 30)
        self.assertTrue(agent['AbandonProcessGroup'], 'Update workers must survive a managed launcher exit')
        self.assertNotIn('config.toml', self.plist.read_text())

    def test_bootstraps_and_wakes_agent_without_killing_existing_tasks(self):
        with patch.object(macos_autostart.subprocess, 'run', side_effect=[Mock(returncode=1), Mock(returncode=0), Mock(returncode=0)]) as run:
            self.assertEqual(macos_autostart.configure(self.root, 8892, start=True)['state'], 'enabled')
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[1], ['/bin/launchctl', 'bootstrap', 'gui/501', str(self.plist)])
        self.assertEqual(commands[2], ['/bin/launchctl', 'kickstart', 'gui/501/org.kinbo.backend.8892'])
        self.assertFalse(any('-k' in command or 'bootout' in command for command in commands))

    def test_running_agent_is_not_unloaded_or_registered_again(self):
        with patch.object(macos_autostart.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            for _ in range(2):
                self.assertEqual(macos_autostart.configure(self.root, 8892, start=True)['state'], 'enabled')
        self.assertEqual([call.args[0][1] for call in run.call_args_list], ['print', 'kickstart'] * 2)

    def test_one_backend_directory_cannot_run_on_two_ports(self):
        self.assertEqual(macos_autostart.configure(self.root, 8892)['state'], 'enabled')
        with patch.object(macos_autostart.subprocess, 'run') as run:
            self.assertEqual(macos_autostart.configure(self.root, 8893, start=True)['state'], 'conflict')
        run.assert_not_called()
        self.assertFalse(self.plist.with_name('org.kinbo.backend.8893.plist').exists())

    def test_other_installation_at_same_port_is_not_overwritten(self):
        macos_autostart.configure(self.root, 8892)
        original = self.plist.read_bytes()
        other = self.root.parent / 'other'; other.mkdir()
        for name in ('server.py', 'run_body_only.py', '.body-only-installed.json', '.body-only-launch.json'):
            (other / name).write_bytes((self.root / name).read_bytes())
        with patch.object(macos_autostart.subprocess, 'run') as run:
            result = macos_autostart.configure(other, 8892, start=True)
        self.assertEqual(result['state'], 'conflict'); run.assert_not_called()
        self.assertEqual(self.plist.read_bytes(), original)

    def test_failure_is_actionable_and_does_not_leak_raw_errors(self):
        with patch.object(macos_autostart.subprocess, 'run', side_effect=OSError('PRIVATE_SENTINEL')):
            result = macos_autostart.configure(self.root, 8892, start=True)
        self.assertEqual(result['state'], 'failed')
        self.assertIn('登录项', result['message']); self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))

    def test_remote_bindings_and_other_platforms_do_not_register(self):
        for platform, host in [('linux', '127.0.0.1'), ('win32', 'localhost'), ('darwin', '0.0.0.0')]:
            with self.subTest(platform=platform, host=host), patch.object(macos_autostart.sys, 'platform', platform):
                self.assertEqual(macos_autostart.configure(self.root, 8892, host)['state'], 'unsupported')
        self.assertFalse(self.plist.exists())

    def test_unmanaged_directory_is_not_registered(self):
        (self.root / '.body-only-installed.json').unlink()
        self.assertEqual(macos_autostart.configure(self.root, 8892)['state'], 'failed')
        self.assertFalse(self.plist.exists())

    def test_venv_executable_is_not_resolved_through_its_symlink(self):
        if sys.platform == 'win32':
            self.skipTest('POSIX venv symlink behavior is tested on macOS and Linux')
        target = self.root.parent / 'base-python'; target.touch()
        self.python.unlink()
        try:
            self.python.symlink_to(target)
        except OSError:
            self.skipTest('Creating symlinks requires platform permissions')
        self.assertEqual(macos_autostart.managed_python(self.root), str(self.python))


if __name__ == '__main__':
    unittest.main()
