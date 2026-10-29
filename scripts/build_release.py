#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Build public release assets and a candidate channel without publishing it."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from install import VERSION
from build_plugin import build
from scripts.build_update_manifest import make_update


def build_release(tag, upstream=None, output=None):
    if tag != 'v' + VERSION or 'pre' in VERSION:
        raise ValueError('Release tag must match the stable backend version')
    output = Path(output or ROOT / 'dist' / tag)
    output.mkdir(parents=True, exist_ok=True)
    entry = json.loads((ROOT / 'downloads.json').read_text(encoding='utf-8'))['plugin']
    upstream = Path(upstream or ROOT / '.downloads' / entry['name'])
    if not upstream.exists():
        upstream.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(entry['url'], timeout=120) as response:
            upstream.write_bytes(response.read())
    xpi = output / f'zotero-pdf2zh-body-only-{tag}.xpi'
    build(upstream, xpi)
    update = make_update(xpi, tag)
    (output / 'updates.json').write_text(json.dumps(update, indent=2) + '\n', encoding='utf-8')
    # Git's tracked inventory excludes runtime files, credentials and PDFs.
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    source = output / f'zotero-pdf2zh-body-only-{tag}.zip'
    prefix = 'zotero-pdf2zh-body-only-' + tag + '/'
    with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(filter(None, names)):
            if name == 'updates.json':
                archive.writestr(prefix + name, json.dumps(update, indent=2) + '\n')
            else:
                archive.write(ROOT / name, prefix + name)
        archive.write(xpi, prefix + 'zotero-pdf2zh-body-only.xpi')
    (output / 'SHA256SUMS.txt').write_text(''.join(
        hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n' for path in (xpi, source)), encoding='ascii')
    print(json.dumps({'tag': tag, 'plugin': update['addons']['pdf2zh@guaguastandup.com']['updates'][0]['version'],
                      'directory': str(output)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--upstream-xpi')
    parser.add_argument('--output')
    args = parser.parse_args()
    build_release(args.tag, args.upstream_xpi, args.output)
