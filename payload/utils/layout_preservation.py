# SPDX-License-Identifier: AGPL-3.0-only
"""Conservative, job-local guards for mathematical and two-column papers."""
from copy import deepcopy
from dataclasses import fields
from functools import wraps
import json
from pathlib import Path
import tempfile

from utils.section_skip import _write_json

DEFAULTS = {"preserveColumns": True, "mathMode": "auto"}


def read_layout_settings(config_folder):
    path = Path(config_folder) / "layout.json"
    return {**DEFAULTS, **(json.loads(path.read_text(encoding="utf-8")) if path.exists() else {})}


def save_layout_settings(config_folder, data):
    settings = read_layout_settings(config_folder)
    if "preserveColumns" in data:
        if not isinstance(data["preserveColumns"], bool):
            raise ValueError("保留双栏选项必须是布尔值")
        settings["preserveColumns"] = data["preserveColumns"]
    if "mathMode" in data:
        if data["mathMode"] not in {"off", "auto", "conservative"}:
            raise ValueError("请选择有效的公式保护模式")
        settings["mathMode"] = data["mathMode"]
    _write_json(Path(config_folder) / "layout.json", settings)
    return settings


def prepare_layout_command(command, config_folder, input_path, settings=None):
    settings = settings or read_layout_settings(config_folder)
    if not settings["preserveColumns"] and settings["mathMode"] == "off":
        return command
    result = list(command)
    marker = "--zotero-section-skip-plan"
    plan = {"detected": False}
    if marker in result:
        index = result.index(marker)
        plan = json.loads(Path(result[index + 1]).read_text(encoding="utf-8"))
        del result[index:index + 2]
    plan["layout"] = settings
    folder = Path(config_folder) / "layout_plans"
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", prefix="layout-", dir=folder, encoding="utf-8", delete=False) as handle:
        plan["layoutReport"] = str(Path(handle.name).with_suffix(".report.json"))
        json.dump(plan, handle, ensure_ascii=False)
        name = handle.name
    if settings["mathMode"] != "off":
        # Keep fraction bars and drawing primitives. OCR workaround intentionally
        # paints backgrounds, so do not force it for vector mathematical pages.
        for flag in ("--no-remove-non-formula-lines",):
            if flag not in result:
                result.append(flag)
    return [*result, marker, name]


def formula_density(paragraph):
    formulas = [getattr(c, "pdf_formula", None) for c in getattr(paragraph, "pdf_paragraph_composition", [])]
    formulas = [formula for formula in formulas if formula is not None]
    characters = sum(len(getattr(formula, "pdf_character", [])) for formula in formulas)
    text = getattr(paragraph, "unicode", "") or ""
    return len(formulas), characters, characters / max(1, len(text.replace(" ", "")))


def protect_formula(paragraph, mode):
    if mode == "off":
        return False
    label = (getattr(paragraph, "layout_label", "") or "").lower()
    count, characters, density = formula_density(paragraph)
    if "formula" in label or "equation" in label:
        return True
    threshold = .16 if mode == "conservative" else .45
    return count > 0 and characters >= 3 and density >= threshold


def column_boundary(page):
    box = getattr(getattr(page, "cropbox", None), "box", None)
    if box is None or box.x is None or box.x2 is None:
        return None
    mid = (box.x + box.x2) / 2
    left, right, wide = [], [], 0
    for paragraph in page.pdf_paragraph:
        rect = paragraph.box
        text = getattr(paragraph, "unicode", "") or ""
        if rect is None or len(text) < 20 or any(getattr(rect, k, None) is None for k in ("x", "x2")):
            continue
        if rect.x2 <= mid + 5:
            left.append(rect.x2)
        elif rect.x >= mid - 5:
            right.append(rect.x)
        else:
            wide += 1
    if len(left) >= 2 and len(right) >= 2 and wide <= len(left) + len(right):
        return (max(left) + min(right)) / 2
    return None


def restore_paragraph(target, original):
    for field in fields(original):
        setattr(target, field.name, deepcopy(getattr(original, field.name)))


