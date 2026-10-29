#!/usr/bin/env python3
"""Restore files changed by a body-only patch installation."""
# SPDX-License-Identifier: AGPL-3.0-only
import argparse
import json
from pathlib import Path
from install import STATE, atomic_write, digest, inside


def restore(server_dir, force=False):
    server = Path(server_dir).expanduser().resolve()
    state_path = inside(server, STATE)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    backup = inside(server, state["backup"])
    for record in state["files"]:
        target = inside(server, record["path"])
        if target.exists() and not force and digest(target.read_bytes()) != record["after_sha256"]:
            raise ValueError(f"File changed after installation: {record['path']}")
        if record["existed"]:
            original = inside(backup, record["path"]).read_bytes()
            if digest(original) != record["before_sha256"]:
                raise ValueError(f"Backup integrity check failed: {record['path']}")
    for record in reversed(state["files"]):
        target = inside(server, record["path"])
        if record["existed"]:
            atomic_write(target, inside(backup, record["path"]).read_bytes())
        elif target.exists():
            target.unlink()
    if (backup / 'installed-state.json').is_file():
        atomic_write(state_path, (backup / 'installed-state.json').read_bytes())
        info = backup / 'backend-info.json'
        if info.is_file():
            atomic_write(server / '.kinbo-backend.json', info.read_bytes())
        else:
            (server / '.kinbo-backend.json').unlink(missing_ok=True)
    else:
        state_path.unlink()
    return {"status": "restored", "server_dir": str(server), "backup_retained": str(backup)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", required=True)
    parser.add_argument("--force", action="store_true", help="Replace files edited after installation")
    args = parser.parse_args()
    try:
        result = restore(args.server_dir, args.force)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
