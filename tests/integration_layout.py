#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Real-engine layout check with a local mock and an installed mathematical font."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pymupdf
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'payload'))
from utils.section_skip import prepare_translation_command, prepare_runtime_command
from utils.layout_preservation import prepare_layout_command, save_layout_settings

calls = []
NORMAL = '这是一段保留双栏版式的正文译文，研究结论需要结合假设和证据解释。'
MISSING_MODE = 'none'


class MockAPI(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        prompt = '\n'.join(str(m.get('content', '')) for m in data['messages'])
        calls.append(prompt)
        if '## Here is the input:' in prompt:
            rows = json.loads(prompt.rsplit('## Here is the input:', 1)[1].strip())
            output = json.dumps([{'id': row['id'], 'output': row['input'] if MISSING_MODE != 'none' and 'Scientific claims' in str(row) else NORMAL * (60 if 'OVERSIZE' in str(row) else 1) + ('续页完整结尾标记' if 'OVERSIZE' in str(row) else '')} for row in rows], ensure_ascii=False)
        else:
            output = NORMAL * (60 if 'OVERSIZE' in prompt else 1) + ('续页完整结尾标记' if 'OVERSIZE' in prompt else '')
            if MISSING_MODE != 'none' and 'Scientific claims' in prompt:
                source_text = prompt.rsplit('Now translate the following text:', 1)[-1].strip()
                if MISSING_MODE == 'permanent' or '[KINBO_COVERAGE_REPAIR]' not in prompt:
                    output = source_text
                else:
                    output = NORMAL + ''.join(re.findall(r'\{v\d+\}', source_text))
        body = json.dumps({'id': 'local-layout-test', 'object': 'chat.completion', 'created': 0,
                           'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': output}, 'finish_reason': 'stop'}],
                           'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def fixture(folder, font_file, font_number):
    font = TTFont(str(font_file), fontNumber=font_number)
    extracted = folder / 'math-font.ttf'
    font.save(str(extracted))
    source = folder / 'two-column-mathematics.pdf'
    rectangles = []
    with pymupdf.open() as doc:
        page = doc.new_page(width=612, height=792)
        page.insert_font(fontname='FMath', fontfile=str(extracted))
        page.insert_text((50, 55), 'Mathematical Finance: A Two-Column Layout Test', fontsize=15, fontname='hebo')
        for column, x in enumerate((45, 325)):
            for index, y in enumerate((95, 310, 510, 665)):
                body = f'BODY_COLUMN_{column}_{index}. Scientific claims in finance depend on clear assumptions. '
                body += 'The model preserves the original constraints and evaluates robust conclusions with careful evidence. '
                page.insert_textbox((x, y, x + 240, y + 80), body, fontsize=10)
            for index, y in enumerate((230, 435, 610)):
                page.insert_text((x + 8, y), 'xₜ =', fontname='FMath', fontsize=16)
                page.insert_text((x + 73, y - 12), 'α² + β² + σₜ²', fontname='FMath', fontsize=14)
                page.draw_line((x + 62, y - 6), (x + 208, y - 6), width=.7)
                page.insert_text((x + 86, y + 14), '√(1 + rₜ)', fontname='FMath', fontsize=14)
                page.insert_text((x + 210, y), f'({column * 3 + index + 1})', fontname='FMath', fontsize=10)
                rectangles.append([0, x + 2, y - 30, x + 237, y + 27])
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 70), 'Proof and Practical Implications', fontsize=15, fontname='hebo')
        page.insert_textbox((50, 110, 560, 210), 'The proof depends on the stated regularity conditions. BODY_BOUNDARY_MUST_TRANSLATE. '
                            'The assumptions limit the interpretation of the financial result.', fontsize=11)
        page.insert_text((50, 260), 'OVERSIZE: preserve readable source if translation cannot fit.', fontsize=10)
        page.insert_text((50, 410), 'References', fontsize=15, fontname='hebo')
        page.insert_text((50, 445), '[1] REFERENCE_SENTINEL_DO_NOT_SEND.', fontsize=10)
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 70), 'Appendix A: Algebraic Details', fontsize=15, fontname='hebo')
        page.insert_text((50, 115), 'APPENDIX_SENTINEL_DO_NOT_SEND.', fontsize=11)
        doc.save(source)
    return source, rectangles


