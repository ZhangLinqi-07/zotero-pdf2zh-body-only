# SPDX-License-Identifier: AGPL-3.0-only
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import install
import restore


class PortableInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="body-only-test-")
        self.addCleanup(self.temp.cleanup)
        self.server = Path(self.temp.name) / "directory with spaces" / "server"
        self.server.mkdir(parents=True)
        for source in (ROOT / "upstream").rglob("*"):
            if source.is_file():
                target = self.server / source.relative_to(ROOT / "upstream")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        (self.server / "config").mkdir()
        (self.server / "config/config.toml").write_text("PRIVATE_SETTINGS_SENTINEL", encoding="utf-8")
        (self.server / "translated").mkdir()
        (self.server / "translated/private.pdf").write_bytes(b"PRIVATE_PDF_SENTINEL")
        self.originals = {
            str(path.relative_to(self.server)): path.read_bytes()
            for path in self.server.rglob("*") if path.is_file()
        }

    def assert_originals_restored(self):
        for relative, original in self.originals.items():
            self.assertEqual((self.server / relative).read_bytes(), original, relative)

    def test_install_restore_and_personal_files_are_preserved(self):
        result = install.install(self.server)
        self.assertEqual(result["status"], "installed")
        self.assertTrue((self.server / "utils/section_skip.py").is_file())
        self.assertTrue((self.server / "start-body-only.cmd").is_file())
        self.assertEqual((self.server / "config/config.toml").read_text(), "PRIVATE_SETTINGS_SENTINEL")
        self.assertEqual((self.server / "translated/private.pdf").read_bytes(), b"PRIVATE_PDF_SENTINEL")
        self.assertEqual(restore.restore(self.server)["status"], "restored")
        self.assert_originals_restored()
        self.assertFalse((self.server / "utils/section_skip.py").exists())
        self.assertFalse((self.server / install.STATE).exists())

    def test_repeated_install_is_a_noop(self):
        install.install(self.server)
        backup_count = len(list((self.server / ".body-only-backups").iterdir()))
        self.assertEqual(install.install(self.server)["status"], "already_installed")
        self.assertEqual(len(list((self.server / ".body-only-backups").iterdir())), backup_count)

    def test_dry_run_does_not_write_files(self):
        self.assertEqual(install.install(self.server, dry_run=True)["status"], "dry_run")
        self.assert_originals_restored()
        self.assertFalse((self.server / install.STATE).exists())
        self.assertFalse((self.server / ".body-only-backups").exists())

    def test_unknown_local_edits_require_explicit_force_and_are_backed_up(self):
        original = (self.server / "server.py").read_text(encoding="utf-8")
        (self.server / "server.py").write_text(original + "\n# user customization\n", encoding="utf-8")
        edited = (self.server / "server.py").read_bytes()
        with self.assertRaises(ValueError):
            install.install(self.server)
        self.assertFalse((self.server / ".body-only-backups").exists())
        install.install(self.server, force=True)
        restore.restore(self.server)
        self.assertEqual((self.server / "server.py").read_bytes(), edited)

    def test_restore_refuses_to_overwrite_later_edits(self):
        install.install(self.server)
        target = self.server / "utils/section_skip.py"
        target.write_text(target.read_text(encoding="utf-8") + "\n# later customization\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            restore.restore(self.server)
        self.assertTrue((self.server / install.STATE).exists())

    def test_interrupted_install_rolls_back_written_source_files(self):
        original_write = install.atomic_write
        calls = 0
        def interrupted_write(path, content):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated disk write error")
            return original_write(path, content)
        with patch.object(install, "atomic_write", side_effect=interrupted_write):
            with self.assertRaises(OSError):
                install.install(self.server)
        self.assert_originals_restored()
        self.assertFalse((self.server / install.STATE).exists())

    def test_unknown_server_version_is_rejected_even_with_force(self):
        target = self.server / "server.py"
        target.write_text(target.read_text(encoding="utf-8").replace('__version__ = "4.1.7"', '__version__ = "99.0.0"'), encoding="utf-8")
        with self.assertRaises(ValueError):
            install.install(self.server, force=True)
        self.assertFalse((self.server / ".body-only-backups").exists())

    def test_outside_paths_are_rejected(self):
        with self.assertRaises(ValueError):
            install.inside(self.server, "../outside")

    def test_crlf_upstream_files_are_compatible(self):
        for relative in ("server.py", "index.html", "utils/execute.py"):
            target = self.server / relative
            target.write_bytes(target.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        install.install(self.server)
        self.assertEqual(restore.restore(self.server)["status"], "restored")
        self.assertIn(b"\r\n", (self.server / "server.py").read_bytes())


if __name__ == "__main__":
    unittest.main()
