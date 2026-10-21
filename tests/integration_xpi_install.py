#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Install the actual release XPI in a separate native Zotero profile."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zotero', required=True)
    parser.add_argument('--old-xpi', required=True)
    parser.add_argument('--new-xpi', required=True)
    parser.add_argument('--output-dir')
    options = parser.parse_args()
    folder = Path(options.output_dir or tempfile.mkdtemp(prefix='kinbo-xpi-install-')).resolve()
    profile, data = folder / 'profile', folder / 'data'
    if profile.exists():
        raise ValueError('Choose a new output directory for an isolated profile')
    (profile / 'extensions').mkdir(parents=True)
    data.mkdir()
    prefs = {'extensions.zotero.useDataDir': True, 'extensions.zotero.dataDir': str(data),
             'extensions.zotero.firstRun.skip': True, 'extensions.zotero.firstRun2': False,
             'extensions.zotero.automaticScraperUpdates': False, 'extensions.autoDisableScopes': 0,
             'extensions.enabledScopes': 15, 'extensions.update.enabled': False,
             'extensions.zotero.httpServer.enabled': False, 'extensions.zotero.httpServer.localAPI.enabled': False,
             'extensions.zoteroWinWordIntegration.skipInstallation': True,
             'extensions.zoteroOpenOfficeIntegration.skipInstallation': True,
             'app.update.auto': False, 'browser.shell.checkDefaultBrowser': False,
             'toolkit.telemetry.enabled': False}
    (profile / 'user.js').write_text(''.join('user_pref(' + json.dumps(k) + ', ' + json.dumps(v) + ');\n' for k, v in prefs.items()), encoding='utf-8')
    result = folder / 'result.json'
    constants = {'TEST_RESULT_PATH': str(result), 'TEST_OLD_XPI': str(Path(options.old_xpi).resolve()),
                 'TEST_NEW_XPI': str(Path(options.new_xpi).resolve())}
    bootstrap = ''.join('var ' + key + ' = ' + json.dumps(value) + ';\n' for key, value in constants.items())
    bootstrap += Path(__file__).with_name('xpi_install_bootstrap.js').read_text(encoding='utf-8')
    metadata = {'manifest_version': 2, 'name': 'Isolated native XPI install regression', 'version': '1.0',
                'applications': {'zotero': {'id': 'kinbo-install-check@local.invalid',
                  'update_url': 'https://example.invalid/updates.json', 'strict_min_version': '10.0', 'strict_max_version': '10.0.*'}}}
    with zipfile.ZipFile(profile / 'extensions/kinbo-install-check@local.invalid.xpi', 'w') as archive:
        archive.writestr('manifest.json', json.dumps(metadata))
        archive.writestr('bootstrap.js', bootstrap)
    startup = None
    if os.name == 'nt':
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
    with (folder / 'zotero.log').open('wb') as log:
        process = subprocess.Popen([options.zotero, '-no-remote', '-profile', str(profile), '-ZoteroDebugText', '-purgecaches'],
                                   stdout=log, stderr=subprocess.STDOUT, startupinfo=startup)
        try:
            # Windows launchers can exit while their new application process
            # continues. Wait for the isolated adapter's result, not the launcher.
            deadline = time.monotonic() + 90
            while not result.exists() and time.monotonic() < deadline:
                time.sleep(.2)
            if not result.exists():
                raise subprocess.TimeoutExpired(process.args, 90)
            if process.poll() is None:
                process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            # Only the process created for this disposable profile is terminated.
            process.terminate()
            process.wait(timeout=15)
            raise RuntimeError(f'Native install test timed out; see {folder / "zotero.log"}')
    if not result.exists():
        raise RuntimeError(f'Native test did not start; see {folder / "zotero.log"}')
    report = json.loads(result.read_text(encoding='utf-8'))
    print(json.dumps(report, ensure_ascii=False))
    if report.get('status') != 'passed':
        raise RuntimeError('Native Zotero XPI installation failed')


if __name__ == '__main__':
    main()
