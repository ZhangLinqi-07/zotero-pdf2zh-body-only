# SPDX-License-Identifier: AGPL-3.0-only
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from flask import Flask
import toml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'payload'))
from utils import paper_chat
from utils.codex_chat import CodexCancelled


class PaperChatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kinbo-paper-chat-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'config').mkdir()
        self.key = 'private-key-DO-NOT-EXPOSE'
        (self.root / 'config/config.toml').write_text(toml.dumps({'openaicompatible': True,
            'openaicompatible_detail': {'openai_compatible_base_url': 'http://127.0.0.1:19876/v1',
                'openai_compatible_model': 'test-model', 'openai_compatible_api_key': self.key}}), encoding='utf-8')
        self.app = Flask(__name__)
        self.app.testing = True
        self.manager = paper_chat.register_paper_chat(self.app, self.root)
        self.addCleanup(self.manager.codex.close)
        self.client = self.app.test_client()
        self.status = patch.object(self.manager.codex, 'status', return_value={
            'available': True, 'authenticated': True, 'message': 'fixture authenticated'}).start()
        self.addCleanup(patch.stopall)

    def document(self, **kwargs):
        body = {'attachmentKey': 'ATTACH01', 'libraryID': 1, 'title': 'Test paper',
                'pages': [{'page': 1, 'text': 'FIRST source sentence'}, {'page': 2, 'text': 'LAST source sentence'}]}
        body.update(kwargs)
        response = self.client.post('/api/paper-chat/sessions', json=body)
        self.assertEqual(response.status_code, 200, response.data)
        return response.json['session']

    def wait(self, session_id):
        for _ in range(400):
            session = self.client.get('/api/paper-chat/sessions/' + session_id).json['session']
            if not session['busy']:
                return session
            time.sleep(.01)
        self.fail('chat worker did not finish')

    def test_config_hides_key_and_does_not_call_inference(self):
        with patch.object(self.manager.codex, 'answer') as answer:
            response = self.client.get('/api/paper-chat/config')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.key, response.get_data(as_text=True))
        answer.assert_not_called()

    def test_session_reopens_after_restart_and_attachment_content_changes_isolated(self):
        first = self.document()
        same = self.document()
        self.assertEqual(first['id'], same['id'])
        second = self.document(pages=[{'page': 1, 'text': 'new PDF content'}])
        self.assertNotEqual(first['id'], second['id'])
        other_library = self.document(libraryID=2)
        self.assertNotEqual(first['id'], other_library['id'])
        manager = paper_chat.PaperChatManager(self.root)
        self.addCleanup(manager.codex.close)
        self.assertEqual(manager.get(first['id'])['pageCount'], 2)
        self.assertNotIn('pages', manager.get(first['id']))

    def test_full_document_selection_history_and_prompt_sent_to_codex(self):
        session = self.document()
        captured = []
        def answer(prompt, **kwargs):
            captured.append(prompt)
            kwargs['on_delta']('partial', 'public summary')
            return {'text': 'Answer [第 2 页](kinbo://page/2)', 'reasoning': 'public summary', 'sources': []}
        with patch.object(self.manager.codex, 'answer', side_effect=answer):
            response = self.client.post('/api/paper-chat/sessions/' + session['id'] + '/messages', json={
                'mode': 'codex', 'question': 'Question one', 'selection': {'page': 2, 'text': 'LAST source'}, 'customPrompt': 'Be precise'})
            self.assertEqual(response.status_code, 200)
            finished = self.wait(session['id'])
            self.client.post('/api/paper-chat/sessions/' + session['id'] + '/messages', json={'mode': 'codex', 'question': 'Question two'})
            finished = self.wait(session['id'])
        self.assertIn('FIRST source sentence', captured[0])
        self.assertIn('LAST source sentence', captured[0])
        self.assertIn('Be precise', captured[0])
        self.assertIn('Question one', captured[1])
        self.assertIn('kinbo://page/2', captured[1])
        self.assertFalse(finished['messages'][-1]['incomplete'])
        self.assertNotIn(self.key, json.dumps(finished))

    def test_failed_request_preserves_partial_and_restart_history(self):
        session = self.document()
        def answer(prompt, **kwargs):
            kwargs['on_delta']('partial answer retained', '')
            raise ValueError('fixture sanitized failure')
        with patch.object(self.manager.codex, 'answer', side_effect=answer):
            self.client.post('/api/paper-chat/sessions/' + session['id'] + '/messages', json={'mode': 'codex', 'question': 'Question'})
            result = self.wait(session['id'])
        self.assertIn('fixture sanitized failure', result['error'])
        self.assertTrue(result['messages'][-1]['incomplete'])
        self.assertEqual(result['messages'][-1]['content'], 'partial answer retained')
        manager = paper_chat.PaperChatManager(self.root)
        self.addCleanup(manager.codex.close)
        self.assertEqual(manager.get(session['id'])['messages'][-1]['content'], 'partial answer retained')

    def test_concurrent_request_rejected_and_cancellation_retains_output(self):
        session = self.document()
        running = threading.Event()
        def answer(prompt, **kwargs):
            kwargs['on_delta']('retained output', '')
            running.set()
            kwargs['cancel'].wait(5)
            raise CodexCancelled('cancelled fixture')
        route = '/api/paper-chat/sessions/' + session['id']
        with patch.object(self.manager.codex, 'answer', side_effect=answer) as call:
            self.client.post(route + '/messages', json={'mode': 'codex', 'question': 'Question'})
            self.assertTrue(running.wait(2))
            rejected = self.client.post(route + '/messages', json={'mode': 'codex', 'question': 'Duplicate'})
            self.assertEqual(rejected.status_code, 400)
            self.assertEqual(self.client.post(route + '/clear', json={}).status_code, 400)
            self.client.post(route + '/cancel', json={})
            result = self.wait(session['id'])
            self.assertEqual(call.call_count, 1)
        self.assertEqual(result['messages'][-1]['content'], 'retained output')
        self.assertTrue(result['messages'][-1]['incomplete'])

    def test_scan_and_non_contiguous_pages_fail_before_inference(self):
        with patch.object(self.manager.codex, 'answer') as answer:
            for pages in ([{'page': 1, 'text': ''}], [{'page': 2, 'text': 'only page2'}]):
                response = self.client.post('/api/paper-chat/sessions', json={
                    'attachmentKey': 'ATTACH01', 'libraryID': 1, 'title': 'Scan', 'pages': pages})
                self.assertEqual(response.status_code, 400)
        answer.assert_not_called()

    def test_remote_and_browser_origin_and_form_requests_rejected(self):
        route = '/api/paper-chat/config'
        self.assertEqual(self.client.get(route, environ_base={'REMOTE_ADDR': '192.168.1.5'}).status_code, 403)
        self.assertEqual(self.client.get(route, headers={'Origin': 'https://attacker.example'}).status_code, 403)
        self.assertEqual(self.client.get(route, headers={'Origin': 'null'}).status_code, 403)
        self.assertEqual(self.client.get(route, headers={'Origin': 'http://localhost:9999'}).status_code, 403)
        self.assertEqual(self.client.post('/api/paper-chat/sessions', data={'question': 'csrf'}).status_code, 415)

    def test_api_uses_shared_key_and_keeps_complete_source_during_continuation(self):
        requests = []
        responses = [
            {'choices': [{'message': {'content': 'first answer'}, 'finish_reason': 'length'}], 'usage': {'prompt_tokens': 3, 'completion_tokens': 2}},
            {'choices': [{'message': {'content': ' final tail'}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 5, 'completion_tokens': 4}},
        ]
        class Opener:
            def open(inner, request, timeout):
                requests.append(request)
                return io.StringIO(json.dumps(responses.pop(0)))
        session = self.document()
        with patch.object(paper_chat.urllib.request, 'build_opener', return_value=Opener()):
            self.client.post('/api/paper-chat/sessions/' + session['id'] + '/messages', json={'mode': 'api', 'question': 'Question'})
            result = self.wait(session['id'])
        self.assertEqual(len(requests), 2)
        for request in requests:
            body = json.loads(request.data)
            self.assertIn('FIRST source sentence', json.dumps(body))
            self.assertIn('LAST source sentence', json.dumps(body))
            self.assertEqual(request.get_header('Authorization'), 'Bearer ' + self.key)
            self.assertNotIn('max_tokens', body)
            self.assertNotIn('reasoning_effort', body)
        self.assertEqual(result['messages'][-1]['content'], 'first answer final tail')
        self.assertEqual(result['messages'][-1]['usage']['prompt_tokens'], 8)


if __name__ == '__main__':
    unittest.main()
