# SPDX-License-Identifier: AGPL-3.0-only
"""Long persistent graphics histories must survive paragraph snapshots."""
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'payload'))
from utils.section_skip_runtime import install_graphics_copy_support

MODULE = 'babeldoc.format.pdf.document_il.frontend.il_creater_active_support'

@dataclass(frozen=True, slots=True)
class Node:
    parent: object
    instruction: str

class GraphicsCopyTests(unittest.TestCase):
    def test_actual_engine_short_and_long_histories_preserve_clipping_and_transforms(self):
        try:
            from babeldoc.format.pdf.document_il.frontend.il_creater_active_support import (
                LazyPassthroughInstruction, PassthroughSnapshot, append_passthrough_instruction,
            )
            from babeldoc.format.pdf.document_il import GraphicState, PdfStyle, PdfCharacter
        except ImportError:
            self.skipTest('Run with the translation engine Python for the native graphics check')
        install_graphics_copy_support()
        for length in (0, 1, 32, 3000, 10000):
            for clipping in (False, True):
                with self.subTest(length=length, clipping=clipping):
                    snapshot = PassthroughSnapshot()
                    for index in range(length):
                        snapshot = append_passthrough_instruction(snapshot, ('rg', f'{index % 10 / 10} 0.2 0.3'))
                    snapshot = append_passthrough_instruction(snapshot, ('W n', '0 0 40 50 re'))
                    lazy = LazyPassthroughInstruction(snapshot, include_clipping=clipping,
                                                      suffix_parts=('q 1 0 0 1 20 30 cm', 'Q'))
                    character = PdfCharacter(pdf_style=PdfStyle(graphic_state=GraphicState(
                        passthrough_per_char_instruction=lazy)))
                    copied = deepcopy([character, character, lazy])
                    value = copied[0].pdf_style.graphic_state.passthrough_per_char_instruction
                    self.assertIsInstance(value, str)
                    self.assertEqual(value, lazy.materialize())
                    self.assertIs(copied[0], copied[1])
                    self.assertIs(copied[2], value)
                    self.assertEqual('W n' in value, clipping)
                    self.assertTrue(value.endswith('q 1 0 0 1 20 30 cm Q'))

    def test_long_history_is_copied_as_exact_value_and_shared_references_survive(self):
        class Lazy:
            def __init__(self, tail):
                self.tail = tail
            def materialize(self):
                values, node = [], self.tail
                while node is not None:
                    values.append(node.instruction)
                    node = node.parent
                return ' '.join(reversed(values)) + ' Q'
        tail = Node(None, 'q 1 0 0 1 20 30 cm 0 0 100 100 re W n')
        for _ in range(2500):
            tail = Node(tail, '0.2 0.3 0.4 rg')
        lazy = Lazy(tail)
        paragraph = SimpleNamespace(first=lazy, second=lazy)
        with self.assertRaises(RecursionError):
            deepcopy(paragraph)
        limit = sys.getrecursionlimit()
        with patch.dict(sys.modules, {MODULE: SimpleNamespace(LazyPassthroughInstruction=Lazy)}):
            install_graphics_copy_support()
            first_method = Lazy.__deepcopy__
            install_graphics_copy_support()
            self.assertIs(Lazy.__deepcopy__, first_method)
            snapshot = deepcopy(paragraph)
        self.assertEqual(snapshot.first, lazy.materialize())
        self.assertIs(snapshot.first, snapshot.second)
        self.assertIs(lazy.tail, tail)
        self.assertEqual(sys.getrecursionlimit(), limit)

    def test_preserves_an_engine_provided_copy_implementation(self):
        class Lazy:
            def __deepcopy__(self, memo):
                return 'engine implementation'
        method = Lazy.__deepcopy__
        with patch.dict(sys.modules, {MODULE: SimpleNamespace(LazyPassthroughInstruction=Lazy)}):
            install_graphics_copy_support()
        self.assertIs(Lazy.__deepcopy__, method)

    def test_engine_without_lazy_instructions_remains_compatible(self):
        with patch.dict(sys.modules, {MODULE: SimpleNamespace()}):
            install_graphics_copy_support()

    def test_rendering_failures_are_reported_without_dropping_graphics(self):
        class Lazy:
            def materialize(self):
                raise ValueError('Invalid graphics snapshot')
        with patch.dict(sys.modules, {MODULE: SimpleNamespace(LazyPassthroughInstruction=Lazy)}):
            install_graphics_copy_support()
        with self.assertRaisesRegex(ValueError, 'Invalid graphics snapshot'):
            deepcopy(Lazy())

if __name__ == '__main__':
    unittest.main()
