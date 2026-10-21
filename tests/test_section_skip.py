# SPDX-License-Identifier: AGPL-3.0-only
# Body-only modifications by ZhangLinqi-07, 2026-10-21. See NOTICE.md.
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'payload'))
from utils.section_skip import detect_sections, heading_kind, prepare_translation_command, read_settings, save_settings, should_skip_paragraph
from utils.section_skip_runtime import body_paragraphs


class SectionSkipTests(unittest.TestCase):
    def test_only_headings_are_matched(self):
        for text in ('References', '7. References', 'BIBLIOGRAPHY', '参考文献', 'Appendix', 'Appendix A: Proofs', 'Supplementary Material', '附录'):
            self.assertIsNotNone(heading_kind(text), text)
        for text in ('See Appendix A for details.', 'References 12', 'References to prior work are useful.', 'Appendix A presents the results.', 'Model AppendixBench results'):
            self.assertIsNone(heading_kind(text), text)

    def test_real_pdf_detects_mixed_boundary_and_preserves_body(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'paper.pdf'
            with pymupdf.open() as doc:
                p = doc.new_page()
                p.insert_text((40, 80), 'Introduction', fontsize=14, fontname='hebo')
                p.insert_text((40, 115), 'This is the complete body of an example scientific paper.', fontsize=10)
                p = doc.new_page()
                p.insert_text((40, 80), 'Code availability remains part of the body.', fontsize=10)
                p.insert_text((40, 150), 'References', fontsize=13, fontname='hebo')
                p.insert_text((40, 180), 'REFERENCE_SENTINEL_DO_NOT_SEND', fontsize=10)
                p = doc.new_page()
                p.insert_text((40, 80), 'Appendix A: Extra details', fontsize=13, fontname='hebo')
                p.insert_text((40, 115), 'APPENDIX_SENTINEL_DO_NOT_SEND', fontsize=10)
                doc.save(source)
            plan = detect_sections(source)
            self.assertTrue(plan['detected'])
            self.assertEqual(plan['boundary']['page'], 2)
            height = plan['boundary']['height']
            self.assertFalse(should_skip_paragraph(1, SimpleNamespace(x=40, x2=250, y2=height - 70), plan))
            self.assertTrue(should_skip_paragraph(1, SimpleNamespace(x=40, x2=250, y2=height - 170), plan))
            self.assertTrue(should_skip_paragraph(2, None, plan))
            self.assertFalse(should_skip_paragraph(0, None, plan))

    def test_two_column_reading_order(self):
        plan = {'detected': True, 'boundary': {'page': 2, 'height': 800, 'width': 600, 'y': 400, 'column': 'right'}}
        def box(x, top):
            return SimpleNamespace(x=x, x2=x + 100, y2=800 - top)
        self.assertFalse(should_skip_paragraph(1, box(50, 600), plan))
        self.assertFalse(should_skip_paragraph(1, box(350, 100), plan))
        self.assertTrue(should_skip_paragraph(1, box(350, 500), plan))
        plan['boundary']['column'] = 'left'
        self.assertTrue(should_skip_paragraph(1, box(350, 100), plan))
        self.assertFalse(should_skip_paragraph(1, box(50, 100), plan))

    def test_filters_restore_originals_after_errors_and_preserve_overflow(self):
        body = SimpleNamespace(box=SimpleNamespace(x=40, x2=250, y2=750))
        references = SimpleNamespace(box=SimpleNamespace(x=40, x2=250, y2=200))
        extra = SimpleNamespace(box=None)
        page = SimpleNamespace(page_number=1, pdf_paragraph=[body, references])
        doc = SimpleNamespace(page=[page])
        plan = {'detected': True, 'boundary': {'page': 2, 'height': 800, 'width': 600, 'y': 400, 'column': 'full'}}
        with self.assertRaises(RuntimeError):
            with body_paragraphs(doc, plan):
                self.assertEqual(page.pdf_paragraph, [body])
                page.pdf_paragraph.append(extra)
                raise RuntimeError('simulated provider error')
        self.assertEqual(page.pdf_paragraph, [body, references, extra])

    def test_switch_is_persistent_and_rejects_ambiguous_input(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(read_settings(folder)['enabled'])
            self.assertFalse(save_settings(folder, {'enabled': False})['enabled'])
            self.assertFalse(read_settings(folder)['enabled'])
            with self.assertRaises(ValueError):
                save_settings(folder, {'enabled': 'false'})
            command = ['pdf2zh_next', 'any.pdf', '--pages', '1-4']
            result, plan = prepare_translation_command(command, 'missing.pdf', folder)
            self.assertEqual(result, command)
            self.assertIsNone(plan)


if __name__ == '__main__':
    unittest.main()
