#!/usr/bin/env python3
"""Install the body-only patch into an existing Zotero PDF2zh server."""
# SPDX-License-Identifier: AGPL-3.0-only
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent
VERSION = "0.4.0pre1"
STATE = ".body-only-installed.json"


def digest(data):
    return hashlib.sha256(data.decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")).hexdigest()


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError(f"Path is outside the installation directory: {relative}")
    return path


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".body-only-", delete=False) as handle:
        handle.write(content)
        name = handle.name
    os.replace(name, path)


def select_python(server, specified=None):
    if specified:
        candidate = Path(specified).expanduser().resolve()
        if not candidate.is_file():
            raise ValueError("The specified server Python executable does not exist")
        return str(candidate)
    for environment in (server.parent / ".server-venv", server / ".server-venv", server / ".venv"):
        for relative in ("Scripts/python.exe", "bin/python"):
            candidate = environment / relative
            if candidate.is_file():
                return str(candidate.resolve())
    return str(Path(sys.executable).resolve())


def install(server_dir, server_python=None, force=False, dry_run=False):
    server = Path(server_dir).expanduser().resolve()
    if not (server / "server.py").is_file():
        raise ValueError("Choose the directory containing the existing server.py")
    source = (server / "server.py").read_text(encoding="utf-8-sig")
    version = re.search(r'__version__\s*=\s*["\x27]([^"\x27]+)', source)
    if not version or version[1] != "4.1.7":
        raise ValueError("This release supports Zotero PDF2zh server 4.1.7 only")
    manifest = json.loads((ROOT / "compatibility.json").read_text(encoding="utf-8"))
    state_file = inside(server, STATE)
    if state_file.exists() and not force:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        if state.get("version") == VERSION and state.get("files") and all(
            inside(server, item["path"]).is_file()
            and digest(inside(server, item["path"]).read_bytes()) == item["after_sha256"]
            for item in state["files"]
        ):
            return {"status": "already_installed", "version": VERSION, "server_dir": str(server)}
        raise ValueError("An installation exists with local changes; restore it first or use --force")
    changes = {}
    for relative, info in manifest["files"].items():
        target = inside(server, relative)
        payload = inside(ROOT / "payload", relative).read_bytes()
        if digest(payload) != info["after_sha256"]:
            raise ValueError(f"Package integrity check failed: {relative}")
        if target.exists() and not force:
            existing = digest(target.read_bytes())
            allowed = {info["after_sha256"], info.get("before_sha256")}
            if existing not in allowed:
                raise ValueError(f"Unrecognized local changes in {relative}; review before --force")
        elif info.get("before_sha256") and not target.exists():
            raise ValueError(f"The upstream installation is incomplete: {relative}")
        changes[relative] = payload
    generated = {
        "run_body_only.py": (ROOT / "run_body_only.py").read_bytes(),
        "README.body-only.md": (ROOT / "README.md").read_text(encoding="utf-8").replace("(NOTICE.md)", "(NOTICE.body-only.md)").replace("(LICENSE)", "(LICENSE.body-only)").encode("utf-8"),
        "NOTICE.body-only.md": (ROOT / "NOTICE.md").read_bytes(),
        "LICENSE.body-only": (ROOT / "LICENSE").read_bytes(),
        ".body-only-launch.json": json.dumps(
            {"server_python": select_python(server, server_python)}, indent=2
        ).encode("utf-8"),
        "start-body-only.cmd": (
            '@echo off\r\nchcp 65001 >nul\r\n"' + select_python(server, server_python).replace('%', '%%')
            + '" "%~dp0run_body_only.py" --server-dir "%~dp0." %*\r\n'
            'if errorlevel 1 pause\r\n'
        ).encode("utf-8"),
    }
    for relative, content in generated.items():
        target = inside(server, relative)
        if target.exists() and not force and digest(target.read_bytes()) != digest(content):
            raise ValueError(f"Existing file would be replaced: {relative}")
        changes[relative] = content
    summary = {
        "status": "dry_run" if dry_run else "installed",
        "version": VERSION, "server_dir": str(server), "files": list(changes),
        "port": 8891,
    }
    if dry_run:
        return summary
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    backup = inside(server, ".body-only-backups/" + name)
    backup.mkdir(parents=True, exist_ok=False)
    records = []
    for relative, content in changes.items():
        target = inside(server, relative)
        record = {"path": relative, "existed": target.exists(), "after_sha256": digest(content)}
        if record["existed"]:
            original = target.read_bytes()
            record["before_sha256"] = digest(original)
            original_path = inside(backup, relative)
            original_path.parent.mkdir(parents=True, exist_ok=True)
            original_path.write_bytes(original)
        records.append(record)
    state = {"version": VERSION, "backup": str(backup.relative_to(server)), "files": records}
    (backup / "manifest.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    written = []
    try:
        for relative, content in changes.items():
            atomic_write(inside(server, relative), content)
            written.append(relative)
        atomic_write(state_file, json.dumps(state, indent=2).encode("utf-8"))
    except Exception:
        records_by_path = {record["path"]: record for record in records}
        for relative in reversed(written):
            target = inside(server, relative)
            if records_by_path[relative]["existed"]:
                atomic_write(target, inside(backup, relative).read_bytes())
            else:
                target.unlink(missing_ok=True)
        raise
    summary["backup"] = str(backup)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", required=True, help="Existing directory containing server.py")
    parser.add_argument("--server-python", help="Python executable that can already run the upstream server")
    parser.add_argument("--dry-run", action="store_true", help="Check compatibility without writing files")
    parser.add_argument("--force", action="store_true", help="Back up and replace locally modified supported files")
    args = parser.parse_args()
    try:
        result = install(args.server_dir, args.server_python, args.force, args.dry_run)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
