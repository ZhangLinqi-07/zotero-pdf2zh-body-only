#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Build the backend carried by an XPI from public source files only."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build_bytes(root=ROOT):
    root = Path(root)
    from install import VERSION
    compatibility = json.loads((root / 'compatibility.json').read_text(encoding='utf-8'))
    files = {}
    for relative, entry in compatibility['files'].items():
        source = root / 'payload' / relative
        data = source.read_text(encoding='utf-8-sig').replace('\r\n', '\n').encode('utf-8')
        if hashlib.sha256(data).hexdigest() != entry['after_sha256']:
            raise ValueError('Refresh compatibility.json before building: ' + relative)
        files[relative] = data
    for source, target in [('run_body_only.py', 'run_body_only.py'), ('README.md', 'README.body-only.md'),
                           ('NOTICE.md', 'NOTICE.body-only.md'), ('LICENSE', 'LICENSE.body-only')]:
        text = (root / source).read_text(encoding='utf-8-sig').replace('\r\n', '\n')
        if source == 'README.md':
            text = text.replace('(NOTICE.md)', '(NOTICE.body-only.md)').replace('(LICENSE)', '(LICENSE.body-only)')
        files[target] = text.encode('utf-8')
    metadata = {'schema': 1, 'backendVersion': VERSION,
                'compatibility': {key: compatibility[key] for key in ('upstream_version', 'pdf2zh_next', 'babeldoc')},
                'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
                          for name, data in sorted(files.items())}}
    files['kinbo-backend.json'] = (json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            item = zipfile.ZipInfo(name, (2026, 10, 29, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, data)
    content = output.getvalue()
    return content, {'schema': 1, 'backendVersion': VERSION,
                     'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    content, info = build_bytes()
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    print(json.dumps(info))
