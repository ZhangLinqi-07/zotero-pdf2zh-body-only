# SPDX-License-Identifier: AGPL-3.0-only
# Body-only modifications by ZhangLinqi-07, 2026-10-21. See NOTICE.md.
"""Conservative, local detection of terminal references and appendix sections.

Only headings are recognized. A sentence mentioning an appendix, a contents
entry with a trailing page number, or an uncertain PDF is never a cutoff.
"""
from collections import Counter
from pathlib import Path
import json
import os
import re
import tempfile
import threading
import unicodedata

_LOCK = threading.Lock()
_PREFIX = r'(?:(?:\d+(?:\.\d+)*|[IVX]+)[.)]?\s+)?'
_REFERENCES = re.compile(_PREFIX + r'(?:references|bibliography|works cited|literature cited|参考文献|参考资料)\s*[:：.]?', re.I)
_APPENDIX = re.compile(_PREFIX + r'(?:appendix|appendices|supplementary materials?|supplemental materials?|supporting information|附录|补充材料)(?:\s+[A-Z0-9]+(?:[.:：]\s*[^\n]{1,100})?|\s*[:：]\s*[^\n]{1,100})?', re.I)


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, suffix='.tmp', delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        temporary = handle.name
    os.replace(temporary, path)


def read_settings(config_folder):
    path = Path(config_folder) / 'section_skip.json'
    if not path.exists():
        return {'enabled': True}
    settings = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(settings, dict) or not isinstance(settings.get('enabled'), bool):
        raise ValueError('section_skip.json must contain a boolean enabled field')
    return {'enabled': settings['enabled']}


def save_settings(config_folder, data):
    if not isinstance(data, dict) or set(data) != {'enabled'} or not isinstance(data['enabled'], bool):
        raise ValueError('Only the boolean enabled setting is accepted')
    with _LOCK:
        _write_json(Path(config_folder) / 'section_skip.json', data)
    return dict(data)


def _normal(text):
    return ' '.join(unicodedata.normalize('NFKC', text).split()).strip()


def heading_kind(text):
    text = _normal(text)
    if _REFERENCES.fullmatch(text):
        return 'references'
    if _APPENDIX.fullmatch(text):
        return 'appendix'
    return None


def _page_lines(page):
    lines = []
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            spans = line.get('spans', [])
            text = _normal(''.join(span.get('text', '') for span in spans))
            if not text:
                continue
            lines.append({
                'text': text, 'bbox': list(line['bbox']),
                'size': max((span.get('size', 0) for span in spans), default=0),
                'bold': any(span.get('flags', 0) & 16 or 'bold' in span.get('font', '').lower() for span in spans),
            })
    return lines


def detect_sections(input_path):
    import pymupdf

    with pymupdf.open(input_path) as document:
        plan = {'version': 1, 'filename': Path(input_path).name, 'total_pages': len(document), 'detected': False}
        candidates = []
        for index, page in enumerate(document):
            lines = _page_lines(page)
            counts = Counter()
            for line in lines:
                if len(line['text']) >= 20:
                    counts[round(line['size'], 1)] += len(line['text'])
            body_size = counts.most_common(1)[0][0] if counts else 10
            # The current boundary geometry is deliberately restricted to normal
            # pages; uncertain rotations/crop offsets retain the full document.
            if page.rotation or page.cropbox.x0 != 0 or page.cropbox.y0 != 0:
                continue
            for line in lines:
                kind = heading_kind(line['text'])
                if not kind or len(line['text']) > 125:
                    continue
                x0, y0, x1, y1 = line['bbox']
                if y0 < 15 or y1 > page.rect.height - 15:
                    continue
                # Protect abstracts, contents pages, and early mentions. A short
                # paper may place its references on page one below the body.
                if index < len(document) * .20 and not (index == 0 and y0 > page.rect.height * .55 and len(document) <= 3):
                    continue
                if not line['bold'] and line['size'] < body_size * 1.04:
                    continue
                mid = page.rect.width / 2
                weights = {'left': 0, 'right': 0, 'wide': 0}
                for item in lines:
                    if len(item['text']) < 20:
                        continue
                    left, _, right, _ = item['bbox']
                    column = 'left' if right <= mid + 8 else 'right' if left >= mid - 8 else 'wide'
                    weights[column] += len(item['text'])
                total = max(1, sum(weights.values()))
                columns = 2 if weights['left'] / total > .20 and weights['right'] / total > .20 and weights['wide'] / total < .20 else 1
                column = 'full'
                if columns == 2 and not (x0 < mid < x1):
                    column = 'left' if x0 < mid else 'right'
                candidates.append({
                    'page': index + 1, 'heading': line['text'], 'kind': kind,
                    'y': y0, 'x': x0, 'width': page.rect.width,
                    'height': page.rect.height, 'column': column,
                })
        if candidates:
            # Column reading order is left-to-right, then top-to-bottom within
            # each column. Full-width headings use their normal vertical order.
            first_page = min(item['page'] for item in candidates)
            on_page = [item for item in candidates if item['page'] == first_page]
            first = min(on_page, key=lambda item: (item['column'] == 'right', item['y']))
            plan.update(detected=True, boundary=first,
                        first_fully_skipped_page=first_page + 1,
                        fully_skipped_pages=max(0, len(document) - first_page))
        return plan


