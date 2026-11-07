import base64
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
import fetch_interests as discovery
import gemini_chat
import server


def pdf_bytes(text=None):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    if text:
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
            DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 12 Tf 50 700 Td ({text}) Tj ET'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [patch.object(discovery, 'ROOT', self.root), patch.object(server, 'ROOT', self.root)]
        for p in self.patches:
            p.start()
        self.sid = 'a' * 43
        self.profile = {'name': 'Example Person', 'profession': 'Researcher',
                        'interests': 'Privacy', 'cv': {'filename': 'cv.pdf',
                        'data': base64.b64encode(pdf_bytes('Python network analysis')).decode()}}

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_pdf_and_profile_save(self):
        saved = server.save_profile(self.sid, self.profile)
        self.assertIn('Python network analysis', saved['cv']['text'])
        self.assertEqual(saved['cv']['text_status'], 'ready')
        self.assertEqual(discovery.extract_cv_text(pdf_bytes())['text_status'], 'needs_ocr')
        with self.assertRaises(ValueError):
            discovery.extract_cv_text(b'not a PDF')
        before = discovery.profile_fingerprint(saved)
        for key in ('profession', 'interests'):
            changed = {**saved, key: 'Different'}
            self.assertNotEqual(before, discovery.profile_fingerprint(changed))
        changed = {**saved, 'cv': {**saved['cv'], 'stored_file': 'different.pdf'}}
        self.assertNotEqual(before, discovery.profile_fingerprint(changed))
        # Name edits should not consume another Gemini query generation call.
        self.assertEqual(before, discovery.profile_fingerprint({**saved, 'name': 'New Name'}))

    def test_queries_use_all_inputs_without_sending_name_or_contacts(self):
        profile = {'name': 'Example Person', 'profession': 'Researcher', 'interests': 'Privacy',
                   'cv': {'text': 'Example Person example@test.com +1 403 555 0123 Python network analysis'}}
        queries = ['privacy research papers', 'network analysis tutorials', 'Python privacy engineering']
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test', 'GEMINI_MODEL': 'test'}), patch('gemini_chat.genai.Client') as factory:
            model = factory.return_value.__enter__.return_value.models
            model.generate_content.return_value = SimpleNamespace(text=json.dumps({'queries': queries}))
            self.assertEqual(gemini_chat.build_discovery_queries(profile), queries)
            payload = model.generate_content.call_args.kwargs['contents']
            self.assertIn('Python network analysis', payload)
            self.assertIn('Privacy', payload)
            self.assertIn('Researcher', payload)
            self.assertNotIn('example@test.com', payload)
            self.assertNotIn('Example Person', payload)
            model.generate_content.return_value = SimpleNamespace(text='{"queries":["one"]}')
            with self.assertRaises(RuntimeError):
                gemini_chat.build_discovery_queries(profile)

    def test_query_cache_deduplication_invalidation_and_failure(self):
        saved = server.save_profile(self.sid, self.profile)
        queries = ['privacy papers', 'network analysis', 'Python projects']
        def search(query, limit):
            return {'response': {'results': [
                {'url': 'https://example.org/shared#section', 'title': 'Shared'},
                {'url': 'https://example.org/' + query.replace(' ', '-'), 'title': query}]}}
        with patch('fetch_interests.build_discovery_queries', return_value=queries) as generate, patch('fetch_interests.search_interests', side_effect=search) as fetch:
            result, path = discovery.fetch_for_profile(server.profile_path(self.sid), 10)
            self.assertEqual(len(result['response']['results']), 4)
            self.assertEqual(fetch.call_count, 3)
            self.assertIn('Python network analysis', generate.call_args.args[0]['cv']['text'])
            discovery.fetch_for_profile(server.profile_path(self.sid), 10)
            self.assertEqual(generate.call_count, 1)
            update = {k: v for k, v in self.profile.items() if k != 'cv'}
            update['profession'] = 'Engineer'
            server.save_profile(self.sid, update)
            discovery.fetch_for_profile(server.profile_path(self.sid), 10)
            self.assertEqual(generate.call_count, 2)
            previous = path.read_text()
            fetch.side_effect = RuntimeError('Rate limited')
            with self.assertRaises(RuntimeError):
                discovery.fetch_for_profile(server.profile_path(self.sid), 10)
            self.assertEqual(path.read_text(), previous)

    def test_discovery_endpoint_hides_stale_cache(self):
        profile = server.save_profile(self.sid, self.profile)
        cache = self.root / 'data/discovery' / f'{self.sid}.json'
        cache.parent.mkdir(parents=True)
        cached = {'profile_fingerprint': discovery.profile_fingerprint(profile),
                  'response': {'results': []}}
        cache.write_text(json.dumps(cached))
        def get_cache():
            handler = server.Handler.__new__(server.Handler)
            handler.path = '/api/discovery'
            handler.headers = {'Host': '127.0.0.1:8000',
                               'Cookie': f'chat_session={self.sid}'}
            output = []
            handler.send = lambda status, data: output.append((status, data))
            handler.do_GET()
            return output[0]
        self.assertEqual(get_cache(), (200, cached))
        profile['profession'] = 'Different profession'
        server.profile_path(self.sid).write_text(json.dumps(profile))
        self.assertEqual(get_cache(), (200, None))

    def test_legacy_cv_extracted_and_scanned_warning(self):
        saved = server.save_profile(self.sid, self.profile)
        del saved['cv']['text']
        del saved['cv']['text_status']
        path = server.profile_path(self.sid)
        path.write_text(json.dumps(saved))
        with patch('fetch_interests.build_discovery_queries', return_value=['one topic', 'two topics', 'three topics']), patch('fetch_interests.search_interests', return_value={'response': {'results': []}}):
            discovery.fetch_for_profile(path)
            self.assertIn('Python network analysis', json.loads(path.read_text())['cv']['text'])
            update = dict(self.profile)
            update['cv'] = {'filename': 'scan.pdf', 'data': base64.b64encode(pdf_bytes()).decode()}
            server.save_profile(self.sid, update)
            result, _ = discovery.fetch_for_profile(path)
            self.assertIn('no selectable text', result['warnings'][0])


if __name__ == '__main__':
    unittest.main()
