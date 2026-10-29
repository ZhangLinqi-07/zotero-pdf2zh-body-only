#!/usr/bin/env python3
"""Launch an existing, patched PDF2zh server on a separate loopback port."""
# SPDX-License-Identifier: AGPL-3.0-only
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--python", dest="server_python")
    parser.add_argument("--port", type=int, default=8891)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    server = Path(args.server_dir).expanduser().resolve()
    if not (server / "server.py").is_file():
        parser.error("server.py was not found in --server-dir")
    config = server / ".body-only-launch.json"
    settings = json.loads(config.read_text(encoding="utf-8")) if config.exists() else {}
    python = args.server_python or settings.get("server_python") or sys.executable
    logs = server / "body-only-logs"
    logs.mkdir(exist_ok=True)
    lock = (logs / f"service-{args.port}.lock").open("a+b")
    lock.seek(0)
    if not lock.read(1):
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("The launcher for this port is already running.")
        return
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/section-settings", timeout=2) as response:
            if json.load(response).get("status") == "success":
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/capabilities", timeout=2) as check:
                        version = json.load(check).get('version')
                except (OSError, ValueError):
                    version = None
                if version == '0.4.0pre1':
                    print(f"Body-only server is already available on port {args.port}.")
                    return
                raise SystemExit('An older body-only service uses this port. Close its window, or choose --port 8892.')
    except (OSError, ValueError):
        pass
    env = os.environ.copy()
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    tools = server.parent / ".tools" / "bin"
    if tools.is_dir():
        env["PATH"] = str(tools) + os.pathsep + env.get("PATH", "")
    runtime = server.parent / "runtime"
    if runtime.is_dir():
        env.setdefault("UV_PYTHON_INSTALL_DIR", str(runtime))
    command = [
        str(python), "-u", str(server / "server.py"), "--host=127.0.0.1",
        f"--port={args.port}", "--check_update=False", "--update_source=github",
    ]
    print(f"Starting body-only server at http://127.0.0.1:{args.port}/")
    print(f"Logs are in {logs}")
    with (logs / f"server-{args.port}.log").open("ab") as stdout, (logs / f"server-{args.port}-error.log").open("ab") as stderr:
        process = subprocess.Popen(
            command, cwd=server, env=env, stdin=subprocess.DEVNULL,
            stdout=stdout, stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        (logs / f"server-{args.port}.pid").write_text(str(process.pid), encoding="ascii")
        result = process.wait()
    if result:
        raise SystemExit(f"Server exited with {result}. Check the log files.")


if __name__ == "__main__":
    main()