def should_skip_paragraph(page_number, box, plan):
    """IL boxes have bottom-left coordinates; detector coordinates are top-left."""
    if not plan.get('detected'):
        return False
    boundary = plan['boundary']
    if page_number + 1 > boundary['page']:
        return True
    if page_number + 1 < boundary['page'] or box is None:
        return False
    if any(getattr(box, name, None) is None for name in ('x', 'x2', 'y2')):
        return False
    top = boundary['height'] - box.y2
    middle_x = (box.x + box.x2) / 2
    column = boundary['column']
    if column == 'left' and middle_x >= boundary['width'] / 2:
        return True
    if column == 'right' and middle_x < boundary['width'] / 2:
        return False
    # A paragraph intersecting both sides of the heading is retained to avoid
    # silently dropping preceding body content. This is recorded by tests/docs.
    return top >= boundary['y'] - 3


def prepare_translation_command(command, input_path, config_folder, skip_last_pages=0, request_override=None, task_id=None):
    settings = read_settings(config_folder)
    enabled = settings['enabled'] if request_override is None else request_override
    if not isinstance(enabled, bool):
        raise ValueError('skipReferencesAndAppendices must be a boolean')
    if not enabled:
        return command, None
    plan = detect_sections(input_path)
    _write_json(Path(config_folder) / 'last_section_plan.json', plan)
    if not plan['detected']:
        print('[section-skip] No confident terminal section heading found; retaining the original translation range.')
        return command, plan
    # This custom path guarantees that unselected original pages remain in output.
    if '--only-include-translated-page' in command:
        raise ValueError('Section skipping preserves original end pages and cannot be combined with only-include-translated-page')
    end_page = min(plan['boundary']['page'], plan['total_pages'] - max(0, int(skip_last_pages)))
    if end_page < 1:
        raise ValueError('The selected page range contains no body pages')
    result = list(command)
    if '--pages' in result:
        index = result.index('--pages')
        del result[index:index + 2]
    result += ['--pages', f'1-{end_page}']
    folder = Path(config_folder) / 'section_plans'
    # A fresh plan belongs to one job; concurrent jobs never share a cutoff.
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', prefix='plan-', dir=folder, encoding='utf-8', delete=False) as handle:
        json.dump(plan, handle, ensure_ascii=False)
        plan_path = handle.name
    result += ['--zotero-section-skip-plan', plan_path]
    boundary = plan['boundary']
    print(f"[section-skip] {boundary['heading']} on PDF page {boundary['page']}; translating body through the boundary page and preserving later pages in the original language.")
    return result, plan


def prepare_runtime_command(command):
    """Wrap only this invocation, leaving the installed translation engine intact."""
    marker = '--zotero-section-skip-plan'
    if marker not in command:
        return command
    result = list(command)
    index = result.index(marker)
    plan = result[index + 1]
    del result[index:index + 2]
    executable = Path(result[0])
    if executable.name.lower() in ('pdf2zh_next', 'pdf2zh_next.exe'):
        python = executable.with_name('python.exe' if os.name == 'nt' else 'python')
        if not python.is_file():
            raise RuntimeError('The section filter requires a Python-managed pdf2zh_next environment')
        engine_args = result[1:]
    elif '-m' in result and result[result.index('-m') + 1] == 'pdf2zh_next':
        python = executable
        engine_args = result[result.index('-m') + 2:]
    else:
        raise RuntimeError('Unsupported pdf2zh_next command for the section filter')
    return [str(python), '-u', str(Path(__file__).with_name('section_skip_runtime.py')), '--plan', plan, '--', *engine_args]
