#!/usr/bin/env python3
"""Install upstream components and the body-only service into a fresh directory."""
# SPDX-License-Identifier: AGPL-3.0-only
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

import install

ROOT = Path(__file__).resolve().parent
MARKER = ".body-only-bootstrap.json"
APPLICATION = "zotero-pdf2zh-body-only"
ENGINE_PACKAGES = [
    "pdf2zh-next==2.9.0", "BabelDOC==0.6.2", "bitstring>=4.3,<5",
    "flask>=3,<4", "pypdf>=6,<7", "toml==0.10.2", "packaging>=24,<27",
]
SERVER_PACKAGES = [
    "flask>=3,<4", "toml==0.10.2", "pypdf>=6,<7",
    "PyMuPDF==1.25.2", "packaging>=24,<27",
]


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(handle.read()).hexdigest()


def checked_asset(info, cache, local=None):
    """Use only the versioned upstream asset whose digest is pinned in source."""
    if local:
        path = Path(local).expanduser().resolve()
        if sha256(path) != info["sha256"]:
            raise ValueError(f"Upstream SHA256 mismatch: {path.name}")
        return path
    path = cache / info["name"]
    if path.exists() and sha256(path) == info["sha256"]:
        return path
    cache.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    print(f"Downloading {info['name']} ...", flush=True)
    request = urllib.request.Request(info["url"], headers={"User-Agent": APPLICATION})
    with urllib.request.urlopen(request, timeout=30) as response, partial.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    if sha256(partial) != info["sha256"]:
        raise ValueError(f"Downloaded SHA256 mismatch: {info['name']}")
    os.replace(partial, path)
    return path


def extract_server(archive_path, destination):
    """Preflight every member before extracting a verified upstream ZIP."""
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive_path) as archive:
        seen = set()
        for item in archive.infolist():
            name = item.filename
            parts = PurePosixPath(name).parts
            mode = item.external_attr >> 16
            if (not parts or parts[0] != "server" or ".." in parts
                    or "\\" in name or ":" in name or name.startswith("/")
                    or stat.S_ISLNK(mode)):
                raise ValueError(f"Unsafe ZIP member: {name}")
            install.inside(destination, name)
            key = name.rstrip("/").casefold()
            if key in seen:
                raise ValueError(f"Duplicate ZIP member: {name}")
            seen.add(key)
        if "server/server.py" not in seen:
            raise ValueError("The archive does not contain server/server.py")
        archive.extractall(destination)


def claim_directory(target):
    target = Path(target).expanduser().resolve()
    marker = target / MARKER
    if marker.exists():
        data = json.loads(marker.read_text(encoding="utf-8"))
        if data.get("application") != APPLICATION:
            raise ValueError("This installation directory belongs to another application")
    elif target.exists() and any(target.iterdir()):
        raise ValueError("Choose an empty directory. Use install.py for an existing server")
    else:
        target.mkdir(parents=True, exist_ok=True)
        install.atomic_write(marker, json.dumps({"application": APPLICATION, "version": install.VERSION}).encode())
    return target


def configure_engine(server):
    """Pin compatible defaults only in this fresh installation."""
    example = server / "config/venv.json.example"
    target = server / "config/venv.json"
    config = json.loads((target if target.exists() else example).read_text(encoding="utf-8-sig"))
    for tool in ("uv", "conda"):
        config.setdefault("pdf2zh_next", {})[tool] = {
            "python_version": "3.12", "packages": ENGINE_PACKAGES,
        }
    install.atomic_write(target, json.dumps(config, indent=2).encode("utf-8"))
    install.atomic_write(example, json.dumps(config, indent=2).encode("utf-8"))


def prepare_sources(target, server_archive=None, plugin_xpi=None):
    target = claim_directory(target)
    assets = json.loads((ROOT / "downloads.json").read_text(encoding="utf-8"))
    server = target / "server"
    if not server.exists():
        archive = checked_asset(assets["server"], target / ".downloads", server_archive)
        with tempfile.TemporaryDirectory(prefix="unpack-", dir=target) as temp:
            extract_server(archive, temp)
            Path(temp, "server").rename(server)
    elif not (server / "server.py").is_file():
        raise ValueError("The managed server directory is incomplete; choose a new install directory")
    plugin = checked_asset(assets["plugin"], target / ".downloads", plugin_xpi)
    destination = target / assets["plugin"]["name"]
    if destination.exists() and sha256(destination) != assets["plugin"]["sha256"]:
        raise ValueError("The existing XPI has local changes")
    if plugin != destination:
        shutil.copy2(plugin, destination)
    configure_engine(server)
    return target, server, destination


