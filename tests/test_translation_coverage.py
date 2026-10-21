# SPDX-License-Identifier: AGPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'payload'))
from utils.translation_coverage import substantial_prose, incomplete, verify_document, require_passed

SOURCE = 'The insurer designs the contract for the firm and evaluates the expected profit under the stated assumptions.'
CHINESE = '保险公司为企业设计合约，并在所述假设下评估期望利润。'

try:
    from babeldoc.format.pdf.document_il.midend.il_translator import ParagraphTranslateTracker
    NATIVE = True
except ImportError:
    NATIVE = False


class CoverageHeuristicTests(unittest.TestCase):
    def test_empty_unchanged_and_english_remaining_in_chinese_are_detected(self):
        self.assertTrue(substantial_prose(SOURCE))
        for result in ('', SOURCE, CHINESE + SOURCE):
            self.assertTrue(incomplete(SOURCE, result, 'zh-CN'))
        self.assertFalse(incomplete(SOURCE, CHINESE + ' DeepSeek API (2026)', 'zh-CN'))

    def test_names_formulas_and_short_captions_are_not_mistaken_for_body_prose(self):
        for text in ('John Smith, James Brown, Alice Zhang, Bob Wang', 'E = m c^2', 'Table 3. Results', 'AAPL IBM API DOI JSON PDF'):
            self.assertFalse(substantial_prose(text))

    def test_missing_or_incomplete_worker_audit_never_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'audit.json'
            with self.assertRaises(RuntimeError):
                require_passed(path)
            path.write_text(json.dumps({'status': 'pending', 'runs': []}))
            with self.assertRaises(RuntimeError):
                require_passed(path)


@unittest.skipUnless(NATIVE, 'Run with translation-engine Python for coverage repair checks')
class CoverageRepairTests(unittest.TestCase):
    def engine(self, response):
        engine = NS(translation_config=NS(lang_in='en', lang_out='zh-CN', raise_if_cancelled=lambda: None),
                    support_llm_translate=True, calc_token_count=len,
                    generate_prompt_for_llm=lambda text, **kwargs: text)
        engine.translate_engine = NS(llm_translate=Mock(side_effect=response if isinstance(response, Exception) else None,
                                                       return_value=response if not isinstance(response, Exception) else None))
        engine.get_translate_input = lambda paragraph, *args, **kwargs: NS(unicode=paragraph.unicode, placeholders=[NS(placeholder='{v1}')])
        def post(paragraph, tracker, prepared, output):
            paragraph.unicode = output
            paragraph.pdf_paragraph_composition = ['translated', paragraph.pdf_paragraph_composition[-1]]
        engine.post_translate_paragraph = post
        return engine

    def document(self, count=1):
        paragraphs = [NS(unicode=SOURCE + ' {v1}', vertical=False, xobj_id=0,
                         pdf_paragraph_composition=['source glyphs', {'formula': 'E=mc^2'}]) for _ in range(count)]
        return NS(page=[NS(page_number=3, pdf_paragraph=paragraphs, pdf_font=[], pdf_xobject=[])])

    def test_single_paragraph_repair_bypasses_cache_and_keeps_formula_objects(self):
        engine = self.engine(CHINESE + ' {v1}')
        doc = self.document()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'audit.json'
            finish = verify_document(engine, doc, path)
            finish()
            require_passed(path)
            self.assertEqual(json.loads(path.read_text())['runs'][0]['repaired'], 1)
        self.assertTrue(engine.translate_engine.llm_translate.call_args.kwargs['ignore_cache'])
        self.assertEqual(doc.page[0].pdf_paragraph[0].pdf_paragraph_composition[-1], {'formula': 'E=mc^2'})

    def test_empty_source_repeat_and_missing_formula_never_become_success(self):
        for output in ('', SOURCE + ' {v1}', CHINESE):
            engine, doc = self.engine(output), self.document()
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'audit.json'
                finish = verify_document(engine, doc, path)
                with self.assertRaisesRegex(RuntimeError, '4'):
                    finish()
                with self.assertRaises(RuntimeError):
                    require_passed(path)
            self.assertEqual(engine.translate_engine.llm_translate.call_count, 1)
            self.assertEqual(doc.page[0].pdf_paragraph[0].unicode, SOURCE + ' {v1}')

    def test_common_api_failure_stops_additional_paid_retries_and_does_not_leak_error(self):
        engine, doc = self.engine(RuntimeError('provider echoed private-fixture-key')), self.document(4)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'audit.json'
            finish = verify_document(engine, doc, path)
            with self.assertRaises(RuntimeError) as error:
                finish()
            self.assertNotIn('private-fixture-key', str(error.exception))
            self.assertNotIn('private-fixture-key', path.read_text())
            self.assertEqual(engine.translate_engine.llm_translate.call_count, 1)
            self.assertEqual(json.loads(path.read_text())['runs'][0]['missing'], 4)


if __name__ == '__main__':
    unittest.main()
