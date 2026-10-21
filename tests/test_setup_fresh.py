# SPDX-License-Identifier: AGPL-3.0-only
import hashlib
import json
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import install
import setup_fresh as setup


class FreshInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="body-only-fresh-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_archive(self, members):
        archive = self.root / "server.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            for name, content in members.items():
                handle.writestr(name, content)
        return archive

    def test_asset_checksum_rejects_modified_local_and_cached_files(self):
        original = self.root / "asset.zip"
        original.write_bytes(b"verified asset")
        info = {"name": "asset.zip", "sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
                "url": "https://example.invalid/asset.zip"}
        self.assertEqual(setup.checked_asset(info, self.root, original), original.resolve())
        self.assertEqual(setup.checked_asset(info, self.root), original)
        original.write_bytes(b"altered asset")
        with self.assertRaises(ValueError):
            setup.checked_asset(info, self.root, original)
        with patch.object(setup.urllib.request, "urlopen", side_effect=OSError("offline")) as download:
            with self.assertRaises(OSError):
                setup.checked_asset(info, self.root)
            download.assert_called_once()

    def test_archive_traversal_is_rejected_before_any_extraction(self):
        archive = self.make_archive({"server/server.py": "valid", "server/../../escape": "bad"})
        with self.assertRaises(ValueError):
            setup.extract_server(archive, self.root / "extract")
        self.assertFalse((self.root / "extract").exists())
        self.assertFalse((self.root / "escape").exists())

    def test_archive_windows_paths_and_symlinks_are_rejected(self):
        for name in ("/server/server.py", "server/C:/escape", "server/..\\escape"):
            with self.subTest(name=name):
                archive = self.make_archive({"server/server.py": "valid", name: "bad"})
                with self.assertRaises(ValueError):
                    setup.extract_server(archive, self.root / "extract")
        archive = self.root / "link.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("server/server.py", "valid")
            item = zipfile.ZipInfo("server/link")
            item.create_system = 3
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
            handle.writestr(item, "../../elsewhere")
        with self.assertRaises(ValueError):
            setup.extract_server(archive, self.root / "extract")

    def test_existing_personal_directory_is_never_claimed(self):
        target = self.root / "personal"
        target.mkdir()
        (target / "private.txt").write_text("personal settings")
        with self.assertRaises(ValueError):
            setup.claim_directory(target)
        self.assertFalse((target / setup.MARKER).exists())
        self.assertEqual((target / "private.txt").read_text(), "personal settings")

    def test_foreign_installation_marker_is_rejected(self):
        target = self.root / "foreign"
        target.mkdir()
        (target / setup.MARKER).write_text('{"application":"another-app"}')
        with self.assertRaises(ValueError):
            setup.claim_directory(target)

    def test_fresh_sources_patch_and_resume_preserve_api_configuration(self):
        members = {"server/" + str(path.relative_to(ROOT / "upstream")).replace("\\", "/"): path.read_bytes()
                   for path in (ROOT / "upstream").rglob("*") if path.is_file()}
        members["server/config/venv.json.example"] = json.dumps({"pdf2zh": {"uv": {"packages": ["old-engine"]}}})
        archive = self.make_archive(members)
        plugin = self.root / "plugin.xpi"
        plugin.write_bytes(b"fixture plugin")
        assets = json.loads((ROOT / "downloads.json").read_text(encoding="utf-8"))
        assets["plugin"]["sha256"] = hashlib.sha256(plugin.read_bytes()).hexdigest()
        (self.root / "downloads.json").write_text(json.dumps(assets), encoding="utf-8")
        target = self.root / "目录 with spaces"
        def asset(info, cache, local=None):
            return archive if info["name"].endswith(".zip") else plugin
        with patch.object(setup, "checked_asset", side_effect=asset), patch.object(setup, "ROOT", self.root):
            _, server, xpi = setup.prepare_sources(target)
            self.assertEqual(xpi.read_bytes(), b"fixture plugin")
            self.assertEqual(install.install(server)["status"], "installed")
            private = server / "config/config.toml"
            private.write_text("PRIVATE_SENTINEL")
            setup.prepare_sources(target)
            self.assertEqual(install.install(server)["status"], "already_installed")
            self.assertEqual(private.read_text(), "PRIVATE_SENTINEL")
        config = json.loads((server / "config/venv.json").read_text())
        self.assertIn("pdf2zh-next==2.9.0", config["pdf2zh_next"]["uv"]["packages"])
        self.assertIn("BabelDOC==0.6.2", config["pdf2zh_next"]["conda"]["packages"])
        self.assertIn("bitstring>=4.3,<5", config["pdf2zh_next"]["uv"]["packages"])
        self.assertEqual(config["pdf2zh"]["uv"]["packages"], ["old-engine"])

    def test_launcher_uses_selected_python_without_path_requirement(self):
        server = self.root / "server"
        shutil.copytree(ROOT / "upstream", server)
        install.install(server, server_python=sys.executable)
        command = (server / "start-body-only.cmd").read_text(encoding="utf-8")
        self.assertIn(str(Path(sys.executable).resolve()).replace("%", "%%"), command)
        self.assertIn("chcp 65001", command)
        self.assertNotIn('\npython "', command)


if __name__ == "__main__":
    unittest.main()
