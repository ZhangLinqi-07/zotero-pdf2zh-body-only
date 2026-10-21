# SPDX-License-Identifier: AGPL-3.0-only
import json
from pathlib import Path
from types import SimpleNamespace as NS
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'payload'))
from utils.layout_preservation import protect_formula, column_boundary, prepare_layout_command, save_layout_settings


class LayoutTests(unittest.TestCase):
    def test_formula_heavy_paragraphs_use_different_protection_thresholds(self):
        paragraph = NS(unicode='x' * 40, layout_label='text', pdf_paragraph_composition=[NS(pdf_formula=NS(pdf_character=[None] * 10))])
        self.assertFalse(protect_formula(paragraph, 'off'))
        self.assertFalse(protect_formula(paragraph, 'auto'))
        self.assertFalse(protect_formula(paragraph, 'conservative'))
        paragraph.layout_label = 'isolate_formula'
        paragraph.unicode = 'x = 1'
        self.assertTrue(protect_formula(paragraph, 'auto'))

    def test_two_column_boundary_does_not_depend_on_paragraph_vertical_alignment(self):
        page = NS(cropbox=NS(box=NS(x=0, x2=600)), pdf_paragraph=[])
        for x, x2 in ((40, 280), (45, 281), (320, 560), (322, 558)):
            page.pdf_paragraph.append(NS(box=NS(x=x, x2=x2), unicode='A substantial body paragraph in one column.'))
        self.assertEqual(column_boundary(page), 300.5)
        page.pdf_paragraph = page.pdf_paragraph[:2]
        self.assertIsNone(column_boundary(page))

    def test_layout_guard_can_run_even_when_no_reference_heading_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            command = prepare_layout_command(['pdf2zh_next', 'paper.pdf'], folder, 'paper.pdf')
            marker = command.index('--zotero-section-skip-plan')
            plan = json.loads(Path(command[marker + 1]).read_text(encoding='utf-8'))
            self.assertFalse(plan['detected'])
            self.assertTrue(plan['layout']['preserveColumns'])
            self.assertIn('--no-remove-non-formula-lines', command)
            save_layout_settings(folder, {'preserveColumns': False, 'mathMode': 'off'})
            original = ['pdf2zh_next', 'paper.pdf']
            self.assertIn('--zotero-section-skip-plan', prepare_layout_command(original, folder, 'paper.pdf'))


if __name__ == '__main__':
    unittest.main()
