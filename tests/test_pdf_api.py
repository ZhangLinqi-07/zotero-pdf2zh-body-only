# SPDX-License-Identifier: AGPL-3.0-only
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

from flask import Flask
import pymupdf
import toml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'payload'))
from utils import shared_api
from utils.deep_reading import register_reading


class PdfAPITests(unittest.TestCase):
    def setUp(self):
        owner = self
        self.requests = []
        self.mode = 'chat'
        self.pdf = b'%PDF-original-complete-file-with-last-page-evidence'
        self.prompt = 'Exact user reading template and evidence constraints.'
        self.key = 'private-local-pdf-fixture-key'

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append((self.path, body, dict(self.headers)))
                turn = len(owner.requests)
                if owner.mode == 'reject':
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Echo ' + owner.key}).encode())
                    return
                if owner.mode == 'gemini':
                    is_search = not any('inlineData' in p for content in body.get('contents', []) for p in content.get('parts', []))
                    turn = sum(any('inlineData' in p for c in request[1].get('contents', []) for p in c.get('parts', []))
                               for request in owner.requests)
                    reply = {'candidates': [{'content': {'role': 'model', 'parts': [
                        {'text': f'Native segment {turn}', 'thoughtSignature': 'opaque-native-signature'}]},
                        'finishReason': 'MAX_TOKENS' if turn == 1 else 'STOP'}],
                        'usageMetadata': {'promptTokenCount': 11, 'candidatesTokenCount': 7,
                                          'thoughtsTokenCount': 3, 'totalTokenCount': 21}}
                    if is_search:
                        reply['candidates'][0].update(finishReason='STOP', groundingMetadata={
                            'webSearchQueries': ['Original paper'], 'groundingChunks': [
                                {'web': {'uri': 'https://publisher.example/official', 'title': 'Official source'}}]})
                elif owner.mode == 'responses':
                    reply = {'status': 'incomplete' if turn == 1 else 'completed',
                             'incomplete_details': {'reason': 'max_output_tokens'} if turn == 1 else None,
                             'output': [{'type': 'message', 'role': 'assistant', 'id': 'msg_fixture',
                                         'content': [{'type': 'output_text', 'text': f'Responses segment {turn}'}]}],
                             'usage': {'input_tokens': 11, 'output_tokens': 10, 'total_tokens': 21}}
                else:
                    reply = {'choices': [{'message': {'role': 'assistant', 'content': f'Chat segment {turn}'},
                                          'finish_reason': 'length' if turn == 1 else 'stop'}],
                             'usage': {'prompt_tokens': 11, 'completion_tokens': 10, 'total_tokens': 21}}
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(reply).encode())

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.profile = shared_api.APIProfile('openaicompatible', 'Fixture', 'gemini-fixture',
                                           f'http://127.0.0.1:{self.server.server_port}/v1', self.key, 30)

    def assert_unbounded(self, body):
        forbidden = {'max_tokens', 'max_completion_tokens', 'max_output_tokens', 'maxOutputTokens',
                     'thinkingConfig', 'thinkingBudget', 'reasoning_effort', 'generationConfig'}
        def visit(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(body)

    def request_twice(self, protocol):
        self.mode = protocol
        conversation = {}
        first = shared_api.read_pdf(self.profile, self.pdf, 'paper.pdf', self.prompt,
                                    protocol=protocol, conversation=conversation)
        last = shared_api.read_pdf(self.profile, self.pdf, 'paper.pdf', self.prompt,
                                   protocol=protocol, conversation=conversation)
        self.assertEqual(first[2], 'length')
        self.assertEqual(last[2], 'stop')
        for _, body, _ in self.requests:
            self.assert_unbounded(body)
        return first, last

    def test_gemini_reads_original_pdf_and_keeps_native_signatures_for_continuation(self):
        first, _ = self.request_twice('gemini')
        self.assertTrue(self.requests[0][0].endswith('/v1beta/models/gemini-fixture:generateContent'))
        for _, body, _ in self.requests:
            raw = body['contents'][0]['parts'][0]['inlineData']
            self.assertEqual(raw['mimeType'], 'application/pdf')
            self.assertEqual(base64.b64decode(raw['data']), self.pdf)
            self.assertEqual(body['systemInstruction']['parts'][0]['text'], self.prompt)
        continuation = self.requests[1][1]['contents']
        self.assertEqual(continuation[1]['parts'][0]['thoughtSignature'], 'opaque-native-signature')
        self.assertEqual(continuation[1]['role'], 'model')
        self.assertIn('继续', continuation[2]['parts'][0]['text'])
        self.assertEqual(first[1]['completion_tokens'], 10)
        self.assertEqual(first[1]['reasoning_tokens'], 3)

    def test_chat_file_input_keeps_complete_pdf_and_prior_output(self):
        self.request_twice('chat')
        for _, body, _ in self.requests:
            pdf = body['messages'][1]['content'][0]['file']
            self.assertEqual(base64.b64decode(pdf['file_data'].split(',', 1)[1]), self.pdf)
            self.assertEqual(body['messages'][0]['content'], self.prompt)
        self.assertEqual(self.requests[1][1]['messages'][2]['content'], 'Chat segment 1')

    def test_responses_pdf_input_can_continue_without_losing_the_original(self):
        self.request_twice('responses')
        for _, body, _ in self.requests:
            pdf = body['input'][0]['content'][0]
            self.assertEqual(pdf['type'], 'input_file')
            self.assertEqual(base64.b64decode(pdf['file_data'].split(',', 1)[1]), self.pdf)
            self.assertEqual(body['instructions'], self.prompt)
        self.assertEqual(self.requests[1][1]['input'][1]['content'][0]['text'], 'Responses segment 1')

    def test_pdf_unsupported_error_does_not_leak_the_key_or_retry_as_text(self):
        self.mode = 'reject'
        with self.assertRaises(ValueError) as error:
            shared_api.read_pdf(self.profile, self.pdf, 'paper.pdf', self.prompt, protocol='chat')
        self.assertNotIn(self.key, str(error.exception))
        self.assertIn('完整 PDF', str(error.exception))
        self.assertEqual(len(self.requests), 1)

    def test_google_native_endpoint_uses_header_auth_and_no_model_substitution(self):
        profile = shared_api.APIProfile('gemini', 'Google', 'gemini-3.8-flash',
                                       'https://generativelanguage.googleapis.com/v1beta/openai', self.key)
        endpoint, body, headers, protocol = shared_api.pdf_request(profile, self.pdf, 'paper.pdf', self.prompt)
        self.assertEqual(endpoint, 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent')
        self.assertEqual(headers['x-goog-api-key'], self.key)
        self.assertNotIn('Authorization', headers)
        self.assertNotIn(self.key, endpoint)
        self.assert_unbounded(body)

    def test_empty_gemini_length_stop_retains_pdf_for_the_next_attempt(self):
        _, body, _, _ = shared_api.pdf_request(self.profile, self.pdf, 'paper.pdf', self.prompt, 'gemini')
        response = {'candidates': [{'content': {'role': 'model'}, 'finishReason': 'MAX_TOKENS'}]}
        self.assertEqual(shared_api.parse_pdf_response(response, 'gemini')[2], 'length')
        next_body = shared_api.continue_pdf_request(body, response, 'gemini')
        self.assertEqual(len(next_body['contents']), 1)
        self.assertEqual(base64.b64decode(next_body['contents'][0]['parts'][0]['inlineData']['data']), self.pdf)
        self.assert_unbounded(next_body)

    def test_real_http_reading_job_continues_the_full_pdf_and_queues_one_child_note(self):
        self.mode = 'gemini'
        with tempfile.TemporaryDirectory(prefix='pdf-whole-job-') as folder:
            root = Path(folder)
            (root / 'config').mkdir()
            (root / 'prompts').mkdir()
            (root / 'prompts/deep_reading_zh.txt').write_text(self.prompt, encoding='utf-8')
            (root / 'config/config.toml').write_text(toml.dumps({'openaicompatible_detail': {
                'openai_compatible_api_key': self.key, 'openai_compatible_model': self.profile.model,
                'openai_compatible_base_url': self.profile.endpoint}}), encoding='utf-8')
            app = Flask(__name__)
            app.testing = True
            manager = register_reading(app, root)
            client = app.test_client()
            with pymupdf.open() as pdf:
                pdf.new_page().insert_text((40, 60), 'First page.')
                pdf.new_page().insert_text((40, 60), 'Last page evidence.')
                content = pdf.tobytes()
            target = {'clientID': 'a' * 32, 'libraryID': 1, 'parentKey': 'ABCD1234', 'attachmentKey': 'PDFK1234', 'title': 'Original paper'}
            uploaded = client.post('/api/reading/documents', json={'fileName': 'paper.pdf', 'fileContent': base64.b64encode(content).decode(), 'zoteroTarget': target}).json['document']
            job = client.post('/api/reading/jobs', json={'documentId': uploaded['id']}).json['job']
            deadline = time.monotonic() + 5
            while job['state'] == 'running' and time.monotonic() < deadline:
                time.sleep(.02)
                job = client.get('/api/reading/jobs/' + job['id']).json['job']
            self.assertEqual(job['state'], 'completed')
            self.assertEqual(job['apiCalls'], 2)
            self.assertEqual(job['continuations'], 1)
            self.assertEqual(job['searchApiCalls'], 1)
            self.assertEqual(job['totalApiCalls'], 3)
            self.assertEqual(job['searchState'], 'verified')
            self.assertIn('https://publisher.example/official', job['markdown'])
            self.assertIn('Native segment 1', job['markdown'])
            self.assertIn('Native segment 2', job['markdown'])
            self.assertEqual(job['usage']['reasoning_tokens'], 6)
            self.assertEqual(job['usage']['completion_tokens'], 20)
            self.assertEqual(len(manager.pending_notes(target['clientID'])), 1)
            for _, body, _ in self.requests:
                if 'inlineData' in body['contents'][0]['parts'][0]:
                    self.assertEqual(base64.b64decode(body['contents'][0]['parts'][0]['inlineData']['data']), content)
                self.assertEqual(body['tools'], [{'google_search': {}}])
                self.assert_unbounded(body)


if __name__ == '__main__':
    unittest.main()
