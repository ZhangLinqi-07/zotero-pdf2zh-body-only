#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Create the Zotero update document for a verified, published fork XPI."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_plugin import UPDATE_URL, MAX_ZOTERO_VERSION, PLUGIN_VERSION


def make_update(plugin, tag):
    plugin = Path(plugin)
    if not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise ValueError('Use a release tag such as v0.3.5')
    with zipfile.ZipFile(plugin) as archive:
        metadata = json.loads(archive.read('manifest.json'))
        bootstrap = archive.read('bootstrap.js')
    app = metadata['applications']['zotero']
    if app.get('id') != 'pdf2zh@guaguastandup.com' or metadata['version'] != PLUGIN_VERSION:
        raise ValueError('The XPI identity or version does not match this release')
    if app.get('update_url') != UPDATE_URL or app.get('strict_max_version') != MAX_ZOTERO_VERSION:
        raise ValueError('The XPI is missing the fork update channel or tested compatibility')
    if b'BodyOnlyLocalServer =' in bootstrap:
        raise ValueError('Publish a public XPI without a local server preference override')
    return {'addons': {app['id']: {'updates': [{
        'version': metadata['version'],
        'update_link': f'https://github.com/ZhangLinqi-07/zotero-pdf2zh-body-only/releases/download/{tag}/zotero-pdf2zh-body-only-{tag}.xpi',
        'update_hash': 'sha256:' + hashlib.sha256(plugin.read_bytes()).hexdigest(),
        'applications': {'zotero': {name: app[name] for name in ('strict_min_version', 'strict_max_version')}},
    }]}}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xpi', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', default=str(ROOT / 'updates.json'))
    args = parser.parse_args()
    Path(args.output).write_text(json.dumps(make_update(args.xpi, args.tag), indent=2) + '\n', encoding='utf-8')
    print('Wrote verified Zotero update manifest')
