# SPDX-License-Identifier: AGPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest

from flask import Flask
import toml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'payload'))
from utils.codex_provider import CodexProvider, configure, register_codex_provider, settings


class FakeCodex:
    def __init__(self):
        self.calls = []
        self.authenticated = True
        self.response = {'text': '完整译文 $x+y$', 'finishReason': 'stop', 'usage': {}}

    def status(self):
        return {'available': True, 'authenticated': self.authenticated}

    def answer(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return self.response


class CodexProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'config').mkdir()
        self.original = b'[openai_detail]\nopenai_api_key = "private-preserve-sentinel"\n'
        (self.root / 'config/config.toml').write_bytes(self.original)
        self.client = FakeCodex()
        self.app = Flask(__name__)
        self.provider = register_codex_provider(self.app, self.root, self.client)
        self.http = self.app.test_client()

    def test_default_does_not_change_existing_translation_or_call_model(self):
        original = {'engine': 'pdf2zh_next', 'llm_api': {'apiKey': 'existing-key'}}
        result, changed = self.provider.translation_request(original, 'http://127.0.0.1:8893')
        self.assertIs(result, original)
        self.assertFalse(changed)
        self.assertEqual(self.client.calls, [])

    def test_codex_routes_engine_to_local_gateway_without_persisting_paid_keys(self):
        configure(self.root, {'translationBackend': 'codex', 'model': 'chosen-model'})
        original = {'engine': 'pdf2zh', 'qps': 10, 'llm_api': {'apiKey': 'existing-key'}}
        result, changed = self.provider.translation_request(original, 'http://127.0.0.1:8893')
        self.assertTrue(changed)
        self.assertEqual(result['engine'], 'pdf2zh_next')
        self.assertEqual(result['qps'], 1)
        self.assertEqual(result['llm_api']['apiUrl'], 'http://127.0.0.1:8893/api/codex/v1')
        self.assertEqual(result['llm_api']['model'], 'chosen-model')
        self.assertEqual(original['llm_api']['apiKey'], 'existing-key')
        path = Path(self.provider.translation_config(result['llm_api']))
        self.assertNotIn('private-preserve-sentinel', path.read_text())
        self.assertIn('openaicompatible_detail', toml.load(path))
        self.assertEqual((self.root / 'config/config.toml').read_bytes(), self.original)
        self.assertEqual(self.client.calls, [])

    def test_task_config_routes_main_and_glossary_engines_to_same_local_model(self):
        configure(self.root, {'translationBackend': 'codex', 'model': 'chosen-model'})
        rewritten, _ = self.provider.translation_request({}, 'http://127.0.0.1:8893')
        config = toml.load(self.provider.translation_config(rewritten['llm_api']))
        self.assertIs(config['openaicompatible'], True)
        self.assertIs(config['term_openaicompatible'], True)
        for table, prefix in [('openaicompatible_detail', ''), ('term_openaicompatible_detail', 'term_')]:
            self.assertEqual(config[table][prefix + 'openai_compatible_api_key'], self.provider.token)
            self.assertEqual(config[table][prefix + 'openai_compatible_model'], 'chosen-model')
            self.assertEqual(config[table][prefix + 'openai_compatible_base_url'], 'http://127.0.0.1:8893/api/codex/v1')
        self.assertNotIn('private-preserve-sentinel', json.dumps(config))
        self.assertEqual((self.root / 'config/config.toml').read_bytes(), self.original)

    def test_task_config_rejects_paid_or_remote_connections(self):
        valid = {'apiKey': self.provider.token, 'apiUrl': 'http://127.0.0.1:8893/api/codex/v1', 'model': 'codex-auto'}
        for invalid in (None, {**valid, 'apiKey': 'paid-existing-key'},
                        {**valid, 'apiUrl': 'https://external.example/v1'},
                        {**valid, 'apiUrl': 'http://127.0.0.1:8893/wrong-route'}, {**valid, 'model': ''}):
            with self.assertRaises(ValueError):
                self.provider.translation_config(invalid)

    def test_login_required_before_translation(self):
        configure(self.root, {'translationBackend': 'codex'})
        self.client.authenticated = False
        with self.assertRaisesRegex(ValueError, '登录'):
            self.provider.translation_request({}, 'http://127.0.0.1:8893')

    def test_gateway_auth_origin_and_remote_access_are_checked_before_model(self):
        body = {'messages': [{'role': 'user', 'content': 'translate'}]}
        self.assertEqual(self.http.post('/api/codex/v1/chat/completions', json=body).status_code, 401)
        headers = {'Authorization': 'Bearer ' + self.provider.token, 'Origin': 'https://example.invalid'}
        self.assertEqual(self.http.post('/api/codex/v1/chat/completions', json=body, headers=headers).status_code, 403)
        headers.pop('Origin')
        self.assertEqual(self.http.post('/api/codex/v1/chat/completions', json=body, headers=headers,
                         environ_base={'REMOTE_ADDR': '192.0.2.1'}).status_code, 403)
        self.assertEqual(self.client.calls, [])

    def test_complete_translation_preserves_all_input_and_formula_placeholders(self):
        source = 'BEGIN ' + '本文素材 ' * 10000 + '<v1>$a+b$</v1> END'
        body = {'model': 'chosen-model', 'messages': [{'role': 'system', 'content': '保留 <v1> 标签'},
                                                        {'role': 'user', 'content': source}]}
        result = self.http.post('/api/codex/v1/chat/completions', json=body,
                               headers={'Authorization': 'Bearer ' + self.provider.token})
        self.assertEqual(result.status_code, 200)
        self.assertIn(source, self.client.calls[0][0])
        self.assertEqual(self.client.calls[0][1], {'model': 'chosen-model', 'web_search': False})
        self.assertEqual(result.json['choices'][0]['message']['content'], '完整译文 $x+y$')

    def test_partial_or_empty_response_is_failure(self):
        for response in ({'text': ''}, {'text': '不完整', 'finishReason': 'length'}):
            self.client.response = response
            with self.assertRaises(ValueError):
                self.provider.complete({'messages': [{'role': 'user', 'content': 'translate'}]})

    def test_settings_do_not_contain_credentials(self):
        self.http.post('/api/model-backend', json={'translationBackend': 'codex', 'model': 'chosen-model'})
        body = self.http.get('/api/model-backend').get_data(as_text=True)
        self.assertNotIn(self.provider.token, body)
        self.assertNotIn('private-preserve-sentinel', body)
        self.assertEqual(settings(self.root)['translationBackend'], 'codex')


if __name__ == '__main__':
    unittest.main()
