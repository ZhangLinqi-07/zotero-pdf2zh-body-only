# SPDX-License-Identifier: AGPL-3.0-only
"""Synthetic complete-page reading tests. No model requests or real PDFs."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from flask import Flask
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'payload'))
from utils import codex_reading
from utils.deep_reading import register_reading

COMPLETE = '[KINBO_READING_COMPLETE]'


def result(text, **extra):
    return {'text': text, 'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
            'finishReason': 'stop', **extra}


def search(**extra):
    return result('已核验官方发表记录。', searchPerformed=True, searchQueries=['Synthetic paper DOI'],
                  sources=[{'url': 'https://publisher.example/paper', 'title': 'Official paper'}], **extra)


class FakeClient:
    def __init__(self):
        self.calls, self.answers = [], [search(), result('完整阅读正文。\n' + COMPLETE)]
        self.available, self.authenticated = True, True
        self.closed, self.conversation_closed = False, False
        self.closed_event = threading.Event()
        self.handler = None

    def status(self):
        return {'available': self.available, 'authenticated': self.authenticated, 'message': 'mock'}

    def answer(self, prompt, **kwargs):
        images = kwargs.get('images') or []
        captured = {**kwargs, 'prompt': prompt, 'image_bytes': [Path(p).read_bytes() for p in images]}
        self.calls.append(captured)
        if self.handler:
            return self.handler(prompt, **kwargs)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if kwargs.get('on_delta'):
            kwargs['on_delta'](answer['text'], '公开摘要')
        kwargs['conversation']['threadId'] = 'mock-thread'
        return answer

    def close_conversation(self, state):
        self.conversation_closed = True
        state.clear()

    def close(self):
        self.closed = True
        self.closed_event.set()


class CodexReadingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kinbo-codex-reading-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'config').mkdir()
        (self.root / 'prompts').mkdir()
        shutil.copy2(ROOT / 'payload/prompts/deep_reading_zh.txt', self.root / 'prompts/deep_reading_zh.txt')
        self.fake = FakeClient()
        mocked = patch.object(codex_reading, 'client_for', return_value=self.fake)
        mocked.start()
        self.addCleanup(mocked.stop)
        self.app = Flask(__name__)
        self.app.testing = True
        self.manager = register_reading(self.app, self.root)
        self.http = self.app.test_client()

    def document(self, pages=3, bound=True):
        with pymupdf.open() as pdf:
            for number in range(pages):
                page = pdf.new_page(width=240, height=320)
                # No text layer is required by the Codex visual reading path.
                page.draw_rect((20 + number, 30, 140, 180), fill=(number / max(pages, 1), .3, .2))
            content = pdf.tobytes()
        target = {'clientID': 'a' * 32, 'libraryID': 1, 'parentKey': 'ABCD1234',
                  'attachmentKey': 'PDFK1234', 'title': 'Synthetic paper'} if bound else None
        return self.manager.add_document(content, 'synthetic.pdf', target)

    def wait(self, job_id):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            value = self.manager.snapshot(job_id)
            if value['state'] != 'running':
                return value
            time.sleep(.01)
        self.fail('Codex reading mock did not terminate')

    def launch(self, document=None, provider='codex'):
        document = document or self.document()
        job = self.manager.start(document['id'], provider)
        return self.wait(job['id'])

    def test_config_retains_api_default_and_exposes_safe_codex_profile(self):
        response = self.http.get('/api/reading/config')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['options']['backend'], 'api')
        self.assertIsNone(response.json['selected'])
        self.assertEqual(response.json['profiles'][-1]['id'], 'codex')
        changed = self.http.post('/api/reading/config', json={'backend': 'codex', 'codexModel': 'test-codex-model'})
        self.assertEqual(changed.json['selected'], 'codex')
        saved = json.loads((self.root / 'config/reading.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['codexModel'], 'test-codex-model')
        self.assertNotIn('apiKey', json.dumps(changed.json))

    def test_backend_selection_applies_when_provider_omitted(self):
        self.manager.configure({'backend': 'codex', 'codexModel': 'test-model'})
        job = self.launch(provider=None)
        self.assertEqual(job['state'], 'completed')
        self.assertEqual(job['model'], 'test-model')
        self.assertTrue(all(call['model'] == 'test-model' for call in self.fake.calls))

    def test_complete_scan_has_all_images_full_template_real_sources_and_note(self):
        document = self.document(4)
        job = self.launch(document)
        self.assertEqual(job['state'], 'completed')
        self.assertEqual(job['noteState'], 'pending')
        self.assertEqual(job['imagePages'], 4)
        self.assertEqual(job['imageDpi'], 144)
        self.assertEqual(len(self.fake.calls), 2)
        self.assertTrue(self.fake.closed_event.wait(2))
        self.assertTrue(self.fake.conversation_closed)
        self.assertTrue(self.fake.closed)
        for call in self.fake.calls:
            self.assertEqual(len(call['images']), 4)
            self.assertTrue(all(data.startswith(b'\x89PNG\r\n\x1a\n') for data in call['image_bytes']))
            self.assertTrue(all(not Path(path).exists() for path in call['images']))
            image = pymupdf.Pixmap(call['image_bytes'][0])
            self.assertEqual((image.width, image.height), (480, 640))
        template = (self.root / 'prompts/deep_reading_zh.txt').read_text(encoding='utf-8-sig')
        self.assertIn(template, self.fake.calls[1]['prompt'])
        self.assertIn('https://publisher.example/paper', job['markdown'])
        self.assertNotIn(COMPLETE, job['markdown'])
        self.assertEqual(len(self.manager.pending_notes('a' * 32)), 1)
        self.assertEqual(job['apiCalls'], 1)
        self.assertEqual(job['searchApiCalls'], 1)

    def test_missing_completion_marker_continues_without_fixed_round_count(self):
        self.fake.answers = [search()] + [result(f'第 {i} 段独立分析。') for i in range(7)] + [result('最终结论。' + COMPLETE)]
        job = self.launch()
        self.assertEqual(job['state'], 'completed')
        self.assertEqual(job['apiCalls'], 8)
        self.assertEqual(job['continuations'], 7)
        self.assertEqual(job['usage']['prompt_tokens'], 80)
        for call in self.fake.calls[1:]:
            self.assertEqual(call['images'], self.fake.calls[0]['images'])
            self.assertIs(call['conversation'], self.fake.calls[0]['conversation'])
            self.assertNotIn('effort', call)
            self.assertIn((self.root / 'prompts/deep_reading_zh.txt').read_text(encoding='utf-8-sig'), call['prompt'])
        self.assertIn('第 0 段独立分析。', self.fake.calls[-1]['prompt'])
        self.assertIn('第 6 段独立分析。', self.fake.calls[-1]['prompt'])

    def test_prose_links_without_tool_search_are_rejected(self):
        self.fake.answers = [result('[source](https://publisher.example/paper)', searchPerformed=False,
                                    sources=[{'url': 'https://publisher.example/paper'}])]
        job = self.launch()
        self.assertEqual(job['state'], 'failed')
        self.assertEqual(job['apiCalls'], 0)
        self.assertIn('没有实际执行', job['message'])
        self.assertEqual(len(self.fake.calls), 1)

    def test_search_without_safe_tool_sources_is_rejected(self):
        self.fake.answers = [result('查到了资料', searchPerformed=True,
                                   sources=[{'url': 'javascript:alert(1)'}, {'url': 'https://user:pass@example.com'}])]
        job = self.launch()
        self.assertEqual(job['state'], 'failed')
        self.assertIn('可验证', job['message'])
        self.assertEqual(job['apiCalls'], 0)

    def test_later_search_without_sources_keeps_initial_verified_evidence_and_output(self):
        self.fake.answers = [search(), result('完整正文。' + COMPLETE, searchPerformed=True, sources=[])]
        job = self.launch()
        self.assertEqual(job['state'], 'completed')
        self.assertIn('完整正文。', job['markdown'])
        self.assertEqual(len(job['webResearch']['sources']), 1)

    def test_stream_failure_preserves_unfinished_note_and_closes_thread(self):
        def answer(prompt, **kwargs):
            if len(self.fake.calls) == 1:
                return search()
            kwargs['on_delta']('已生成的方法与公式 $x^2$。', '')
            raise ValueError('模拟连接中断')
        self.fake.handler = answer
        job = self.launch()
        self.assertEqual(job['state'], 'partial')
        self.assertEqual(job['noteState'], 'pending')
        self.assertIn('已生成的方法与公式 $x^2$', job['markdown'])
        self.assertIn('尚未完成', job['markdown'])
        self.assertFalse(job['usageComplete'])
        self.assertTrue(self.fake.conversation_closed)

    def test_repeat_stops_and_preserves_existing_output(self):
        self.fake.answers = [search(), result('首次独立正文，包含公式 $E=mc^2$。'), result('首次独立正文，包含公式 $E=mc^2$。')]
        job = self.launch()
        self.assertEqual(job['state'], 'partial')
        self.assertEqual(job['apiCalls'], 2)
        self.assertIn('重复', job['message'])

    def test_cancel_waits_for_current_response_then_preserves_partial(self):
        def answer(prompt, **kwargs):
            if len(self.fake.calls) == 1:
                return search()
            job_id = next(iter(self.manager.jobs))
            self.manager.request_cancel(job_id, 'a' * 32)
            return result('当前响应已生成，停止后续调用。')
        self.fake.handler = answer
        job = self.launch()
        self.assertEqual(job['state'], 'partial')
        self.assertEqual(job['apiCalls'], 1)
        self.assertEqual(job['noteState'], 'pending')
        self.assertIn('当前响应已生成', job['markdown'])

    def test_explicit_pdf_mode_fails_without_model_call(self):
        self.manager.configure({'documentMode': 'pdf'})
        document = self.document()
        with self.assertRaisesRegex(ValueError, '全部页面图像'):
            self.manager.start(document['id'], 'codex')
        self.assertEqual(self.fake.calls, [])

    def test_login_is_required_before_render_or_search(self):
        self.fake.authenticated = False
        document = self.document()
        with self.assertRaisesRegex(ValueError, '登录'):
            self.manager.start(document['id'], 'codex')
        self.assertEqual(self.fake.calls, [])

    def test_changed_pdf_and_incomplete_render_never_call_search(self):
        document = self.document()
        self.manager.path(document['id'], '.pdf').write_bytes(b'changed')
        job = self.launch(document)
        self.assertEqual(job['state'], 'failed')
        self.assertIn('发生变化', job['message'])
        self.assertEqual(self.fake.calls, [])
        document = self.document()
        with patch.object(codex_reading.page_images, 'render_all', return_value=[]):
            job = self.launch(document)
        self.assertEqual(job['state'], 'failed')
        self.assertEqual(self.fake.calls, [])


if __name__ == '__main__':
    unittest.main()
