# SPDX-License-Identifier: AGPL-3.0-only
import base64
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'payload'))
from utils import page_images, shared_api


class PageImageTests(unittest.TestCase):
    def setUp(self):
        self.profile = shared_api.APIProfile('deepseek', 'DS', 'deepseek-flash', 'https://api.deepseek.com/v1', 'fixture-private')
        with pymupdf.open() as pdf:
            for index in range(3):
                page = pdf.new_page(width=300 + index, height=400)
                page.insert_text((30, 40), 'PAGE_' + str(index + 1))
            self.pdf = pdf.tobytes()

    def test_auto_and_explicit_modes_do_not_substitute_models(self):
        self.assertEqual(page_images.select_mode(self.profile), 'images')
        with self.assertRaisesRegex(ValueError, 'PDF'):
            page_images.select_mode(self.profile, 'pdf')
        with self.assertRaisesRegex(ValueError, 'deepseek-flash'):
            page_images.select_mode(shared_api.APIProfile('deepseek', 'DS', 'deepseek-chat', self.profile.endpoint, 'fixture'))

    def test_all_pages_are_full_size_and_preserved_in_every_protocol_and_continuation(self):
        with patch.object(pymupdf.Page, 'get_text', side_effect=AssertionError('No local text extraction')):
            images = page_images.render_all(self.pdf, self.profile)
        self.assertEqual([image['page'] for image in images], [1, 2, 3])
        self.assertEqual([(i['width'], i['height']) for i in images], [(600, 800), (602, 800), (604, 800)])
        for item in images:
            self.assertTrue(base64.b64decode(item['data']).startswith(b'\x89PNG'))
        for protocol in ('chat', 'responses', 'gemini'):
            _, body, _, _ = shared_api.pdf_request(self.profile, self.pdf, 'paper.pdf', 'EXACT_PROMPT', protocol, images=images)
            encoded = json.dumps(body)
            self.assertNotIn('application/pdf', encoded)
            self.assertIn('EXACT_PROMPT', encoded)
            for item in images:
                self.assertEqual(encoded.count(item['data']), 1)
            response = ({'choices': [{'message': {'content': 'partial', 'reasoning_content': 'opaque'}}]} if protocol == 'chat' else
                        {'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'partial'}]}]} if protocol == 'responses' else
                        {'candidates': [{'content': {'parts': [{'text': 'partial', 'thoughtSignature': 'opaque'}]}}]})
            continued = json.dumps(shared_api.continue_pdf_request(body, response, protocol))
            for item in images:
                self.assertEqual(continued.count(item['data']), 1)
            for forbidden in ('max_tokens', 'max_output_tokens', 'reasoning_effort', 'generationConfig'):
                self.assertNotIn(forbidden, continued)

    def test_cancel_and_oversized_request_stop_without_network_or_partial_input(self):
        with self.assertRaises(InterruptedError):
            page_images.render_all(self.pdf, self.profile, cancelled=lambda: True)
        with patch.object(page_images, 'DEEPSEEK_BODY_LIMIT', 40):
            with self.assertRaisesRegex(ValueError, '48 MiB'):
                page_images.render_all(self.pdf, self.profile)
            with self.assertRaisesRegex(ValueError, '未发送'):
                page_images.serialize(self.profile, {'input': 'x' * 100})


if __name__ == '__main__':
    unittest.main()
