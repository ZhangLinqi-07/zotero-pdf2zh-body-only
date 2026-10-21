#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Refresh normalized source checksums after editing the install payload."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'compatibility.json').read_text(encoding='utf-8'))
files = {}
def digest(path):
    return hashlib.sha256(path.read_text(encoding='utf-8-sig').replace('\r\n', '\n').encode('utf-8')).hexdigest()
for path in sorted((root / 'payload').rglob('*')):
    if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
        continue
    relative = path.relative_to(root / 'payload').as_posix()
    info = {'after_sha256': digest(path)}
    before = root / 'upstream' / relative
    if before.is_file():
        info['before_sha256'] = digest(before)
    files[relative] = info
manifest['files'] = files
(root / 'compatibility.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(f'Refreshed {len(files)} payload file checksums')