def main():
    global MISSING_MODE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir')
    parser.add_argument('--font', default='C:/Windows/Fonts/cambria.ttc')
    parser.add_argument('--font-number', type=int, default=1)
    parser.add_argument('--missing-mode', choices=('none', 'recover', 'permanent'), default='none')
    options = parser.parse_args()
    MISSING_MODE = options.missing_mode
    folder = Path(options.output_dir or tempfile.mkdtemp(prefix='body-only-layout-')).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    source, rectangles = fixture(folder, Path(options.font), options.font_number)
    api = ThreadingHTTPServer(('127.0.0.1', 0), MockAPI)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    config = folder / 'local-model.toml'
    config.write_text(f'''[translation]
qps = 2
pool_max_workers = 2
ignore_cache = true
[pdf]
only_include_translated_page = false
[openaicompatible_detail]
translate_engine_type = "OpenAICompatible"
openai_compatible_model = "local-layout-test"
openai_compatible_base_url = "http://127.0.0.1:{api.server_port}/v1"
openai_compatible_api_key = "local-test-key"
openai_compatible_send_temperature = false
openai_compatible_send_reasoning_effort = false
openai_compatible_enable_json_mode = false
openai_compatible_timeout = "15"
''', encoding='utf-8')
    save_layout_settings(folder, {'preserveColumns': True, 'mathMode': 'conservative'})
    command = [str(Path(sys.executable).with_name('pdf2zh_next.exe' if os.name == 'nt' else 'pdf2zh_next')), str(source),
               '--openaicompatible', '--config-file', str(config), '--output', str(folder), '--lang-in', 'en', '--lang-out', 'zh-CN',
               '--watermark-output-mode', 'no_watermark', '--skip-scanned-detection', '--no-auto-extract-glossary']
    command, plan = prepare_translation_command(command, source, folder)
    command = prepare_layout_command(command, folder, source)
    layout_plan = json.loads(Path(command[command.index('--zotero-section-skip-plan') + 1]).read_text(encoding='utf-8'))
    command = prepare_runtime_command(command)
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9', NO_PROXY='127.0.0.1,localhost')
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    with (folder / 'engine.log').open('w', encoding='utf-8') as log:
        result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    api.shutdown()
    (folder / 'mock-prompts.json').write_text(json.dumps(calls, ensure_ascii=False), encoding='utf-8')
    audit_path = Path(command[command.index('--plan') + 1]).with_suffix('.coverage.json')
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    if MISSING_MODE == 'permanent':
        assert result.returncode != 0, 'Untranslated body was incorrectly reported as success'
        assert audit['status'] == 'failed' and audit['runs'][-1]['missing'] >= 1, audit
        assert not list(folder.glob('*.dual.pdf')), 'Untranslated PDF should not be exported as a successful result'
        result = {'success': True, 'expectedFailureDetected': True, 'coverageAudit': audit, 'externalApiCalls': 0}
        (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
        return
    assert result.returncode == 0, f'Engine failed; inspect {folder / "engine.log"}'
    assert audit['status'] == 'passed', audit
    if MISSING_MODE == 'recover':
        assert audit['runs'][-1]['repaired'] >= 1, audit
        assert any('[KINBO_COVERAGE_REPAIR]' in call for call in calls)
    output = next(folder.glob('*.dual.pdf'))
    report = json.loads(Path(layout_plan['layoutReport']).read_text(encoding='utf-8'))
    joined = '\n'.join(calls)
    assert 'REFERENCE_SENTINEL_DO_NOT_SEND' not in joined
    assert 'APPENDIX_SENTINEL_DO_NOT_SEND' not in joined
    # Some display formulas already live outside text paragraphs in BabelDOC
    # and pass through unchanged. Paragraph count is not a formula count.
    # Inline-math prose now stays in the translation stage. The pixel checks
    # below verify actual formulas independently of protected paragraph counts.
    assert 1 in report['twoColumnPages'], report
    assert report['fallbacks'], 'The deliberately oversized translation did not fall back safely'
    differences = []
    with pymupdf.open(source) as original, pymupdf.open(output) as translated:
        assert len(translated) > 3, 'Full translation continuation is missing'
        assert translated[0].rect == pymupdf.Rect(0, 0, 1224, 792)
        text = translated[0].get_text()
        assert re.search(r'[\u4e00-\u9fff]', text), 'No translated body text'
        # A successful exit and intact formulas cannot prove that fallback
        # paragraphs survived. Check the translated half explicitly.
        right_text = ''.join(page.get_text(clip=pymupdf.Rect(612, 0, 1224, 792)) for page in translated)
        assert '续页完整结尾标记' in right_text.replace('\n', ''), 'Complete overflow translation is missing'
        assert 'OVERSIZE' not in right_text, 'Source replaced an overflow translation'
        assert 'APPENDIX_SENTINEL_DO_NOT_SEND' in translated[-1].get_text()
        for page_number, x0, y0, x1, y1 in rectangles:
            clip = pymupdf.Rect(x0, y0, x1, y1)
            right_clip = clip + pymupdf.Rect(612, 0, 612, 0)
            before = original[page_number].get_pixmap(clip=clip, alpha=False)
            after = translated[page_number].get_pixmap(clip=right_clip, alpha=False)
            assert before.width == after.width and before.height == after.height
            fraction = sum(abs(a - b) > 12 for a, b in zip(before.samples, after.samples)) / len(before.samples)
            differences.append(fraction)
        assert max(differences) < .025, f'Formula region changed: {differences}'
        translated[0].get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=False).save(folder / 'layout-preview.png')
    assert 'Unknown composition type' not in (folder / 'engine.log').read_text(encoding='utf-8'), 'Unexportable paragraph compositions'
    result = {'success': True, 'sourcePages': 3, 'outputPages': len(pymupdf.open(output)), 'spreadWidth': 1224, 'formulaPixelDifferences': differences,
              'layoutReport': report, 'mockCalls': len(calls), 'externalApiCalls': 0, 'output': str(output)}
    (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
