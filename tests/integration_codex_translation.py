#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Real PDF engine through the Codex gateway, using only a local fake model.

Run with the installed pdf2zh_next environment. All artifacts contain synthetic
paper text, and --server-dir is read only for upstream Config implementation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading

from flask import Flask
import pymupdf
import toml
from werkzeug.serving import make_server, WSGIRequestHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'payload'))
sys.path.insert(0, str(ROOT / 'tests'))
from utils.codex_provider import configure, register_codex_provider
from utils.layout_preservation import prepare_layout_command, save_layout_settings
from utils.section_skip import prepare_runtime_command, prepare_translation_command
from integration_layout import fixture

NORMAL = '研究结论需要结合完整假设与证据解释，模型保留原有约束并检验稳健性。'


class FakeCodex:
    def __init__(self):
        self.calls = []

    def status(self):
        return {'available': True, 'authenticated': True}

    def answer(self, prompt, **kwargs):
        self.calls.append(prompt)
        def translate(text):
            return NORMAL + ''.join(re.findall(r'\{v\d+\}|<v\d+>|</v\d+>', text))
        if '## Here is the input:' in prompt:
            rows = json.loads(prompt.rsplit('## Here is the input:', 1)[1].strip())
            output = json.dumps([{'id': row['id'], 'output': translate(str(row['input']))} for row in rows], ensure_ascii=False)
        else:
            source = prompt.rsplit('Now translate the following text:', 1)[-1]
            output = translate(source)
        return {'text': output, 'finishReason': 'stop', 'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}}


class QuietHandler(WSGIRequestHandler):
    def log_request(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-dir', required=True)
    parser.add_argument('--output-dir')
    options = parser.parse_args()
    server_root = Path(options.server_dir).resolve()
    # Only import the existing upstream Config class. Never start or modify the
    # user's server, its config directory, Zotero profile, or current tasks.
    import utils
    utils.__path__ = list(utils.__path__) + [str(server_root / 'utils')]
    from utils.config import Config
    folder = Path(options.output_dir or tempfile.mkdtemp(prefix='kinbo-codex-engine-')).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'config').mkdir(exist_ok=True)
    api_config = folder / 'config/config.toml'
    original = b'[openai_detail]\nopenai_api_key = "synthetic-private-preserve-fixture"\n'
    api_config.write_bytes(original)
    source, _ = fixture(folder, Path('C:/Windows/Fonts/cambria.ttc'), 1)
    app = Flask(__name__)
    fake = FakeCodex()
    provider = register_codex_provider(app, folder, fake)
    configure(folder, {'translationBackend': 'codex', 'model': 'fixture-codex'})
    local = make_server('127.0.0.1', 0, app, threaded=True, request_handler=QuietHandler)
    threading.Thread(target=local.serve_forever, daemon=True).start()
    try:
        data, changed = provider.translation_request({'engine': 'pdf2zh_next', 'disableGlossary': True,
            'noWatermark': True, 'qps': 1, 'poolSize': 1}, f'http://127.0.0.1:{local.server_port}')
        assert changed
        config = Config(data)
        task_config = Path(provider.translation_config(config.llm_api))
        config.update_config_file(task_config)
        parsed = toml.load(task_config)
        assert 'synthetic-private-preserve-fixture' not in task_config.read_text()
        assert parsed['openaicompatible_detail']['openai_compatible_api_key'] == provider.token
        assert parsed['openaicompatible'] is True
        assert parsed['term_openaicompatible'] is True
        assert parsed['term_openaicompatible_detail']['term_openai_compatible_api_key'] == provider.token
        assert parsed['term_openaicompatible_detail']['term_openai_compatible_base_url'] == config.llm_api['apiUrl']
        save_layout_settings(folder / 'config', {'preserveColumns': True, 'mathMode': 'conservative'})
        executable = Path(sys.executable).with_name('pdf2zh_next.exe' if os.name == 'nt' else 'pdf2zh_next')
        command = [str(executable), str(source), '--openaicompatible', '--config-file', str(task_config),
            '--output', str(folder), '--lang-in', 'en', '--lang-out', 'zh-CN', '--qps', '1',
            '--watermark-output-mode', 'no_watermark', '--skip-scanned-detection', '--no-auto-extract-glossary', '--ignore-cache']
        command, _ = prepare_translation_command(command, source, folder / 'config')
        command = prepare_layout_command(command, folder / 'config', source)
        command = prepare_runtime_command(command)
        env = os.environ.copy()
        env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', HTTP_PROXY='http://127.0.0.1:9',
                   HTTPS_PROXY='http://127.0.0.1:9', NO_PROXY='127.0.0.1,localhost')
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        with (folder / 'engine.log').open('w', encoding='utf-8') as log:
            result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        assert result.returncode == 0, f'Engine failed; inspect {folder / "engine.log"}'
        audit_path = Path(command[command.index('--plan') + 1]).with_suffix('.coverage.json')
        audit = json.loads(audit_path.read_text(encoding='utf-8'))
        assert audit['status'] == 'passed', audit
        assert fake.calls, 'Engine never used local Codex gateway'
        prompts = '\n'.join(fake.calls)
        assert 'REFERENCE_SENTINEL_DO_NOT_SEND' not in prompts
        assert 'APPENDIX_SENTINEL_DO_NOT_SEND' not in prompts
        output = next(folder.glob('*.dual.pdf'))
        with pymupdf.open(output) as translated:
            output_pages = len(translated)
            text = ''.join(page.get_text() for page in translated)
            assert re.search(r'[\u4e00-\u9fff]', text), 'No translated Chinese text'
            assert 'APPENDIX_SENTINEL_DO_NOT_SEND' in text
        assert api_config.read_bytes() == original, 'Shared translation API config changed'
        result = {'success': True, 'sourcePages': 3, 'outputPages': output_pages, 'mockCodexCalls': len(fake.calls),
                  'externalModelCalls': 0, 'coverageStatus': audit['status'], 'sharedAPIConfigUnchanged': True,
                  'sourceConfigSHA256': hashlib.sha256(original).hexdigest(), 'output': str(output)}
        (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        local.shutdown()
        local.server_close()


if __name__ == '__main__':
    main()
