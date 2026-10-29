# SPDX-License-Identifier: AGPL-3.0-only
"""Recover text cells before fallback glyph boxes fragment table sentences."""
from functools import wraps
import re


def table_cells(pdf_page, table):
    """Use PDF text blocks and aligned wrapped lines, without OCR or model calls."""
    height = pdf_page.rect.height
    cells = []
    for block in pdf_page.get_text('dict')['blocks']:
        groups = []
        row = 0
        left = block['bbox'][0]
        for line in block.get('lines', []):
            spans = line.get('spans', [])
            if not spans or line.get('dir', (1, 0)) != (1, 0):
                continue
            x0, top, x1, bottom = line['bbox']
            baseline = sum(span['origin'][1] for span in spans) / len(spans)
            if not (table.x <= (x0 + x1) / 2 <= table.x2
                    and table.y <= height - baseline <= table.y2):
                continue
            size = max(span['size'] for span in spans)
            text = ''.join(span['text'] for span in spans).strip()
            words = re.findall(r'[A-Za-z]+', text)
            if text.isdigit() and abs(x0 - left) < size and x1 - x0 < size * 3:
                row += 1
            # Distinct columns on the same physical line must remain distinct.
            previous = next((g for g in groups
                             if abs(g['x0'] - x0) <= max(2, size * 1.5)
                             and g['row'] == row
                             and g['prose'] and words
                             and baseline - g['baseline'] > size * .5
                             and baseline - g['baseline'] < size * 2.5), None)
            if previous is None:
                groups.append(dict(x0=x0, top=top, x1=x1, bottom=bottom,
                                   baseline=baseline, row=row, prose=len(words) >= 6))
            else:
                previous.update(x0=min(previous['x0'], x0), top=min(previous['top'], top),
                                x1=max(previous['x1'], x1), bottom=max(previous['bottom'], bottom),
                                baseline=baseline)
        # Detector boxes are approximate. Clipping to them can cut the final
        # letters off a word and send those letters back to fallback layouts.
        cells.extend((g['x0'] - .5, height - g['bottom'],
                      g['x1'] + .5, height - g['top'])
                     for g in groups)
    return [box for box in cells if box[0] < box[2] and box[1] < box[3]]


def recover_table_layouts(document, pdf):
    from babeldoc.format.pdf.document_il import Box, PageLayout
    recovered = 0
    for page in document.page:
        original = pdf[page.page_number]
        if original.rotation:
            continue
        tables = [layout for layout in page.page_layout if layout.class_name == 'table']
        next_id = max((layout.id for layout in page.page_layout), default=0) + 1
        for table in tables:
            # Layout models sometimes label ruled pseudocode as a table.
            # Keep the engine's algorithm/formula handling for those regions.
            import pymupdf
            caption = original.get_text(clip=pymupdf.Rect(
                table.box.x, original.rect.height - table.box.y2 - 16,
                table.box.x2, original.rect.height - table.box.y2 + 32))
            if re.search(r'(?im)^\s*Algorithm\s+\d+\b', caption):
                continue
            for box in table_cells(original, table.box):
                page.page_layout.append(PageLayout(id=next_id, box=Box(*box),
                                                   conf=1, class_name='table_text'))
                next_id += 1
                recovered += 1
    print(f'[table-text] Recovered {recovered} table text cells from the PDF text layer.', flush=True)


def install_table_text_support():
    from babeldoc.format.pdf.document_il.midend.layout_parser import LayoutParser
    original = LayoutParser.process
    if getattr(original, '_kinbo_table_text', False):
        return

    @wraps(original)
    def process(self, document, pdf):
        result = original(self, document, pdf)
        recover_table_layouts(document, pdf)
        return result

    process._kinbo_table_text = True
    LayoutParser.process = process
