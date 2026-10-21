# SPDX-License-Identifier: AGPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'payload'))
from utils.layout_overflow import add_continuations, continuation_pdf, finish_layout_outputs


class ContinuationTests(unittest.TestCase):
    def fixture(self, folder, mode, alternating=False):
        source = folder / 'source[1].pdf'
        output = folder / 'output.pdf'
        with pymupdf.open() as doc:
            for index in range(2):
                page = doc.new_page(width=420, height=595)
                page.insert_text((35, 70), f'SOURCE_PAGE_{index + 1}')
                page.insert_text((35, 130), 'x = a + b')
            doc.save(source)
        with pymupdf.open(source) as original, pymupdf.open() as translated:
            for index in range(2):
                if mode == 'dual' and alternating:
                    translated.insert_pdf(original, from_page=index, to_page=index)
                page = translated.new_page(width=840 if mode == 'dual' and not alternating else 420, height=595)
                if mode == 'dual' and not alternating:
                    page.show_pdf_page(pymupdf.Rect(0, 0, 420, 595), original, index)
                page.insert_text((455 if mode == 'dual' and not alternating else 35, 80), f'TRANSLATED_PAGE_{index + 1}')
            translated.save(output)
        return source, output

    def test_long_translation_is_carried_to_readable_pages_with_tail_and_links(self):
        text = '完整中文译文必须保留所有论证与细节。' * 180 + '最终结尾哨兵'
        for mode, alternating in (('mono', False), ('dual', False), ('dual', True)):
            with self.subTest(mode=mode, alternating=alternating), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                source, output = self.fixture(folder, mode, alternating)
                entries = [{'page': 0, 'box': [35, 480, 190, 495], 'runs': [{'text': text}]}]
                add_continuations(output, source, entries, mode, alternating)
                with pymupdf.open(output) as doc:
                    self.assertGreater(len(doc), 4)
                    if mode == 'dual' and not alternating:
                        rendered = ''.join(p.get_text(clip=pymupdf.Rect(420, 0, 840, 595)) for p in doc)
                    else:
                        rendered = ''.join(p.get_text() for p in doc)
                    compact = ''.join(rendered.split())
                    self.assertIn('最终结尾哨兵', compact)
                    self.assertGreaterEqual(compact.count('完整中文译文'), 175)
                    main = doc[1 if mode == 'dual' and alternating else 0]
                    self.assertTrue(main.get_links())
                    self.assertIn('TRANSLATED_PAGE_2', doc[-1].get_text())
                    self.assertIn('[1]', main.get_text())

    def test_inline_formula_image_is_kept_between_translated_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source, _ = self.fixture(folder, 'mono')
            entries = [{'runs': [{'text': '公式之前的中文说明'},
                                 {'formula': {'page': 0, 'box': [34, 460, 100, 480]}},
                                 {'text': '公式之后的中文说明'}]}]
            with pymupdf.open(source) as doc, continuation_pdf(entries, doc, 420, 595) as extra:
                text = ''.join(extra[0].get_text().split())
                self.assertIn('公式之前的中文说明', text)
                self.assertIn('公式之后的中文说明', text)
                self.assertTrue(extra[0].get_images())

    def test_short_translated_table_cell_fits_without_an_extra_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source, output = self.fixture(folder, 'dual')
            entry = {'page': 0, 'box': [48, 182, 67.1, 189.2], 'fontSize': 7.2,
                     'runs': [{'text': '网络空间'}]}
            result = add_continuations(output, source, [entry])
            self.assertEqual(result, {'inline': 1, 'continued': 0})
            with pymupdf.open(output) as doc:
                self.assertEqual(len(doc), 2)
                self.assertIn('网络空间', ''.join(doc[0].get_text().split()))

    def test_page_mapping_failure_preserves_existing_pdf_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source, output = self.fixture(folder, 'mono')
            before = output.read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'mapping'):
                add_continuations(output, source, [{'page': 0}], 'dual', True)
            self.assertEqual(output.read_bytes(), before)

    def test_missing_output_is_an_error_instead_of_dropping_translations(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            report = folder / 'report.json'
            report.write_text(json.dumps({'continuations': [{'page': 0}]}))
            with self.assertRaisesRegex(RuntimeError, 'No PDF output'):
                finish_layout_outputs({'layoutReport': str(report)}, [str(folder / 'paper.pdf'), '--output', str(folder)])


if __name__ == '__main__':
    unittest.main()