def run(command, env, capture=False):
    result = subprocess.run([str(item) for item in command], env=env, check=True,
                            text=True, encoding="utf-8", capture_output=capture)
    return result.stdout.strip() if capture else None


def venv_python(environment):
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def prepare_environments(target, uv_path, index_url, defer_engine=False):
    uv_path = Path(uv_path).expanduser().resolve()
    if not uv_path.is_file():
        raise ValueError("uv was not found. Windows users can run install-windows.cmd")
    tools = target / ".tools/bin"
    tools.mkdir(parents=True, exist_ok=True)
    uv = tools / ("uv.exe" if os.name == "nt" else "uv")
    if uv_path != uv:
        shutil.copy2(uv_path, uv)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", UV_PYTHON_INSTALL_DIR=str(target / "runtime"),
               UV_PYTHON_BIN_DIR=str(target / ".tools/python-bin"), UV_DEFAULT_INDEX=index_url,
               UV_NO_CONFIG="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    print("Preparing private Python 3.12 ...", flush=True)
    run([uv, "python", "install", "3.12", "--no-bin", "--no-registry"], env)
    python = run([uv, "python", "find", "--managed-python", "3.12"], env, capture=True)
    server_python = venv_python(target / ".server-venv")
    environments = [(target / ".server-venv", SERVER_PACKAGES)]
    if not defer_engine:
        environments.append((target / "server/zotero-pdf2zh-next-venv", ENGINE_PACKAGES))
    for environment, packages in environments:
        executable = venv_python(environment)
        if not executable.is_file():
            run([uv, "venv", "--python", python, environment], env)
        run([executable, "-m", "ensurepip", "--upgrade"], env)
        print(f"Installing dependencies in {environment.name} ...", flush=True)
        run([executable, "-m", "pip", "install", "--no-compile", "--index-url", index_url, *packages], env)
        run([executable, "-m", "pip", "check"], env)
    # Metadata checks avoid downloading model weights or contacting translation APIs.
    if not defer_engine:
        run([venv_python(environments[-1][0]), "-I", "-c",
             "from importlib.metadata import version; from bitstring import BitStream; "
             "assert version('pdf2zh-next') == '2.9.0'; assert version('BabelDOC') == '0.6.2'"], env)
    return server_python


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-dir", default=str(ROOT / "app"), help="Empty directory, or a previous setup_fresh.py installation")
    parser.add_argument("--uv", default=shutil.which("uv") or str(ROOT / ".bootstrap/bin/uv.exe"))
    parser.add_argument("--index-url", default="https://pypi.org/simple")
    parser.add_argument("--server-archive", help="Previously downloaded, unmodified upstream server ZIP")
    parser.add_argument("--plugin-xpi", help="Previously downloaded, unmodified upstream XPI")
    parser.add_argument("--defer-engine", action="store_true", help="Install the translation engine on first use instead")
    parser.add_argument("--start", action=argparse.BooleanOptionalAction, default=False, help="Start the local service after installation")
    args = parser.parse_args()
    try:
        target, server, plugin = prepare_sources(args.install_dir, args.server_archive, args.plugin_xpi)
        python = prepare_environments(target, args.uv, args.index_url, args.defer_engine)
        result = install.install(server, server_python=python)
        if os.name == "nt":
            # The wrapper remains usable when Python is absent from the user's PATH.
            # chcp also makes UTF-8 installation paths work in cmd.exe.
            command = '@echo off\r\nchcp 65001 >nul\r\ncall "%~dp0server\\start-body-only.cmd" %*\r\n'
            install.atomic_write(target / "start-body-only.cmd", command.encode("utf-8"))
        result.update(plugin_file=str(plugin), engine_deferred=args.defer_engine)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("Install the XPI in Zotero's Add-ons window.")
        print("Set PDF2zh server URL to http://127.0.0.1:8891 and engine to pdf2zh_next.")
        print("Free translation or your own API can be selected in Zotero.")
        print("Keep this installation folder in place. First translation may download model assets.")
        if args.start:
            subprocess.run([str(python), str(server / "run_body_only.py"), "--server-dir", str(server)], check=True)
    except (OSError, ValueError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Installation stopped. Run again to resume. {error}\n")


if __name__ == "__main__":
    main()
