# SPDX-License-Identifier: AGPL-3.0-only
"""Detect substantial untranslated source prose before typesetting can hide it."""
from copy import deepcopy
import json
from pathlib import Path
import re

from utils.section_skip import _write_json

WORDS = re.compile(r'[A-Za-z]+')
CJK = re.compile(r'[\u3400-\u9fff]')
FUNCTION_WORDS = set('the a an this these those is are was were be been of in on for to from and or with by that which it its as can may will have has their we our they'.split())


def substantial_prose(text):
    words = WORDS.findall(text or '')
    return len(words) >= 12 and sum(word.lower() in FUNCTION_WORDS for word in words) >= 3


def incomplete(source, result, target):
    if not isinstance(result, str) or not result.strip():
        return True
    normalized = lambda value: re.sub(r'\s+', '', value).casefold()
    if normalized(source) == normalized(result):
        return True
    if str(target).lower().startswith(('zh', 'chinese')):
        if len(CJK.findall(result)) < 4:
            return True
        # A long English sentence left amid Chinese is still an incomplete translation.
        for span in re.split(r'[\u3400-\u9fff。！？\n]', result):
            if substantial_prose(span):
                return True
    return False


def _record(path, run):
    if not path:
        return
    path = Path(path)
    report = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'runs': []}
    report.setdefault('runs', []).append(run)
    report['status'] = 'failed' if any(item['missing'] for item in report['runs']) else 'passed'
    _write_json(path, report)


def verify_document(translator, document, report_path):
    """Capture originals before the engine's worker threads can mutate them."""
    target = str(translator.translation_config.lang_out)
    source_language = str(getattr(translator.translation_config, 'lang_in', ''))
    enabled = source_language.casefold() != target.casefold()
    originals = [(page, paragraph, deepcopy(paragraph)) for page in document.page for paragraph in page.pdf_paragraph
                 if enabled and not paragraph.vertical and substantial_prose(paragraph.unicode)]

    def finish():
        from babeldoc.format.pdf.document_il.midend.il_translator import ParagraphTranslateTracker
        missing = [(page, paragraph, original) for page, paragraph, original in originals
                   if incomplete(original.unicode, paragraph.unicode, target)]
        repairs = 0
        attempts = 0
        fatal = False
        for page, paragraph, original in missing:
            if fatal:
                break
            translator.translation_config.raise_if_cancelled()
            attempts += 1
            try:
                fonts = {font.font_id: font for font in page.pdf_font}
                for xobj in page.pdf_xobject:
                    if xobj.xobj_id == original.xobj_id:
                        fonts.update({font.font_id: font for font in xobj.pdf_font})
                # Remove optional style tags, retain every formula placeholder and object.
                prepared = translator.get_translate_input(original, fonts, disable_rich_text_translate=True)
                if prepared is None:
                    raise ValueError('Unsupported paragraph composition')
                tracker = ParagraphTranslateTracker()
                tracker.set_pdf_unicode(original.unicode)
                tracker.set_input(prepared.unicode)
                tracker.set_placeholders(prepared.placeholders)
                llm = tracker.new_llm_translate_tracker()
                params = {'paragraph_token_count': translator.calc_token_count(prepared.unicode)}
                if translator.support_llm_translate:
                    prompt = ('[KINBO_COVERAGE_REPAIR]\nThe previous translation was incomplete. Translate every sentence '
                              'into the requested target language and retain all formula placeholders exactly.\n' +
                              translator.generate_prompt_for_llm(prepared.unicode, translate_input=prepared))
                    llm.set_input(prompt)
                    output = translator.translate_engine.llm_translate(prompt, ignore_cache=True, rate_limit_params=params)
                else:
                    output = translator.translate_engine.translate(prepared.unicode, ignore_cache=True, rate_limit_params=params)
                if incomplete(prepared.unicode, output, target):
                    continue
                if any(output.count(item.placeholder) != prepared.unicode.count(item.placeholder)
                       for item in prepared.placeholders):
                    continue
                llm.set_output(output)
                # Apply transactionally. Invalid parsing must not destroy the existing paragraph.
                candidate = deepcopy(original)
                translator.post_translate_paragraph(candidate, tracker, prepared, output)
                if not candidate.pdf_paragraph_composition:
                    continue
                paragraph.unicode = candidate.unicode
                paragraph.pdf_paragraph_composition = candidate.pdf_paragraph_composition
                repairs += 1
            except Exception:
                # A broken credential, quota, endpoint or network should not be tried for every paragraph.
                # Raw provider exceptions can contain credentials. Only counts and pages enter the audit.
                fatal = True
        unresolved = [(page, paragraph) for page, paragraph, original in originals
                      if incomplete(original.unicode, paragraph.unicode, target)]
        run = {'checked': len(originals), 'detected': len(missing), 'repairAttempts': attempts, 'repaired': repairs,
               'missing': len(unresolved), 'pages': sorted({page.page_number + 1 for page, _ in unresolved})}
        _record(report_path, run)
        print('[translation-coverage] ' + json.dumps(run), flush=True)
        if unresolved:
            raise RuntimeError('译文完整性检查失败，仍有未翻译正文。PDF 页码 ' + ', '.join(map(str, run['pages'])) +
                               '。已停止导出成功结果，请检查 API 权限、余额或后台日志')
    return finish


def require_passed(path):
    if not path or not Path(path).is_file():
        raise RuntimeError('译文完整性检查未完成，未将本次任务标为成功')
    report = json.loads(Path(path).read_text(encoding='utf-8'))
    if report.get('status') != 'passed':
        pages = sorted({page for run in report.get('runs', []) for page in run.get('pages', [])})
        suffix = ' PDF 页码 ' + ', '.join(map(str, pages)) if pages else ''
        raise RuntimeError('译文完整性检查失败，仍有未翻译正文或翻译未完成。' + suffix)
