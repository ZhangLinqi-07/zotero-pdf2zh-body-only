#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise Kinbo chat UI against native PDF.js in a disposable Zotero profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import zipfile

import pymupdf

ROOT = Path(__file__).resolve().parents[1]


def stop_isolated_process(process, profile):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
    if os.name == 'nt':
        # Windows launchers may exit before their application child. Match only
        # this fresh profile's absolute path, never the user's normal Zotero.
        script = """$targetProfile = $env:KINBO_NATIVE_TEST_PROFILE
Get-CimInstance Win32_Process -Filter \"Name='zotero.exe'\" | Where-Object {
  $_.CommandLine -and $_.CommandLine.IndexOf($targetProfile, [StringComparison]::OrdinalIgnoreCase) -ge 0
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
"""
        env = dict(os.environ, KINBO_NATIVE_TEST_PROFILE=str(profile.resolve()))
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                       env=env, capture_output=True, timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zotero', required=True)
    parser.add_argument('--xpi', required=True)
    parser.add_argument('--output-dir')
    options = parser.parse_args()
    folder = Path(options.output_dir or tempfile.mkdtemp(prefix='kinbo-chat-reader-')).resolve()
    profile, data = folder / 'profile', folder / 'data'
    if profile.exists() or data.exists():
        raise ValueError('Use a new directory for the isolated profile and database')
    (profile / 'extensions').mkdir(parents=True)
    data.mkdir()
    pdf_path = folder / 'synthetic-reader.pdf'
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        page.insert_text((60, 80), 'KINBO_FIRST_PAGE_SENTINEL', fontsize=15)
        page.insert_text((60, 115), 'This first page remains part of the complete paper.', fontsize=11)
        page = document.new_page(width=612, height=792)
        page.insert_text((60, 80), 'KINBO_FINAL_PAGE_SENTINEL', fontsize=15)
        page.insert_text((60, 115), 'Exact evidence sentence appears here only once.', fontsize=11)
        document.save(pdf_path)
    prefs = {
        'extensions.zotero.useDataDir': True, 'extensions.zotero.dataDir': str(data),
        'extensions.zotero.firstRun.skip': True, 'extensions.zotero.firstRun2': False,
        'extensions.zotero.automaticScraperUpdates': False,
        'extensions.autoDisableScopes': 0, 'extensions.enabledScopes': 15,
        'extensions.update.enabled': False, 'extensions.zotero.httpServer.enabled': False,
        'extensions.zotero.httpServer.localAPI.enabled': False,
        'extensions.zoteroWinWordIntegration.skipInstallation': True,
        'extensions.zoteroOpenOfficeIntegration.skipInstallation': True,
        'extensions.zotero.pdf2zh.new_serverip': 'http://127.0.0.1:19731',
        'extensions.zotero.pdf2zh.bodyOnlyServerMigrated_0_3_0': True,
        'app.update.auto': False, 'browser.shell.checkDefaultBrowser': False,
        'toolkit.telemetry.enabled': False,
    }
    (profile / 'user.js').write_text(''.join('user_pref(' + json.dumps(key) + ', ' + json.dumps(value) + ');\n'
                                           for key, value in prefs.items()), encoding='utf-8')
    result = folder / 'result.json'
    xpi_path = Path(options.xpi).resolve()
    chat_source = folder / 'packaged-kinbo-paper-chat.js'
    with zipfile.ZipFile(xpi_path) as archive:
        chat_source.write_bytes(archive.read('content/scripts/kinbo-paper-chat.js'))
    constants = {'CHAT_TEST_RESULT': str(result), 'CHAT_TEST_XPI': str(Path(options.xpi).resolve()),
                 'CHAT_TEST_PDF': str(pdf_path), 'CHAT_TEST_SOURCE': str(chat_source),
                 'CHAT_TEST_XPI_HASH': hashlib.sha256(xpi_path.read_bytes()).hexdigest()}
    bootstrap = ''.join('var ' + key + ' = ' + json.dumps(value) + ';\n' for key, value in constants.items())
    bootstrap += Path(__file__).with_name('chat_reader_bootstrap.js').read_text(encoding='utf-8')
    metadata = {'manifest_version': 2, 'name': 'Isolated Kinbo native PDF reader check', 'version': '1.0',
                'applications': {'zotero': {'id': 'kinbo-chat-reader-check@local.invalid',
                 'update_url': 'https://example.invalid/updates.json', 'strict_min_version': '10.0',
                 'strict_max_version': '10.0.*'}}}
    with zipfile.ZipFile(profile / 'extensions/kinbo-chat-reader-check@local.invalid.xpi', 'w') as archive:
        archive.writestr('manifest.json', json.dumps(metadata))
        archive.writestr('bootstrap.js', bootstrap)
    startup, flags = None, 0
    if os.name == 'nt':
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        flags = subprocess.CREATE_NO_WINDOW
    with (folder / 'zotero.log').open('wb') as log:
        process = subprocess.Popen([options.zotero, '-no-remote', '-profile', str(profile), '-ZoteroDebugText', '-purgecaches'],
                                   stdout=log, stderr=subprocess.STDOUT, startupinfo=startup, creationflags=flags)
        deadline = time.monotonic() + 82
        try:
            while not result.exists() and time.monotonic() < deadline:
                time.sleep(.2)
            if not result.exists():
                report = {'status': 'failed', 'stage': 'native-startup-or-timeout',
                          'error': 'The isolated harness did not return within 82 seconds',
                          'log': str(folder / 'zotero.log'), 'userProfileUsed': False,
                          'externalModelCalls': 0}
                result.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            else:
                report = json.loads(result.read_text(encoding='utf-8'))
            if process.poll() is None:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            stop_isolated_process(process, profile)
    print(json.dumps({**report, 'resultFile': str(result)}, ensure_ascii=False))
    if report.get('status') != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
