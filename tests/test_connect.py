import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import connect_backend as connect
import server


class ConnectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sid = 'd' * 43
        self.other = 'e' * 43
        self.profile = {'name': 'Test User', 'profession': 'Researcher', 'interests': 'Climate',
                        'cv': {'text': 'PRIVATE CV'}}

    def tearDown(self):
        self.tmp.cleanup()

    def act(self, action, **kwargs):
        return connect.perform(self.root, self.sid, {'action': action, **kwargs}, self.profile)

    def test_seed_directory_and_real_reply_counts(self):
        data = connect.snapshot(self.root, self.sid)
        self.assertEqual(len(data['people']), 9)
        self.assertTrue(all(p['sample'] for p in data['people']))
        for discussion in data['discussions']:
            self.assertEqual(discussion['replies'], len(discussion['comments']))
        self.assertEqual(data['directory_mode'], 'sample')

    def test_requests_follows_and_isolation(self):
        self.act('connect', target='maya')
        self.act('connect', target='maya')
        self.assertEqual(connect.load_state(self.root, self.sid)['connections'], ['maya'])
        self.act('follow', target='noah')
        self.assertIn('noah', connect.load_state(self.root, self.sid)['following'])
        self.assertEqual(connect.load_state(self.root, self.other)['connections'], [])
        self.act('follow', target='noah')
        self.assertEqual(connect.load_state(self.root, self.sid)['following'], [])

    def test_block_unblock_and_report(self):
        self.act('follow', target='noah')
        self.act('connect', target='noah')
        blocked = self.act('block', target='noah')
        self.assertNotIn('noah', [p['id'] for p in blocked['people']])
        self.assertNotIn('d4', [d['id'] for d in blocked['discussions']])
        self.assertNotIn('noah', blocked['state']['following'])
        self.assertNotIn('noah', blocked['state']['connections'])
        with self.assertRaises(ValueError):
            self.act('connect', target='noah')
        self.assertIn('noah', [p['id'] for p in self.act('unblock', target='noah')['people']])
        report = self.act('report', target='maya', reason='Spam')
        self.assertEqual(report['state']['reports'][0]['reason'], 'Spam')

    def test_community_shared_without_profile_or_cookie_disclosure(self):
        result = self.act('discussion', title='A question', body='How do we evaluate this?', topic='Climate')
        post = result['discussions'][0]
        self.assertEqual(post['author'], 'Test User')
        self.assertFalse(post['sample'])
        self.assertNotIn(self.sid, json.dumps(result))
        self.assertNotIn('PRIVATE CV', json.dumps(result))
        self.assertEqual(connect.snapshot(self.root, self.other)['discussions'][0]['id'], post['id'])
        connect.perform(self.root, self.other, {'action': 'comment', 'target': post['id'], 'text': 'Useful question'}, {'name': 'Second User'})
        loaded = connect.snapshot(self.root, self.sid)['discussions'][0]
        self.assertEqual(loaded['replies'], 1)
        self.assertEqual(loaded['comments'][0]['author'], 'Second User')
        connect.perform(self.root, self.other, {'action': 'block', 'target': post['author_id']}, {})
        self.assertNotIn(post['id'], [d['id'] for d in connect.snapshot(self.root, self.other)['discussions']])
        with self.assertRaises(ValueError):
            connect.perform(self.root, self.other, {'action': 'comment', 'target': post['id'], 'text': 'Hidden'}, {'name': 'Second User'})

    def test_validation_and_preferences(self):
        for body in [None, {'action': 'connect', 'target': 'missing'},
                     {'action': 'comment', 'target': 'd1', 'text': ''},
                     {'action': 'discussion', 'title': 'A', 'body': 'B', 'topic': 'unknown'},
                     {'action': 'privacy', 'searchable': 'yes', 'requests': 'everyone'}]:
            with self.assertRaises(ValueError):
                connect.perform(self.root, self.sid, body, self.profile)
        with self.assertRaises(ValueError):
            connect.perform(self.root, self.sid, {'action': 'comment', 'target': 'd1', 'text': 'Reply'}, {})
        result = self.act('privacy', searchable=False, requests='none')
        self.assertEqual(result['state']['privacy'], {'searchable': False, 'requests': 'none'})
        self.act('join', topic='Climate')
        self.assertEqual(connect.load_state(self.root, self.sid)['joined'], ['Climate'])
        self.act('join', topic='Climate')
        self.assertEqual(connect.load_state(self.root, self.sid)['joined'], [])

    def test_http_routes_use_browser_identity_and_origin_check(self):
        def request(method, body=None, origin='http://127.0.0.1:8000'):
            h = server.Handler.__new__(server.Handler)
            payload = json.dumps(body or {}).encode()
            h.headers = {'Host': '127.0.0.1:8000', 'Origin': origin,
                         'Cookie': f'chat_session={self.sid}', 'Content-Length': str(len(payload))}
            h.path = '/api/connect'
            h.rfile = io.BytesIO(payload)
            result = []
            h.send = lambda status, data: result.append((status, data))
            getattr(h, 'do_' + method)()
            return result[0]
        with patch.object(server, 'ROOT', self.root):
            self.assertEqual(request('GET')[0], 200)
            result = request('POST', {'action': 'connect', 'target': 'maya'})
            self.assertEqual(result[0], 200)
            self.assertEqual(result[1]['state']['connections'], ['maya'])
            self.assertEqual(request('POST', {'action': 'connect', 'target': 'samir'}, origin='http://evil.example')[0], 403)
            self.assertEqual(request('POST', {'action': 'connect', 'target': 'missing'})[0], 400)


if __name__ == '__main__':
    unittest.main()
