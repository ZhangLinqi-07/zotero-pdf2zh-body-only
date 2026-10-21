# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise the real engine against a local mock; never use an external API."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'payload'))
from utils.section_skip import prepare_translation_command, prepare_runtime_command

root = Path(tempfile.mkdtemp(prefix='body-only-integration-'))
root.mkdir(parents=True, exist_ok=True)
source = root / 'section-fixture.pdf'
calls = []


class MockAPI(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        text = '\n'.join(str(m.get('content', '')) for m in body['messages'])
        calls.append(text)
        if '## Here is the input:' in text:
            rows = json.loads(text.rsplit('## Here is the input:', 1)[1].strip())
            content = json.dumps([{'id': row['id'], 'output': '这段正文已经翻译，研究结论仍然需要稳健性检验。'} for row in rows], ensure_ascii=False)
        elif 'term' in text[:500].lower() and ('extract' in text[:600].lower() or 'glossary' in text[:600].lower()):
            content = '[]'
        else:
            content = '这段正文已经翻译，研究结论仍然需要稳健性检验。'
        response = {
            'id': 'local-section-test', 'object': 'chat.completion', 'created': 0,
            'model': 'local-section-test',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20},
        }
        data = json.dumps(response, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    with pymupdf.open() as doc:
        p = doc.new_page(width=612, height=792)
        p.insert_text((60, 80), 'A scientific paper for section filtering', fontsize=16, fontname='hebo')
        p.insert_textbox((60, 115, 550, 250), 'Introduction\nScientific claims require careful robustness audits. BODY_MAIN_MUST_TRANSLATE.\nA translated reader should retain every original page.', fontsize=11)
        p = doc.new_page(width=612, height=792)
        p.insert_text((60, 80), 'Code Availability', fontsize=14, fontname='hebo')
        p.insert_textbox((60, 110, 550, 220), 'The code is available for the main study. BODY_BOUNDARY_MUST_TRANSLATE.\nThis paragraph precedes references and remains part of the body.', fontsize=11)
        p.insert_text((60, 300), 'References', fontsize=14, fontname='hebo')
        p.insert_textbox((60, 330, 550, 450), '[1] Example Author. REFERENCE_SENTINEL_DO_NOT_SEND.\nThis reference entry must stay in its original language.', fontsize=11)
        p = doc.new_page(width=612, height=792)
        p.insert_text((60, 80), 'Appendix A: Details', fontsize=14, fontname='hebo')
        p.insert_textbox((60, 115, 550, 250), 'APPENDIX_SENTINEL_DO_NOT_SEND.\nThese supplementary details remain in English.', fontsize=11)
        doc.save(source)
    api = ThreadingHTTPServer(('127.0.0.1', 0), MockAPI)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    config = root / 'local-only.toml'
    config.write_text(f'''[translation]
qps = 2
pool_max_workers = 2
ignore_cache = true
[pdf]
only_include_translated_page = false
[openaicompatible_detail]
translate_engine_type = "OpenAICompatible"
openai_compatible_model = "local-section-test"
openai_compatible_base_url = "http://127.0.0.1:{api.server_port}/v1"
openai_compatible_api_key = "local-test-key"
openai_compatible_send_temperature = false
openai_compatible_send_reasoning_effort = false
openai_compatible_enable_json_mode = false
openai_compatible_timeout = "15"
''', encoding='utf-8')
    command = [str(Path(sys.executable).with_name('pdf2zh_next.exe' if os.name == 'nt' else 'pdf2zh_next')), str(source), '--openaicompatible', '--config-file', str(config), '--output', str(root), '--lang-in', 'en', '--lang-out', 'zh-CN', '--watermark-output-mode', 'no_watermark', '--use-alternating-pages-dual', '--skip-scanned-detection']
    command, plan = prepare_translation_command(command, source, root)
    command = prepare_runtime_command(command)
    env = os.environ.copy()
    env.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1', HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9', NO_PROXY='127.0.0.1,localhost')
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    with (root / 'engine.log').open('w', encoding='utf-8') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env, timeout=180)
    api.shutdown()
    (root / 'mock-prompts.json').write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding='utf-8')
    assert result.returncode == 0, f'Engine failed with {result.returncode}; see engine.log'
    outputs = list(root.glob('*.dual.pdf'))
    assert outputs, 'The real engine did not create a dual PDF'
    assert calls, 'No local mock translation call occurred'
    all_prompts = '\n'.join(calls)
    assert 'BODY_MAIN_MUST_TRANSLATE' in all_prompts, 'Main body did not reach the model'
    assert 'BODY_BOUNDARY_MUST_TRANSLATE' in all_prompts, 'Mixed-page body did not reach the model'
    assert 'REFERENCE_SENTINEL_DO_NOT_SEND' not in all_prompts, 'References reached the model'
    assert 'APPENDIX_SENTINEL_DO_NOT_SEND' not in all_prompts, 'Appendix reached the model'
    with pymupdf.open(outputs[0]) as doc:
        assert len(doc) == 6, f'Expected all three original/translated page pairs, got {len(doc)}'
        page_two = doc[3].get_text()
        assert re.search(r'[\u4e00-\u9fff]', page_two), 'Mixed-page body was not translated'
        assert 'REFERENCE_SENTINEL_DO_NOT_SEND' in page_two, 'Original references were lost'
        assert 'APPENDIX_SENTINEL_DO_NOT_SEND' in doc[5].get_text(), 'Original appendix was lost'
        assert not re.search(r'[\u4e00-\u9fff]', doc[5].get_text()), 'Appendix was translated'
        doc[3].get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save(root / 'mixed-boundary-result.png')
    summary = {'success': True, 'mock_call_count': len(calls), 'source_pages': 3, 'dual_pages': 6, 'boundary': plan['boundary'], 'external_api_calls': 0, 'output': str(outputs[0])}
    (root / 'verification.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == '__main__':
    main()
