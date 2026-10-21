# SPDX-License-Identifier: AGPL-3.0-only
"""Native backend regressions for missing fallback text and retained formulas."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'payload'))
from utils.layout_preservation import LayoutGuard, restore_paragraph

try:
    from babeldoc.format.pdf.document_il import (
        Box, PdfParagraph, PdfParagraphComposition as Composition, PdfCharacter,
        PdfStyle, PdfLine, PdfSameStyleCharacters, PdfFormula, PdfCurve, PdfForm,
        PdfSameStyleUnicodeCharacters,
    )
    from babeldoc.format.pdf.document_il.backend.pdf_creater import PDFCreater
    from babeldoc.format.pdf.document_il.midend import typesetting
    NATIVE = True
except ImportError:
    NATIVE = False


@unittest.skipUnless(NATIVE, 'Run with translation-engine Python for native backend export checks')
class ExportTests(unittest.TestCase):
    def source(self):
        chars = [PdfCharacter(char_unicode=char, pdf_character_id=ord(char),
                              box=Box(x=40 + i * 6, y=100, x2=46 + i * 6, y2=110),
                              pdf_style=PdfStyle(font_id='F1', font_size=10),
                              render_order=100 + i, xobj_id=3)
                 for i, char in enumerate('ABC=')]
        formula = PdfFormula(box=Box(x=58, y=100, x2=64, y2=110), pdf_character=[chars[3]], pdf_curve=[PdfCurve()], pdf_form=[PdfForm()])
        return PdfParagraph(unicode='ABC=', box=Box(x=40, y=100, x2=280, y2=110),
                            pdf_paragraph_composition=[
                                Composition(pdf_line=PdfLine(pdf_character=[chars[0]])),
                                Composition(pdf_same_style_characters=PdfSameStyleCharacters(pdf_character=[chars[1]])),
                                Composition(pdf_character=chars[2]), Composition(pdf_formula=formula)])

    def test_all_source_glyph_groups_survive_the_actual_pdf_backend(self):
        source = self.source()
        target = PdfParagraph(unicode='bad', pdf_paragraph_composition=[])
        restore_paragraph(target, source)
        with self.assertNoLogs('babeldoc.format.pdf.document_il.backend.pdf_creater', 'ERROR'):
            chars = PDFCreater.render_paragraph_to_char(None, target)
        self.assertEqual(''.join(c.char_unicode for c in chars), 'ABC=')
        self.assertEqual([c.render_order for c in chars], [100, 101, 102, 103])
        self.assertEqual([c.xobj_id for c in chars], [3] * 4)
        self.assertEqual(chars[0].box, source.pdf_paragraph_composition[0].pdf_line.pdf_character[0].box)
        self.assertIsNot(chars[0], source.pdf_paragraph_composition[0].pdf_line.pdf_character[0])
        formula = target.pdf_paragraph_composition[-1].pdf_formula
        self.assertEqual(len(formula.pdf_curve), 1)
        self.assertEqual(len(formula.pdf_form), 1)

    def test_source_without_positioned_glyphs_fails_explicitly(self):
        source = PdfParagraph(unicode='unpositioned', pdf_paragraph_composition=[Composition(
            pdf_same_style_unicode_characters=PdfSameStyleUnicodeCharacters(unicode='unpositioned'))])
        with self.assertRaisesRegex(RuntimeError, 'without positioned glyphs'):
            restore_paragraph(PdfParagraph(), source)

    def fake_engine(self):
        class Engine:
            def render_paragraph(self, paragraph, page, fonts):
                paragraph.pdf_paragraph_composition = []
            def get_max_right_space(self, box, page):
                return 600
            def _get_optimal_scale(self, *args):
                return 1
            def preprocess_document(self, *args):
                pass
            def typesetting_document(self, document):
                for page in document.page:
                    for paragraph in page.pdf_paragraph:
                        self.render_paragraph(paragraph, page, {})
            def _layout_typesetting_units(self, units, box, *args, **kwargs):
                self.last_box = box
                return units, True
        return Engine

    def test_failed_layout_retains_visible_text_through_pdf_export(self):
        for protect in (False, True):
            with self.subTest(protected_formula=protect):
                source = self.source()
                page = NS(page_number=0, cropbox=None, pdf_paragraph=[source], pdf_curve=[], pdf_form=[])
                guard = LayoutGuard({'layout': {'preserveColumns': True, 'mathMode': 'off'}})
                guard.remember_document(NS(page=[page]))
                if protect:
                    guard.protected.add(id(source))
                Engine = self.fake_engine()
                with patch.object(typesetting, 'Typesetting', Engine):
                    guard.install()
                    Engine().typesetting_document(NS(page=[page]))
                if protect:
                    self.assertEqual(''.join(c.char_unicode for c in PDFCreater.render_paragraph_to_char(None, source)), 'ABC=')
                    self.assertFalse(guard.continuations)
                else:
                    self.assertEqual(source.pdf_paragraph_composition, [])
                    self.assertEqual(''.join(run.get('text', '') for run in guard.continuations[0]['runs']), 'ABC')
                    self.assertIn('formula', guard.continuations[0]['runs'][-1])
                self.assertEqual(len(guard.fallbacks), 0 if protect else 1)

    def test_column_overflow_rejected_during_layout_so_engine_can_retry(self):
        source = self.source()
        guard = LayoutGuard({'layout': {'preserveColumns': True, 'mathMode': 'off'}})
        guard.remember(NS(page_number=0), source)
        guard.columns[0] = 300
        Engine = self.fake_engine()
        units = [NS(box=Box(x=290, y=100, x2=310, y2=110))]
        with patch.object(typesetting, 'Typesetting', Engine):
            guard.install()
            engine = Engine()
            _, fits = engine._layout_typesetting_units(units, Box(x=40, y=100, x2=550, y2=110), 1, 1.5, source)
        self.assertFalse(fits)
        self.assertEqual(engine.last_box.x2, 295)

    def test_failed_render_queues_the_translation_instead_of_the_source(self):
        paragraph = self.source()
        page = NS(page_number=0, cropbox=None, pdf_paragraph=[paragraph], pdf_curve=[], pdf_form=[])
        guard = LayoutGuard({'layout': {'preserveColumns': True, 'mathMode': 'off'}})
        guard.remember_document(NS(page=[page]))
        paragraph.unicode = '完整中文译文'
        paragraph.pdf_paragraph_composition = [Composition(pdf_same_style_unicode_characters=
            PdfSameStyleUnicodeCharacters(unicode='完整中文译文'))]
        Engine = self.fake_engine()
        with patch.object(typesetting, 'Typesetting', Engine):
            guard.install()
            Engine().typesetting_document(NS(page=[page]))
        text = ''.join(run.get('text', '') for run in guard.continuations[0]['runs'])
        self.assertEqual(text, '完整中文译文')
        self.assertNotIn('ABC', text)


if __name__ == '__main__':
    unittest.main()
