# SPDX-License-Identifier: AGPL-3.0-only
"""Keep complete translations on linked continuation pages when layout is full."""
from collections import defaultdict
import html
import io
import json
from pathlib import Path
import re
import tempfile

import pymupdf


def paragraph_runs(paragraph, page_number):
    runs = []
    for item in paragraph.pdf_paragraph_composition:
        if item.pdf_formula is not None:
            formula = item.pdf_formula
            if formula.box is None:
                raise RuntimeError('Formula in continuation has no bounding box')
            runs.append({'formula': {'page': page_number,
                                    'box': [getattr(formula.box, k) for k in ('x', 'y', 'x2', 'y2')]}})
        elif item.pdf_same_style_unicode_characters is not None:
            runs.append({'text': item.pdf_same_style_unicode_characters.unicode or ''})
        else:
            group = item.pdf_line or item.pdf_same_style_characters
            chars = group.pdf_character if group is not None else [item.pdf_character]
            if any(char is None for char in chars):
                raise RuntimeError('Unsupported continuation composition')
            runs.append({'text': ''.join(char.char_unicode or '' for char in chars)})
    return runs


def continuation_pdf(entries, source, width, height):
    """Story carries all text forward, including across columns and pages."""
    with tempfile.TemporaryDirectory(prefix='kinbo-continuation-') as temporary:
        folder = Path(temporary)
        (folder / 'cjk.ttf').write_bytes(pymupdf.Font('cjk').buffer)
        fragments = []
        for number, entry in enumerate(entries, 1):
            pieces = []
            for index, run in enumerate(entry['runs']):
                if 'text' in run:
                    pieces.append(html.escape(run['text']))
                else:
                    formula = run['formula']
                    page = source[formula['page']]
                    x0, y0, x1, y1 = formula['box']
                    clip = pymupdf.Rect(x0, page.rect.height - y1, x1, page.rect.height - y0) & page.rect
                    if clip.is_empty:
                        raise RuntimeError('Formula continuation crop is empty')
                    name = f'math-{number}-{index}.png'
                    page.get_pixmap(matrix=pymupdf.Matrix(4, 4), clip=clip, alpha=True).save(folder / name)
                    scale = min(1, (width / 2 - 46) / clip.width, (height - 100) / clip.height)
                    pieces.append(f'<img src="{name}" style="width:{clip.width * scale}pt;height:{clip.height * scale}pt;vertical-align:middle">')
            fragments.append(f'<p id="entry-{number}"><b>[{number}] </b>{"".join(pieces)}</p>')
        css = '@font-face{font-family:Kinbo;src:url(cjk.ttf)} body{font-family:Kinbo;font-size:10pt;line-height:1.35} p{margin:0 0 10pt} img{max-width:100%}'
        story = pymupdf.Story(html=''.join(fragments), user_css=css, archive=pymupdf.Archive(str(folder)))
        buffer = io.BytesIO()
        writer = pymupdf.DocumentWriter(buffer)
        more = True
        while more:
            device = writer.begin_page(pymupdf.Rect(0, 0, width, height))
            mid = width / 2
            for rect in (pymupdf.Rect(34, 54, mid - 10, height - 36), pymupdf.Rect(mid + 10, 54, width - 34, height - 36)):
                more, filled = story.place(rect)
                if more and pymupdf.Rect(filled).is_empty:
                    writer.end_page()
                    writer.close()
                    raise RuntimeError('Continuation content cannot fit in an empty column')
                story.draw(device)
                if not more:
                    break
            writer.end_page()
        writer.close()
    return pymupdf.open(stream=buffer.getvalue(), filetype='pdf')


