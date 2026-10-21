# SPDX-License-Identifier: AGPL-3.0-only
# Body-only modifications by ZhangLinqi-07, 2026-10-21. See NOTICE.md.
"""Per-process BabelDOC filtering for a locally generated, immutable section plan."""
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
import argparse
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.section_skip import should_skip_paragraph


@contextmanager
def body_paragraphs(document, plan, guard=None):
    saved = []
    removed = 0
    try:
        if guard is not None:
            guard.remember_document(document)
        for page in document.page:
            original = page.pdf_paragraph
            kept = [p for p in original if not should_skip_paragraph(page.page_number, p.box, plan)
                    and not (guard is not None and guard.remember(page, p))]
            removed += len(original) - len(kept)
            saved.append((page, original, {id(p) for p in original}))
            page.pdf_paragraph = kept
        print(f'[section-skip] Excluded {removed} terminal-section paragraphs from this model stage.', flush=True)
        yield
    finally:
        for page, original, identities in saved:
            # The translator may append overflow paragraphs. Preserve these as
            # well as original unmodified references for the PDF renderer.
            added = [p for p in page.pdf_paragraph if id(p) not in identities]
            page.pdf_paragraph = original + added


def install_filters(plan):
    from importlib.metadata import version
    if version('pdf2zh-next') != '2.9.0' or version('babeldoc') != '0.6.2':
        raise RuntimeError('Body-only requires pdf2zh-next 2.9.0 and BabelDOC 0.6.2; no model request has been sent.')
    install_graphics_copy_support()
    from babeldoc.format.pdf.document_il.midend.automatic_term_extractor import AutomaticTermExtractor
    from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
    from babeldoc.format.pdf.document_il.midend.il_translator_llm_only import ILTranslatorLLMOnly
    from utils.layout_preservation import LayoutGuard
    guard = LayoutGuard(plan) if plan.get('layout') else None
    if guard is not None:
        guard.install()

    def wrap(original, coverage=False):
        if getattr(original, '_zotero_section_filter', False):
            return original
        @wraps(original)
        def filtered(self, document, *args, **kwargs):
            with body_paragraphs(document, plan, guard):
                if coverage:
                    from utils.translation_coverage import verify_document
                    translator = getattr(self, 'il_translator', self)
                    finish = verify_document(translator, document, plan.get('coverageReport'))
                result = original(self, document, *args, **kwargs)
                if coverage:
                    finish()
                return result
        filtered._zotero_section_filter = True
        return filtered

    AutomaticTermExtractor.procress = wrap(AutomaticTermExtractor.procress)
    ILTranslator.translate = wrap(ILTranslator.translate, True)
    ILTranslatorLLMOnly.translate = wrap(ILTranslatorLLMOnly.translate, True)


def copy_graphics_instruction(instruction, memo):
    """Freeze lazy graphics as their exact string value, without copying history.

    BabelDOC may store thousands of persistent linked graphics-state nodes in
    one string-compatible instruction. Generic deepcopy follows every parent
    recursively. Materialization already walks that history iteratively and
    preserves clipping, transforms, colours, and suffix instructions.
    """
    value = instruction.materialize()
    memo[id(instruction)] = value
    return value


def install_graphics_copy_support():
    # Only this translation subprocess is patched. Older compatible engine
    # builds store plain strings and do not expose the lazy wrapper.
    try:
        from babeldoc.format.pdf.document_il.frontend.il_creater_active_support import LazyPassthroughInstruction
    except ImportError:
        return
    if '__deepcopy__' not in LazyPassthroughInstruction.__dict__:
        LazyPassthroughInstruction.__deepcopy__ = copy_graphics_instruction


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('engine_args', nargs=argparse.REMAINDER)
    options = parser.parse_args()
    plan = json.loads(Path(options.plan).read_text(encoding='utf-8'))
    # Windows starts BabelDOC in a fresh Python process. Its __mp_main__ import
    # must install the same filter before invoking the native worker target.
    os.environ['ZOTERO_PDF2ZH_SECTION_PLAN'] = str(Path(options.plan).resolve())
    plan['coverageReport'] = str(Path(options.plan).with_suffix('.coverage.json'))
    from utils.section_skip import _write_json
    _write_json(Path(plan['coverageReport']), {'status': 'pending', 'runs': []})
    install_filters(plan)
    engine_args = options.engine_args
    if engine_args and engine_args[0] == '--':
        engine_args = engine_args[1:]
    sys.argv = ['pdf2zh_next', *engine_args]
    from pdf2zh_next.main import cli
    try:
        cli()
    except SystemExit as result:
        if result.code not in (None, 0):
            raise
    from utils.translation_coverage import require_passed
    require_passed(plan['coverageReport'])
    from utils.layout_overflow import finish_layout_outputs
    finish_layout_outputs(plan, engine_args)


if __name__ == '__mp_main__' and os.environ.get('ZOTERO_PDF2ZH_SECTION_PLAN'):
    child_plan_path = Path(os.environ['ZOTERO_PDF2ZH_SECTION_PLAN'])
    child_plan = json.loads(child_plan_path.read_text(encoding='utf-8'))
    child_plan['coverageReport'] = str(child_plan_path.with_suffix('.coverage.json'))
    install_filters(child_plan)

if __name__ == '__main__':
    main()