class LayoutGuard:
    def __init__(self, plan):
        self.settings = plan.get("layout", {"preserveColumns": False, "mathMode": "off"})
        self.report_path = plan.get("layoutReport")
        self.originals = {}
        self.protected = set()
        self.pages = {}
        self.columns = {}
        self.fallbacks = []
        self.optimal_scales = {}

    def remember(self, page, paragraph):
        key = id(paragraph)
        if key not in self.originals:
            self.originals[key] = deepcopy(paragraph)
            self.pages[key] = page.page_number
            if protect_formula(paragraph, self.settings["mathMode"]):
                self.protected.add(key)
        return key in self.protected

    def remember_document(self, document):
        for page in document.page:
            self.columns.setdefault(page.page_number, column_boundary(page) if self.settings["preserveColumns"] else None)
            for paragraph in page.pdf_paragraph:
                self.remember(page, paragraph)

    def report(self):
        data = {"protectedFormulaParagraphs": len(self.protected), "fallbacks": list(self.fallbacks),
                "twoColumnPages": [number + 1 for number, middle in self.columns.items() if middle is not None]}
        if self.report_path:
            _write_json(Path(self.report_path), data)
        return data

    def install(self):
        from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
        if self.settings['mathMode'] != 'off':
            from babeldoc.format.pdf.document_il.utils import formular_helper
            original_font = formular_helper.is_formulas_font
            if not getattr(original_font, '_zotero_math_font', False):
                import re
                import base64
                @wraps(original_font)
                def formula_font(name, pattern):
                    decoded = name
                    if name.startswith('BASE64:'):
                        try:
                            decoded = base64.b64decode(name[7:]).decode('latin-1')
                        except (ValueError, UnicodeError):
                            pass
                    if re.search(r'Cambria[ -]?Math', decoded, re.I):
                        return True
                    return original_font(name, pattern)
                formula_font._zotero_math_font = True
                formular_helper.is_formulas_font = formula_font
        if getattr(Typesetting.render_paragraph, "_zotero_layout_guard", False):
            return
        original_render = Typesetting.render_paragraph
        original_right = Typesetting.get_max_right_space
        original_document = Typesetting.typesetting_document
        original_optimal = Typesetting._get_optimal_scale
        original_preprocess = Typesetting.preprocess_document
        guard = self

        @wraps(original_optimal)
        def optimal(self, paragraph, page, units, *args, **kwargs):
            scale = original_optimal(self, paragraph, page, units, *args, **kwargs)
            guard.optimal_scales[id(paragraph)] = scale
            return scale

        @wraps(original_preprocess)
        def preprocess(self, document, pbar):
            result = original_preprocess(self, document, pbar)
            # A single verbose translation must not shrink every paragraph in
            # the document through BabelDOC's global weighted modal scale.
            for page in document.page:
                for paragraph in page.pdf_paragraph:
                    if id(paragraph) in guard.optimal_scales:
                        paragraph.optimal_scale = guard.optimal_scales[id(paragraph)]
            return result

        @wraps(original_document)
        def document(self, document):
            guard.remember_document(document)
            try:
                return original_document(self, document)
            finally:
                guard.report()

        @wraps(original_right)
        def right_space(self, box, page):
            result = original_right(self, box, page)
            middle = guard.columns.get(page.page_number)
            if middle is not None and box.x2 <= middle + 3:
                result = min(result, max(box.x2, middle - 5))
            return result

        @wraps(original_render)
        def render(self, paragraph, page, fonts):
            key = id(paragraph)
            original = guard.originals.get(key)
            if key in guard.protected:
                restore_paragraph(paragraph, original)
                return
            curve_count, form_count = len(page.pdf_curve), len(page.pdf_form)
            result = original_render(self, paragraph, page, fonts)
            if original is None:
                return result
            reason = None
            scale = getattr(paragraph, "scale", 1) or 1
            compositions = getattr(paragraph, "pdf_paragraph_composition", [])
            if scale < .55 or (original.pdf_paragraph_composition and not compositions):
                reason = "译文无法在可读字号下排入原版面"
            middle = guard.columns.get(page.page_number)
            if middle is not None and original.box and original.box.x2 <= middle:
                for item in compositions:
                    char = getattr(item, "pdf_character", None)
                    if char and char.box and char.box.x2 > middle + 1:
                        reason = "译文跨越原有栏间距"
                        break
            if guard.settings['mathMode'] != 'off':
                protected_boxes = [guard.originals[key].box for key in guard.protected
                                   if guard.pages[key] == page.page_number and guard.originals[key].box]
                for item in compositions:
                    char = getattr(item, 'pdf_character', None)
                    if char is None or char.box is None:
                        continue
                    box = char.box
                    if any(min(box.x2, math.x2) - max(box.x, math.x) > 1
                           and min(box.y2, math.y2) - max(box.y, math.y) > 1 for math in protected_boxes):
                        reason = '译文侵入保留的公式区域'
                        break
            if reason:
                del page.pdf_curve[curve_count:]
                del page.pdf_form[form_count:]
                restore_paragraph(paragraph, original)
                guard.fallbacks.append({"page": page.page_number + 1, "reason": reason})
            return result

        render._zotero_layout_guard = True
        Typesetting.typesetting_document = document
        Typesetting._get_optimal_scale = optimal
        Typesetting.preprocess_document = preprocess
        Typesetting.get_max_right_space = right_space
        Typesetting.render_paragraph = render

