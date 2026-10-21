# SPDX-License-Identifier: AGPL-3.0-only
"""Native tool evidence, provider routing, privacy and failure regression checks."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'payload'))
from utils import shared_api, web_research


class WebResearchTests(unittest.TestCase):
    def setUp(self):
        owner = self
        self.requests = []
        self.reply = {'candidates': [{'content': {'parts': [{'text': 'Verified official metadata.'}]},
                                     'groundingMetadata': {'webSearchQueries': ['Paper title'], 'groundingChunks': [
                                         {'web': {'uri': 'https://publisher.example/paper', 'title': 'Official paper'}}]}}],
                      'usageMetadata': {'promptTokenCount': 12, 'candidatesTokenCount': 4, 'thoughtsTokenCount': 3}}
        self.status = 200
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                owner.requests.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.send_response(owner.status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(owner.reply).encode())
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.key = 'local-research-private-key'
        self.profile = shared_api.APIProfile('openaicompatible', 'Fixture', 'gemini-fixture',
                                            f'http://127.0.0.1:{self.server.server_port}/v1', self.key)
        self.document = {'filename': 'paper.pdf', 'title': 'Embedded PDF title', 'zoteroTarget': {'title': 'Actual Zotero paper title'}}

    def test_gemini_search_has_tool_evidence_and_no_generation_budgets(self):
        result = web_research.research(self.profile, self.document)
        path, body = self.requests[0]
        self.assertIn('/v1beta/models/gemini-fixture:generateContent', path)
        self.assertEqual(body['tools'], [{'google_search': {}}])
        self.assertIn('Actual Zotero paper title', body['contents'][0]['parts'][0]['text'])
        self.assertNotIn('inlineData', json.dumps(body))
        for key in ('generationConfig', 'max_tokens', 'max_output_tokens', 'thinkingConfig', 'reasoning_effort'):
            self.assertNotIn(key, body)
        self.assertEqual(result['usage']['completion_tokens'], 7)
        self.assertTrue(result['verified'])
        self.assertNotIn(self.key, json.dumps(result))
        self.assertIn('https://publisher.example/paper', web_research.markdown_sources(result))

    def test_responses_search_is_required_and_uses_sources_from_tool_metadata(self):
        profile = shared_api.APIProfile('openaicompatible', 'Fixture', 'gpt-fixture', self.profile.endpoint, self.key)
        self.reply = {'output': [
            {'type': 'web_search_call', 'status': 'completed', 'action': {'type': 'search', 'query': 'Actual paper title',
             'sources': [{'url': 'https://publisher.example/doi', 'title': 'Publication'}]}},
            {'type': 'message', 'content': [{'type': 'output_text', 'text': 'Published.', 'annotations': [
                {'type': 'url_citation', 'url': 'https://publisher.example/doi', 'title': 'Publication'}]}]}],
            'usage': {'input_tokens': 8, 'output_tokens': 4}}
        result = web_research.research(profile, self.document)
        path, body = self.requests[0]
        self.assertEqual(path, '/v1/responses')
        self.assertEqual(body['tool_choice'], 'required')
        self.assertEqual(body['tools'], [{'type': 'web_search'}])
        self.assertEqual(len(result['sources']), 1)
        self.assertEqual(result['queries'], ['Actual paper title'])

    def test_model_claiming_to_search_without_tool_metadata_is_rejected(self):
        self.reply = {'candidates': [{'content': {'parts': [{'text': 'I searched https://publisher.example/paper'}]}}]}
        with self.assertRaisesRegex(ValueError, '可验证'):
            web_research.research(self.profile, self.document)
        self.assertEqual(len(self.requests), 1)

    def test_responses_annotations_without_an_actual_search_call_are_rejected(self):
        data = {'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'I searched.', 'annotations': [
            {'type': 'url_citation', 'url': 'https://publisher.example/doi'}]}]}]}
        with self.assertRaisesRegex(ValueError, '可验证'):
            web_research.sources_from_response(data, 'responses')

    def test_api_error_never_echoes_a_key_and_is_not_retried(self):
        self.status, self.reply = 400, {'error': {'message': self.key}}
        with self.assertRaises(ValueError) as error:
            web_research.research(self.profile, self.document)
        self.assertNotIn(self.key, str(error.exception))
        self.assertIn('HTTP 400', str(error.exception))
        self.assertEqual(len(self.requests), 1)

    def test_deepseek_raw_search_reuses_its_key_without_a_model_call(self):
        self.reply = {'results': [{'url': 'https://publisher.example/paper', 'title': 'Paper', 'summary': 'Official evidence.'}]}
        with patch.object(web_research, 'protocol_for', return_value='deepseek'):
            result = web_research.research(self.profile, self.document)
        path, body = self.requests[0]
        self.assertEqual(path, '/v1/tools/search')
        self.assertEqual(body['query'], 'Actual Zotero paper title')
        self.assertNotIn('model', body)
        self.assertEqual(result['usage'], {})
        self.assertEqual(result['sources'][0]['snippet'], 'Official evidence.')

    def test_source_links_cannot_inject_local_files_or_credentials(self):
        data = {'results': [
            {'url': 'javascript:alert(1)'}, {'url': 'file:///private/key'}, {'url': 'https://user:password@example.org/'},
            {'url': 'https://example.org/\nprivate'}, {'url': 'https://publisher.example/paper', 'title': '<img src=x> [unsafe]'}]}
        result = web_research.sources_from_response(data, 'deepseek')
        result.update(searchedAt='2026-10-21', provider='Fixture')
        self.assertEqual(len(result['sources']), 1)
        markdown = web_research.markdown_sources(result)
        self.assertNotIn('<img', markdown)
        self.assertNotIn('javascript:', markdown)

    def test_official_deepseek_search_routing_and_openai_pdf_routing(self):
        profile = shared_api.APIProfile('deepseek', 'DeepSeek', 'deepseek-flash', 'https://api.deepseek.com/v1', self.key)
        self.assertEqual(web_research.protocol_for(profile), 'deepseek')
        profile = shared_api.APIProfile('openai', 'OpenAI', 'gpt-fixture', 'https://api.openai.com/v1', self.key)
        self.assertEqual(shared_api.pdf_protocol(profile), 'responses')


if __name__ == '__main__':
    unittest.main()
