# SPDX-License-Identifier: AGPL-3.0-only
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'payload'))
from utils.table_text import table_cells, recover_table_layouts


class TableTextTests(unittest.TestCase):
    def line(self, text, x, y, width=150):
        return {'bbox': (x, y - 8, x + width, y + 2), 'dir': (1, 0),
                'spans': [{'text': text, 'origin': (x, y), 'size': 8}]}

    def cells(self, lines):
        page = NS(rect=NS(height=800), get_text=lambda _: {
            'blocks': [{'bbox': (40, 90, 320, 250), 'lines': lines}]})
        return table_cells(page, NS(x=38, y=550, x2=318, y2=712))

    def test_wrapped_sentences_stay_together_and_row_ids_stay_separate(self):
        cells = self.cells([self.line('6', 40, 100, 5),
                            self.line('The agent evaluates the previous choices', 70, 100),
                            self.line('and favors reliable routes over time.', 70, 110),
                            self.line('3', 40, 130, 5),
                            self.line('The next agent has a different strategy.', 70, 130)])
        self.assertEqual(len(cells), 4)
        self.assertTrue(any(b[0] == 69.5 and b[1] == 688 and b[3] == 708 for b in cells))
        self.assertTrue(any(b[0] == 69.5 and b[1] == 668 for b in cells))

    def test_same_line_numeric_columns_and_approximate_detector_edges(self):
        cells = self.cells([self.line('Accuracy', 70, 100, 30),
                            self.line('F1-score', 200, 100, 120),
                            self.line('0.920', 70, 120, 30),
                            self.line('0.880', 200, 120, 30)])
        self.assertEqual(len(cells), 4)
        self.assertEqual(cells[1][2], 320.5)

    def test_spanning_headers_never_merge_down_into_numeric_columns(self):
        cells = self.cells([self.line('Performance metrics', 70, 100, 80),
                            self.line('Accuracy', 70, 112, 30),
                            self.line('F1-score', 110, 112, 30),
                            self.line('0.920', 70, 124, 30),
                            self.line('0.880', 110, 124, 30)])
        self.assertEqual(len(cells), 5)

    def test_image_blocks_and_rotated_text_are_not_invented_as_cells(self):
        line = self.line('Vertical label', 70, 100)
        line['dir'] = (0, 1)
        self.assertEqual(self.cells([line]), [])

    def test_pseudocode_misclassified_as_a_table_keeps_native_algorithm_handling(self):
        try:
            from babeldoc.format.pdf.document_il import Box, PageLayout
        except ImportError:
            self.skipTest('Requires translation-engine Python')
        table = PageLayout(id=1, box=Box(40, 550, 320, 712), class_name='table', conf=1)
        page = NS(page_number=0, page_layout=[table])
        pdf_page = NS(rotation=0, rect=NS(height=800),
                      get_text=lambda **kwargs: 'Algorithm 1 Agent decision process\nRequire: A state and an agent.')
        recover_table_layouts(NS(page=[page]), [pdf_page])
        self.assertEqual(page.page_layout, [table])


if __name__ == '__main__':
    unittest.main()
