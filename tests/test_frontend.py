"""Frontend entry point, asset routing, and private-path regression checks."""
import unittest
from html.parser import HTMLParser
from pathlib import Path
import server


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids = []
        self.assets = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'script':
            self.assets.append(attrs.get('src'))
        if tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.assets.append(attrs.get('href'))


class FrontendTests(unittest.TestCase):
    def request(self, path):
        handler = server.Handler.__new__(server.Handler)
        handler.path = path
        handler.headers = {'Host': '127.0.0.1:8000'}
        handler.session = lambda: {}
        result = []
        handler.send = lambda *args: result.append(args)
        handler.do_GET()
        return result[0]

    def test_entry_and_all_assets_are_served(self):
        response = self.request('/')
        self.assertEqual(response[0], 200)
        doc = Document(response[1].decode('utf-8'))
        self.assertEqual(len(doc.ids), len(set(doc.ids)), 'Duplicate element IDs')
        for section in ('discover', 'connect', 'learn', 'practice', 'portfolio', 'settings'):
            self.assertIn(section + '-page', doc.ids)
        for asset in doc.assets:
            with self.subTest(asset=asset):
                status, body, mime = self.request(asset)
                self.assertEqual(status, 200)
                self.assertTrue(body)
                self.assertIn('charset=utf-8', mime)

    def test_static_allowlist_blocks_private_and_traversal_paths(self):
        for path in ('/static/../.env', '/static/../server.py', '/data/profiles/test.json'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)


if __name__ == '__main__':
    unittest.main()

