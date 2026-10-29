# SPDX-License-Identifier: AGPL-3.0-only
import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'payload'))
from utils.codex_chat import (CodexClient, CodexError, CodexCancelled, _RPC, safe_config,
                             _configured_mcp_names, _launch_prefix, protocol_error, cli_version, find_codex)


class FakeRPC:
    def __init__(self, script=None):
        self.events = queue.Queue()
        self.calls = []
        self.closed = False
        self.script = script or [
            {'method': 'item/agentMessage/delta', 'params': {'threadId': 't1', 'itemId': 'a', 'delta': '部分'}},
            {'method': 'item/reasoning/summaryTextDelta', 'params': {'threadId': 't1', 'itemId': 'r', 'delta': '公开摘要'}},
            {'method': 'item/completed', 'params': {'threadId': 't1', 'item': {'type': 'agentMessage', 'id': 'a', 'text': '完整答案'}}},
            {'method': 'thread/tokenUsage/updated', 'params': {'threadId': 't1', 'tokenUsage': {'last': {
                'inputTokens': 15, 'outputTokens': 7, 'totalTokens': 22, 'reasoningOutputTokens': 2}}}},
            {'method': 'turn/completed', 'params': {'threadId': 't1', 'turn': {'id': 'turn1', 'status': 'completed'}}},
        ]

    def request(self, method, params=None, timeout=30):
        self.calls.append((method, params))
        if method == 'account/read':
            return {'account': {'type': 'chatgpt', 'email': 'private@example.test', 'planType': 'pro'}}
        if method == 'thread/start':
            return {'thread': {'id': 't1'}}
        if method == 'turn/start':
            for event in self.script:
                self.events.put(event)
            return {'turn': {'id': 'turn1'}}
        if method == 'account/login/start':
            return {'loginId': 'login1', 'verificationUrl': 'https://auth.openai.com/codex/device', 'userCode': 'ABCD-TEST'}
        return {}

    def close(self):
        self.closed = True


class CodexClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kinbo-codex-test-')
        self.addCleanup(self.temp.cleanup)
        self.client = CodexClient(self.temp.name)
        self.addCleanup(self.client.close)

    def test_entire_prompt_all_images_and_public_summary(self):
        rpc = FakeRPC()
        image_paths = []
        for number in range(3):
            path = Path(self.temp.name) / f'{number}.png'
            path.write_bytes(b'fake fixture, not a real image')
            image_paths.append(path)
        updates = []
        prompt = 'FIRST' + ('whole paper text ' * 10000) + 'LAST'
        with patch.object(self.client, '_rpc', return_value=rpc):
            result = self.client.answer(prompt, model='user-model', effort='high', images=image_paths,
                                        on_delta=lambda text, summary: updates.append((text, summary)))
        start = next(params for method, params in rpc.calls if method == 'thread/start')
        turn = next(params for method, params in rpc.calls if method == 'turn/start')
        self.assertEqual(start['sandbox'], 'read-only')
        self.assertEqual(start['approvalPolicy'], 'never')
        self.assertEqual(start['environments'], [])
        self.assertFalse(start['allowProviderModelFallback'])
        self.assertEqual(turn['input'][0]['text'], prompt)
        self.assertEqual([row['path'] for row in turn['input'][1:]], [str(p.resolve()) for p in image_paths])
        self.assertEqual(turn['effort'], 'high')
        self.assertEqual(result['text'], '完整答案')
        self.assertEqual(result['reasoning'], '公开摘要')
        self.assertEqual(result['usage']['prompt_tokens'], 15)
        self.assertTrue(rpc.closed)
        self.assertIn(('部分', ''), updates)

    def test_live_conversation_reuses_thread_and_resends_all_images(self):
        rpc, conversation = FakeRPC(), {}
        path = Path(self.temp.name) / 'page.png'
        path.write_bytes(b'image fixture')
        with patch.object(self.client, '_rpc', return_value=rpc) as create:
            self.client.answer('full prompt', images=[path], conversation=conversation)
            self.client.answer('continue with all pages', images=[path], conversation=conversation)
        self.assertEqual(create.call_count, 1)
        self.assertEqual(sum(method == 'thread/start' for method, _ in rpc.calls), 1)
        self.assertEqual(sum(method == 'turn/start' for method, _ in rpc.calls), 2)
        self.assertFalse(rpc.closed)
        self.client.close_conversation(conversation)
        self.assertTrue(rpc.closed)
        self.assertFalse(conversation)

    def test_search_sources_come_only_from_tool_events(self):
        rpc = FakeRPC()
        rpc.script.insert(0, {'method': 'item/completed', 'params': {'threadId': 't1', 'item': {
            'id': 'w', 'type': 'webSearch', 'query': 'paper identity',
            'action': {'type': 'search', 'query': 'paper identity'},
            'results': [{'url': 'https://publisher.example/paper', 'title': 'Source'}]}}})
        with patch.object(self.client, '_rpc', return_value=rpc):
            result = self.client.answer('Find actual sources. Model link https://fake.example', web_search=True)
        self.assertTrue(result['searchPerformed'])
        self.assertEqual([row['url'] for row in result['sources']], ['https://publisher.example/paper'])
        self.assertEqual(result['searchQueries'], ['paper identity'])

    def test_no_tool_search_cannot_claim_searched(self):
        with patch.object(self.client, '_rpc', return_value=FakeRPC()):
            with self.assertRaisesRegex(CodexError, '实际联网搜索'):
                self.client.answer('Search', web_search=True)
        with patch.object(self.client, '_rpc', return_value=FakeRPC()):
            result = self.client.answer('Continue after verified search', web_search=True, require_search=False)
        self.assertFalse(result['searchPerformed'])

    def test_cancel_before_model_request(self):
        cancel = threading.Event()
        cancel.set()
        with patch.object(self.client, '_rpc') as spawn:
            with self.assertRaises(CodexCancelled):
                self.client.answer('question', cancel=cancel)
        spawn.assert_not_called()

    def test_failed_turn_preserves_partial_callback(self):
        rpc = FakeRPC()
        rpc.script[-1]['params']['turn']['status'] = 'failed'
        updates = []
        with patch.object(self.client, '_rpc', return_value=rpc):
            with self.assertRaisesRegex(CodexError, '未完成'):
                self.client.answer('question', on_delta=lambda text, reasoning: updates.append(text))
        self.assertIn('完整答案', updates)
        self.assertTrue(rpc.closed)

    def test_api_key_login_is_not_chatgpt_login_and_no_private_account_return(self):
        with patch('utils.codex_chat.find_codex', return_value='codex'), patch.object(self.client, '_control_rpc', return_value=FakeRPC()):
            status = self.client.status()
        self.assertTrue(status['authenticated'])
        self.assertNotIn('email', json.dumps(status))
        self.assertNotIn('private@example', json.dumps(status))
        rpc = FakeRPC()
        rpc.request = lambda *args, **kwargs: {'account': {'type': 'apiKey'}}
        with patch('utils.codex_chat.find_codex', return_value='codex'), patch.object(self.client, '_control_rpc', return_value=rpc):
            self.assertFalse(self.client.status()['authenticated'])

    def test_login_prefers_official_browser_flow_without_device_setting(self):
        rpc = FakeRPC()
        rpc.request = lambda method, params=None, **kwargs: (rpc.calls.append((method, params)) or {
            'loginId': 'browser1', 'authUrl': 'https://chatgpt.com/oauth/authorize?test=fixture'})
        with patch.object(self.client, 'status', return_value={'authenticated': False}), patch.object(self.client, '_control_rpc', return_value=rpc):
            login = self.client.start_login()
        self.assertEqual(rpc.calls[0][1]['type'], 'chatgpt')
        self.assertEqual(login['verificationUri'], 'https://chatgpt.com/oauth/authorize?test=fixture')
        self.assertEqual(login['userCode'], '')
        self.assertNotIn('token', json.dumps(login).lower())

    def test_browser_flow_falls_back_only_for_definite_local_callback_failure(self):
        rpc = FakeRPC()
        original = rpc.request
        def request(method, params=None, **kwargs):
            if params.get('type') == 'chatgpt':
                rpc.calls.append((method, params))
                raise protocol_error(method, {'code': -32000, 'message': 'failed to bind: Address already in use'})
            return original(method, params, **kwargs)
        rpc.request = request
        with patch.object(self.client, 'status', return_value={'authenticated': False}), patch.object(self.client, '_control_rpc', return_value=rpc):
            login = self.client.start_login()
        self.assertEqual([params['type'] for method, params in rpc.calls], ['chatgpt', 'chatgptDeviceCode'])
        self.assertEqual(login['userCode'], 'ABCD-TEST')

    def test_login_network_failure_is_not_retried_and_private_errors_are_not_returned(self):
        rpc = FakeRPC()
        rpc.request = lambda method, *args, **kwargs: (_ for _ in ()).throw(protocol_error(method, {
            'code': -32000, 'message': 'TLS connection failed sk-private-secret https://private.test/?token=secret'}))
        self.client._cli_version = '0.141.0'
        with patch.object(self.client, 'status', return_value={'authenticated': False}), patch.object(self.client, '_control_rpc', return_value=rpc):
            with self.assertRaisesRegex(CodexError, '步骤 account/login/start，错误码 -32000，CLI 0.141.0') as error:
                self.client.start_login()
        self.assertNotIn('sk-private', str(error.exception))
        self.assertNotIn('private.test', str(error.exception))

    def test_official_login_url_rejects_untrusted_hosts_and_credentials(self):
        for url in ('https://chatgpt.com.evil.test/login', 'https://user:secret@chatgpt.com/login',
                    'http://chatgpt.com/login', 'https://chatgpt.com:secret/login'):
            rpc = FakeRPC()
            rpc.request = lambda *args, **kwargs: {'loginId': 'x', 'authUrl': url}
            with patch.object(self.client, 'status', return_value={'authenticated': False}), patch.object(self.client, '_control_rpc', return_value=rpc):
                with self.assertRaisesRegex(CodexError, '官方登录地址'):
                    self.client.start_login()

    def test_status_provides_safe_diagnostic_without_starting_login_or_model(self):
        rpc = FakeRPC()
        rpc.request = lambda method, *args, **kwargs: (_ for _ in ()).throw(protocol_error(method, {
            'code': -32601, 'message': 'method missing PRIVATE_ACCOUNT_SENTINEL'}))
        with patch('utils.codex_chat.find_codex', return_value='fixture'), patch.object(self.client, '_control_rpc', return_value=rpc):
            status = self.client.status()
        self.assertEqual(status['diagnostic']['stage'], 'account/read')
        self.assertEqual(status['diagnostic']['category'], 'protocol_incompatible')
        self.assertNotIn('PRIVATE_ACCOUNT_SENTINEL', json.dumps(status))

    def test_mac_homebrew_executable_is_found_when_gui_path_is_missing(self):
        with patch('utils.codex_chat.platform.system', return_value='Darwin'), \
             patch('utils.codex_chat.shutil.which', return_value=None), \
             patch.dict('os.environ', {'KINBO_CODEX_EXECUTABLE': ''}), \
             patch('utils.codex_chat.Path.is_file', lambda path: str(path).replace('\\', '/') == '/opt/homebrew/bin/codex'), \
             patch('utils.codex_chat.os.access', return_value=True):
            self.assertTrue(find_codex().replace('\\', '/').endswith('/opt/homebrew/bin/codex'))

    def test_cli_version_returns_only_version_not_extra_output(self):
        result = type('Result', (), {'stdout': 'private account info\ncodex-cli 0.141.0-alpha.1\n'})()
        with patch('utils.codex_chat.subprocess.run', return_value=result):
            self.assertEqual(cli_version('codex', self.temp.name), '0.141.0-alpha.1')

    def test_mac_npm_symlink_uses_native_binary_without_node_path(self):
        package = Path(self.temp.name) / 'node_modules/@openai/codex'
        wrapper = package / 'bin/codex.js'
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text('// fixture')
        native = package / 'node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/codex/codex'
        native.parent.mkdir(parents=True)
        native.write_bytes(b'fixture')
        with patch('utils.codex_chat.platform.system', return_value='Darwin'), \
             patch('utils.codex_chat.platform.machine', return_value='arm64'), \
             patch('utils.codex_chat.os.access', return_value=True), \
             patch('utils.codex_chat.shutil.which', return_value=None):
            self.assertEqual(_launch_prefix(str(wrapper)), [str(native)])

    def test_mac_npm_wrapper_uses_node_without_invoking_a_shell(self):
        wrapper = Path(self.temp.name) / 'codex/bin/codex.js'
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text('// fixture')
        with patch('utils.codex_chat.platform.system', return_value='Darwin'), \
             patch('utils.codex_chat.shutil.which', return_value='/fixture/node'):
            self.assertEqual(_launch_prefix(str(wrapper)), ['/fixture/node', str(wrapper)])

    def test_tools_disabled_and_server_requests_refused(self):
        config = safe_config(True)
        self.assertFalse(config['features.shell_tool'])
        self.assertFalse(config['features.apps'])
        self.assertFalse(config['features.plugins'])
        self.assertFalse(config['features.multi_agent'])
        self.assertEqual(config['mcp_servers'], {})
        rpc = object.__new__(_RPC)
        rpc.pending, rpc.lock, rpc.events = {}, threading.Lock(), queue.Queue()
        rpc.process = type('Process', (), {'stdout': [json.dumps({'id': 5, 'method': 'item/commandExecution/requestApproval'})]})()
        responses = []
        rpc.send = responses.append
        rpc._read()
        self.assertEqual(responses[0]['id'], 5)
        self.assertIn('error', responses[0])

    def test_mcp_servers_are_disabled_by_name_because_empty_tables_merge(self):
        path = Path(self.temp.name) / 'config.toml'
        path.write_text('[mcp_servers.fixture]\ncommand="not-executed"\n[mcp_servers.fixture.env]\nAPI_KEY="private-fixture"\n', encoding='utf-8')
        with patch.dict('os.environ', {'CODEX_HOME': self.temp.name}):
            names = _configured_mcp_names()
        self.assertEqual(names, ['fixture'])
        config = safe_config(False, names)
        self.assertIs(config['mcp_servers.fixture.enabled'], False)
        self.assertNotIn('private-fixture', json.dumps(config))

    def test_npm_batch_shim_resolves_native_optional_package_without_shell(self):
        shim = Path(self.temp.name) / 'codex.cmd'
        native = shim.parent / 'node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/codex/codex.exe'
        native.parent.mkdir(parents=True)
        native.write_bytes(b'non-executable fixture; test only resolves its path')
        with patch('utils.codex_chat.platform.machine', return_value='AMD64'):
            self.assertEqual(_launch_prefix(str(shim)), [str(native.resolve())])

    def test_npm_batch_shim_uses_node_wrapper_and_missing_install_fails_closed(self):
        shim = Path(self.temp.name) / 'codex.cmd'
        wrapper = shim.parent / 'node_modules/@openai/codex/bin/codex.js'
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text('// non-executed test fixture', encoding='utf-8')
        with patch('utils.codex_chat.shutil.which', return_value='fixture-node.exe'):
            self.assertEqual(_launch_prefix(str(shim)), ['fixture-node.exe', str(wrapper.resolve())])
        with patch('utils.codex_chat.shutil.which', return_value=None):
            with self.assertRaisesRegex(CodexError, 'npm Codex'):
                _launch_prefix(str(shim))


if __name__ == '__main__':
    unittest.main()
