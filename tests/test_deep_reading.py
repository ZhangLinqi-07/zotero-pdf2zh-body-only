# SPDX-License-Identifier: AGPL-3.0-only
import base64
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from flask import Flask
import pymupdf
import toml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'payload'))
from utils import shared_api
from utils.deep_reading import register_reading, ReadingManager, CHUNK_PROMPT


class StructuredReadingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='structured-reading-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'config').mkdir()
        (self.root / 'prompts').mkdir()
        shutil.copy2(ROOT / 'payload/prompts/deep_reading_zh.txt', self.root / 'prompts/deep_reading_zh.txt')
        self.app = Flask(__name__)
        self.app.testing = True
        self.manager = register_reading(self.app, self.root)
        self.client = self.app.test_client()
        self.key = 'local-private-fixture-key'

    def configured(self):
        data = {'siliconflowfree': True, 'openaicompatible_detail': {
            'openai_compatible_api_key': self.key, 'openai_compatible_model': 'local-reading-model',
            'openai_compatible_base_url': 'http://127.0.0.1:19876/v1'}}
        (self.root / 'config/config.toml').write_text(toml.dumps(data), encoding='utf-8')

    def pdf(self, pages=2, dense=False):
        with pymupdf.open() as document:
            for index in range(pages):
                page = document.new_page()
                text = f'Source page {index + 1}. Evidence must retain its page. LAST_PAGE_{index + 1}.\n'
                text += ('Scientific claims require robustness audits and clear assumptions.\n' * (48 if dense else 4))
                page.insert_textbox((50, 70, 540, 760), text, fontsize=8)
                page.draw_rect((70, 770, 180, 790))
            return document.tobytes()

    def upload(self, **kwargs):
        response = self.client.post('/api/reading/documents', data={'file': (io.BytesIO(self.pdf(**kwargs)), 'paper.pdf')}, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200, response.data)
        return response.json['document']

    def wait_job(self, job_id):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = self.client.get('/api/reading/jobs/' + job_id).json['job']
            if result['state'] != 'running':
                return result
            time.sleep(.02)
        self.fail('Reading job did not complete')

    def test_free_translation_cannot_start_reading_without_user_api(self):
        document = self.upload()
        with patch.object(shared_api, 'chat') as call:
            response = self.client.post('/api/reading/jobs', json={'documentId': document['id']})
        self.assertEqual(response.status_code, 400)
        self.assertIn('自己的 API', response.json['message'])
        call.assert_not_called()

    def test_translation_api_is_reused_without_returning_the_key(self):
        self.configured()
        response = self.client.get('/api/reading/config')
        self.assertEqual(response.json['profiles'][0]['model'], 'local-reading-model')
        self.assertNotIn(self.key, response.get_data(as_text=True))
        self.assertNotIn(self.key, repr(shared_api.resolve(self.root / 'config')))
        document = self.upload()
        calls = []
        def answer(profile, messages, limit):
            calls.append((profile, messages))
            return '## 方法\n\n公式为 $x_i^2$。\n\n$$E=mc^2$$\n\n研究边界见 PDF 第 2 页。', {'prompt_tokens': 50, 'completion_tokens': 20, 'total_tokens': 70}, 'stop'
        with patch.object(shared_api, 'chat', side_effect=answer):
            response = self.client.post('/api/reading/jobs', json={'documentId': document['id']})
            job = self.wait_job(response.json['job']['id'])
        self.assertEqual(job['state'], 'completed')
        self.assertEqual(calls[0][0].key, self.key)
        self.assertIn('论文基本信息', calls[0][1][0]['content'])
        self.assertIn('未核实', calls[0][1][0]['content'])
        self.assertEqual(job['usage']['total_tokens'], 70)
        self.assertEqual(job['apiCalls'], 1)
        self.assertNotIn(self.key, job['markdown'])
        self.assertIsNone(job['estimatedCny'])
        download = self.client.get('/api/reading/jobs/' + job['id'] + '/download')
        self.assertEqual(download.status_code, 200)
        self.assertIn(b'$x_i^2$', download.data)
        download.close()

    def test_shared_configuration_updates_translation_table_and_keeps_other_settings(self):
        self.configured()
        response = self.client.post('/api/reading/config', json={'endpoint': 'https://example.org/v1', 'model': 'new-model', 'apiKey': ''})
        self.assertEqual(response.status_code, 200)
        data = toml.load(self.root / 'config/config.toml')
        self.assertEqual(data['openaicompatible_detail']['openai_compatible_api_key'], self.key)
        self.assertEqual(data['openaicompatible_detail']['openai_compatible_model'], 'new-model')
        self.assertEqual(data['openaicompatible_detail']['support_llm'], 'yes')
        self.assertTrue(data['siliconflowfree'])
        self.assertNotIn(self.key, response.get_data(as_text=True))

    def test_zotero_saved_api_can_sync_without_a_paid_translation_first(self):
        response = self.client.post('/api/reading/sync-translation-api', json={
            'service': 'openailiked', 'model': 'already-in-zotero', 'apiKey': self.key,
            'apiUrl': 'https://example.org/v1'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.key, response.get_data(as_text=True))
        self.assertEqual(shared_api.resolve(self.root / 'config').model, 'already-in-zotero')

    def test_long_paper_covers_the_final_page_instead_of_truncating_it(self):
        self.configured()
        self.manager.configure({'contextChars': 8000})
        document = self.upload(pages=8, dense=True)
        seen = []
        def answer(profile, messages, limit):
            seen.append(messages)
            text = '逐段证据，见 PDF 原始页码。' if CHUNK_PROMPT in messages[0]['content'] else '## 阅读笔记\n\n全文证据已经汇总。'
            return text, {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}, 'stop'
        with patch.object(shared_api, 'chat', side_effect=answer):
            result = self.client.post('/api/reading/jobs', json={'documentId': document['id']})
            job = self.wait_job(result.json['job']['id'])
        self.assertEqual(job['state'], 'completed')
        self.assertGreater(job['chunks'], 1)
        self.assertEqual(job['apiCalls'], job['chunks'] + 1)
        self.assertIn('LAST_PAGE_8', '\n'.join(str(messages) for messages in seen[:-1]))

    def test_vision_is_explicit_and_images_are_sent_only_when_selected(self):
        self.configured()
        document = self.upload()
        images = []
        def answer(profile, messages, limit):
            images.extend(part for part in messages[-1]['content'] if part.get('type') == 'image_url')
            return '## 图表\n\n已提供图像。', {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}, 'stop'
        with patch.object(shared_api, 'chat', side_effect=answer):
            result = self.client.post('/api/reading/jobs', json={'documentId': document['id'], 'vision': True})
            job = self.wait_job(result.json['job']['id'])
        self.assertEqual(job['state'], 'completed')
        self.assertEqual(len(images), 2)
        self.assertTrue(images[0]['image_url']['url'].startswith('data:image/jpeg;base64,'))

    def test_output_limit_is_visible_and_continuation_is_bounded(self):
        self.configured()
        document = self.upload()
        with patch.object(shared_api, 'chat', return_value=('未完成内容。', {'prompt_tokens': 1, 'completion_tokens': 1}, 'length')) as call:
            result = self.client.post('/api/reading/jobs', json={'documentId': document['id']})
            job = self.wait_job(result.json['job']['id'])
        self.assertEqual(call.call_count, 2)
        self.assertEqual(job['state'], 'partial')
        self.assertIn('本稿尚未完成', job['markdown'])

    def test_own_pricing_and_recharge_ratio_are_used_without_inventing_a_rate(self):
        self.configured()
        self.manager.configure({'inputPrice': 1, 'outputPrice': 3, 'unitCny': 1})
        document = self.upload()
        with patch.object(shared_api, 'chat', return_value=('报告完成。', {'prompt_tokens': 1000, 'completion_tokens': 2000, 'total_tokens': 3000}, 'stop')):
            result = self.client.post('/api/reading/jobs', json={'documentId': document['id']})
            job = self.wait_job(result.json['job']['id'])
        self.assertAlmostEqual(job['estimatedCny'], .007)

    def test_missing_usage_never_becomes_a_zero_fee_estimate(self):
        self.configured()
        self.manager.configure({'inputPrice': 1, 'outputPrice': 3, 'unitCny': 1})
        document = self.upload()
        with patch.object(shared_api, 'chat', return_value=('报告完成。', {}, 'stop')):
            result = self.client.post('/api/reading/jobs', json={'documentId': document['id']})
            job = self.wait_job(result.json['job']['id'])
        self.assertFalse(job['usageComplete'])
        self.assertIsNone(job['estimatedCny'])

    def test_shared_endpoint_accepts_full_chat_url_without_breaking_translation(self):
        self.configured()
        response = self.client.post('/api/reading/config', json={'endpoint': 'https://example.org/v1/chat/completions', 'model': 'new-model'})
        self.assertEqual(response.status_code, 200)
        profile = shared_api.resolve(self.root / 'config')
        self.assertEqual(profile.endpoint, 'https://example.org/v1')

    def test_cross_site_mutations_and_path_traversal_are_rejected(self):
        response = self.client.post('/api/reading/config', json={}, headers={'Origin': 'https://attacker.invalid'})
        self.assertEqual(response.status_code, 403)
        response = self.client.post('/api/reading/documents', json={'existingFile': '../secret.pdf'})
        self.assertEqual(response.status_code, 400)
        response = self.client.get('/api/reading/documents/not-an-id')
        self.assertEqual(response.status_code, 400)

    def test_backend_restart_marks_unfinished_jobs_as_interrupted(self):
        job_id = 'f' * 32
        self.manager.path(job_id, '.job.json').write_text(json.dumps({'id': job_id, 'state': 'running'}))
        self.assertEqual(self.manager.snapshot(job_id)['state'], 'interrupted')

    def bound_document(self):
        target = {'clientID': 'a' * 32, 'libraryID': 1, 'parentKey': 'ABCD1234',
                  'attachmentKey': 'PDFK1234', 'title': 'Original parent paper'}
        result = self.client.post('/api/reading/documents', json={
            'fileName': 'paper.pdf', 'fileContent': base64.b64encode(self.pdf()).decode(), 'zoteroTarget': target})
        self.assertEqual(result.status_code, 200)
        return result.json['document'], target

    def test_completed_reading_queues_the_original_parent_and_survives_restart(self):
        self.configured()
        document, target = self.bound_document()
        with patch.object(shared_api, 'chat', return_value=('## Evidence\n\n$x_i$ and $$E=mc^2$$', {}, 'stop')):
            result = self.client.post('/api/reading/jobs', json={'documentId': document['id'], 'zoteroTarget': {'parentKey': 'WRONGKEY'}})
            job = self.wait_job(result.json['job']['id'])
        self.assertEqual(job['zoteroTarget'], target)
        self.assertEqual(job['noteState'], 'pending')
        self.assertEqual(self.manager.pending_notes('b' * 32), [])
        restarted = ReadingManager(self.root)
        self.assertEqual(restarted.pending_notes(target['clientID'])[0]['id'], job['id'])
        saved = restarted.acknowledge_note(job['id'], {'clientID': target['clientID'], 'state': 'saved', 'noteKey': 'NOTE1234'})
        self.assertEqual(saved['noteState'], 'saved')
        self.assertEqual(restarted.pending_notes(target['clientID']), [])
        self.assertEqual(restarted.acknowledge_note(job['id'], {'clientID': target['clientID'], 'state': 'saved', 'noteKey': 'NOTE1234'})['noteKey'], 'NOTE1234')
        with self.assertRaises(ValueError):
            restarted.acknowledge_note(job['id'], {'clientID': target['clientID'], 'state': 'saved', 'noteKey': 'OTHER123'})

    def test_note_ack_rejects_other_clients_and_retries_without_more_model_calls(self):
        self.configured()
        document, target = self.bound_document()
        with patch.object(shared_api, 'chat', return_value=('A complete report', {}, 'stop')) as model:
            result = self.client.post('/api/reading/jobs', json={'documentId': document['id']})
            job = self.wait_job(result.json['job']['id'])
            route = '/api/reading/jobs/' + job['id'] + '/zotero-note'
            self.assertEqual(self.client.post(route, json={'clientID': 'b' * 32, 'state': 'saved', 'noteKey': 'NOTE1234'}).status_code, 400)
            failed = self.client.post(route, json={'clientID': target['clientID'], 'state': 'error'})
            self.assertEqual(failed.json['job']['noteState'], 'error')
            self.assertEqual(len(self.client.get('/api/reading/zotero/pending?clientID=' + target['clientID']).json['jobs']), 1)
            self.assertEqual(self.client.post(route, json={'clientID': target['clientID'], 'state': 'saved', 'noteKey': 'NOTE1234'}).status_code, 200)
        self.assertEqual(model.call_count, 1)

    def test_invalid_zotero_target_is_rejected_before_document_creation(self):
        for target in ({}, {'clientID': 'a' * 32, 'libraryID': True, 'parentKey': 'ABCD1234', 'attachmentKey': 'PDFK1234'}):
            response = self.client.post('/api/reading/documents', json={'fileName': 'paper.pdf', 'fileContent': base64.b64encode(self.pdf()).decode(), 'zoteroTarget': target})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(list(self.manager.folder.glob('*.pdf')), [])

    def test_unbound_web_upload_does_not_guess_a_zotero_parent(self):
        self.configured()
        document = self.upload()
        with patch.object(shared_api, 'chat', return_value=('A complete report', {}, 'stop')):
            result = self.client.post('/api/reading/jobs', json={'documentId': document['id']})
            job = self.wait_job(result.json['job']['id'])
        self.assertNotIn('noteState', job)
        self.assertEqual(self.manager.pending_notes('a' * 32), [])

    def test_double_click_reuses_running_reading_without_a_second_api_call(self):
        self.configured()
        first, target = self.bound_document()
        second = self.manager.add_document(self.manager.path(first['id'], '.pdf').read_bytes(), 'same-paper.pdf', target)
        entered, release = threading.Event(), threading.Event()
        def model(*args):
            entered.set()
            release.wait(4)
            return 'Completed report', {}, 'stop'
        with patch.object(shared_api, 'chat', side_effect=model) as call:
            initial = self.client.post('/api/reading/jobs', json={'documentId': first['id']}).json['job']
            self.assertTrue(entered.wait(2))
            try:
                repeat = self.client.post('/api/reading/jobs', json={'documentId': second['id']}).json['job']
                self.assertEqual(initial['id'], repeat['id'])
            finally:
                release.set()
                self.wait_job(initial['id'])
                if 'repeat' in locals():
                    self.wait_job(repeat['id'])
        self.assertEqual(call.call_count, 1)


if __name__ == '__main__':
    unittest.main()