def add_continuations(path, source_path, entries, mode='dual', alternating=False):
    """Create a complete replacement first; preserve the previous PDF on error."""
    path = Path(path)
    grouped = defaultdict(list)
    for entry in entries:
        grouped[entry['page']].append(entry)
    if not grouped:
        return {'inline': 0, 'continued': 0}
    stats = {'inline': 0, 'continued': 0}
    with pymupdf.open(path) as translated, pymupdf.open(source_path) as source, pymupdf.open() as result:
        expected_pages = len(source) * (2 if mode == 'dual' and alternating else 1)
        if len(translated) != expected_pages:
            raise RuntimeError('Continuation mapping requires all original pages in output')
        for index, page in enumerate(source):
            width, height = page.rect.width, page.rect.height
            base = len(result)
            start = index * 2 if mode == 'dual' and alternating else index
            end = start + (1 if mode == 'dual' and alternating else 0)
            result.insert_pdf(translated, from_page=start, to_page=end)
            current = grouped.get(index, [])
            if not current:
                continue
            main_index = base + (1 if mode == 'dual' and alternating else 0)
            main = result[main_index]
            offset = width if mode == 'dual' and not alternating else 0
            remaining = []
            for entry in current:
                x0, y0, x1, y1 = entry['box']
                rect = pymupdf.Rect(x0 + offset, height - y1, x1 + offset, height - y0)
                text = ''.join(run.get('text', '') for run in entry['runs'])
                only_text = all('text' in run for run in entry['runs'])
                placed = False
                if only_text and 0 < len(text) <= 40 and 0 < rect.height <= 14 and 0 < rect.width <= 100:
                    font_size = entry.get('fontSize') or rect.height
                    css = f'*{{margin:0;padding:0}} body{{font-family:sans-serif;font-size:{font_size}pt;line-height:1}}'
                    spare, _ = main.insert_htmlbox(rect, '<div>' + html.escape(text) + '</div>', css=css, scale_low=.55)
                    placed = spare >= 0
                if placed:
                    stats['inline'] += 1
                else:
                    remaining.append(entry)
            current = remaining
            if not current:
                continue
            stats['continued'] += len(current)
            first_continuation = len(result) + (1 if mode == 'dual' and alternating else 0)
            markers = []
            for number, entry in enumerate(current, 1):
                x0, y0, x1, y1 = entry['box']
                rect = pymupdf.Rect(x0 + offset, height - y1, x1 + offset, height - y0)
                label = f'[{number}]'
                font = max(3, min(8, rect.height * .75, rect.width / max(1, len(label)) * 1.5))
                main.insert_text((rect.x0, rect.y0 + font), label, fontsize=font, color=(0, .25, .7))
                markers.append(rect)
            continuation = continuation_pdf(current, source, width, height)
            for part, extra in enumerate(continuation):
                if mode == 'dual' and not alternating:
                    spread = result.new_page(width=width * 2, height=height)
                    spread.show_pdf_page(pymupdf.Rect(0, 0, width, height), source, index)
                    spread.show_pdf_page(pymupdf.Rect(width, 0, width * 2, height), continuation, part)
                    spread.insert_font(fontname='KinboCJK', fontbuffer=pymupdf.Font('cjk').buffer)
                    spread.insert_text((width + 34, 31), f'译文续页  原文第 {index + 1} 页  {part + 1}', fontsize=10, fontname='KinboCJK')
                else:
                    if mode == 'dual':
                        result.insert_pdf(source, from_page=index, to_page=index)
                    result.insert_pdf(continuation, from_page=part, to_page=part)
                    result[-1].insert_font(fontname='KinboCJK', fontbuffer=pymupdf.Font('cjk').buffer)
                    result[-1].insert_text((34, 31), f'译文续页  原文第 {index + 1} 页  {part + 1}', fontsize=10, fontname='KinboCJK')
            continuation.close()
            for rect in markers:
                result[main_index].insert_link({'kind': pymupdf.LINK_GOTO, 'from': rect, 'page': first_continuation})
        temporary = path.with_name(path.name + '.continuation.tmp')
        try:
            result.save(temporary, garbage=3, deflate=True)
            with pymupdf.open(temporary) as check:
                if stats['continued'] and len(check) <= len(translated):
                    raise RuntimeError('Continuation pages were not saved')
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)
    return stats


def finish_layout_outputs(plan, engine_args):
    report = Path(plan.get('layoutReport', ''))
    if not report.is_file():
        return
    data = json.loads(report.read_text(encoding='utf-8'))
    if data.get('layoutOutputsFinalized'):
        return
    entries = data.get('continuations', [])
    if not entries:
        return
    source = Path(engine_args[0]).resolve()
    output = Path(engine_args[engine_args.index('--output') + 1]) if '--output' in engine_args else source.parent
    lang = engine_args[engine_args.index('--lang-out') + 1] if '--lang-out' in engine_args else 'zh-CN'
    files = [path for path in output.iterdir()
             if path.name.startswith(source.stem + '.')
             and re.search(r'\.' + re.escape(lang) + r'\.(mono|dual)\.pdf$', path.name)
             and path.stat().st_mtime >= report.stat().st_mtime - 1
             and not ('--no-mono' in engine_args and path.name.endswith('.mono.pdf'))
             and not ('--no-dual' in engine_args and path.name.endswith('.dual.pdf'))]
    if not files:
        raise RuntimeError('No PDF output found for translation continuation')
    results = []
    for path in files:
        results.append(add_continuations(path, source, entries, mode='dual' if path.name.endswith('.dual.pdf') else 'mono',
                                        alternating='--use-alternating-pages-dual' in engine_args))
    data['compactInlineParagraphs'] = max(result['inline'] for result in results)
    data['continuedParagraphs'] = max(result['continued'] for result in results)
    data['layoutOutputsFinalized'] = True
    report.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
