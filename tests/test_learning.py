import copy
import io
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from urllib.error import URLError

import server
import gemini_chat
import fetch_interests

SOURCE = {'content_id': 'https://example.org/gamification',
          'url': 'https://example.org/gamification', 'title': 'Gamification',
          'content': 'Practice tasks encourage skill development.', 'warning': ''}


def plan_data():
    return {'title': 'Practice gamification', 'goal': 'Apply mastery-based incentives.',
            'tasks': [{'title': f'Task {i}', 'learn': 'Understand incentives',
                       'steps': ['Explain an idea', 'Apply it to a scenario'],
                       'success_criteria': 'Justify how the incentive supports learning.',
                       'estimated_minutes': 10} for i in range(4)]}


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.sid = 'c' * 43
        server.conversations[self.sid] = {'source': None, 'history': [], 'ended': False, 'practice': []}
        self.session = server.conversations[self.sid]
        self.env = patch.dict(os.environ, {'GEMINI_API_KEY': 'test', 'GEMINI_MODEL': 'test', 'KEENABLE_API_KEY': 'test'})
        self.env.start()
        self.client_patch = patch('gemini_chat.genai.Client')
        factory = self.client_patch.start()
        self.model = factory.return_value.__enter__.return_value.models
        self.model.generate_content.return_value = SimpleNamespace(text='Intro and guidance: /end or /practice.')

    def tearDown(self):
        self.env.stop()
        self.client_patch.stop()
        server.conversations.pop(self.sid, None)

    def request(self, path, body=None, method='POST'):
        handler = server.Handler.__new__(server.Handler)
        handler.path = path
        payload = json.dumps(body or {}).encode()
        handler.headers = {'Host': '127.0.0.1:8000', 'Origin': 'http://127.0.0.1:8000',
                           'Cookie': f'chat_session={self.sid}', 'Content-Length': str(len(payload))}
        handler.rfile = io.BytesIO(payload)
        result = []
        handler.send = lambda status, data, *args: result.append((status, copy.deepcopy(data)))
        getattr(handler, 'do_' + method)()
        return result[0]

    def start(self):
        with patch('server.fetch_learning_source', return_value=SOURCE.copy()):
            status, data = self.request('/api/learn/start', {'url': SOURCE['url'], 'title': SOURCE['title']})
        self.assertEqual(status, 200)
        return data

    def test_start_followups_end_and_restart(self):
        self.start()
        self.assertEqual(len(self.session['history']), 2)
        self.request('/api/learn/message', {'message': 'Give me an example'})
        sent = self.model.generate_content.call_args.kwargs['contents']
        self.assertIn('Practice tasks encourage', sent[0].parts[0].text)
        self.assertEqual(sent[-1].parts[0].text, 'Give me an example')
        self.assertEqual(len(self.session['history']), 4)
        self.request('/api/learn/message', {'message': '/end'})
        self.assertTrue(self.session['ended'])
        self.assertEqual(self.session['history'][-2]['text'], '/end')
        self.assertEqual(self.request('/api/learn/message', {'message': 'More?'})[0], 409)
        with patch('server.fetch_learning_source') as fetch:
            self.request('/api/learn/start', {'url': SOURCE['url'], 'restart': True})
            fetch.assert_not_called()
        self.assertFalse(self.session['ended'])
        self.assertEqual(len(self.session['history']), 2)

    def test_practice_navigation_progress_and_after_end(self):
        self.start()
        self.request('/api/learn/message', {'message': '/end'})
        self.model.generate_content.return_value = SimpleNamespace(text=json.dumps(plan_data()))
        status, data = self.request('/api/learn/message', {'message': '/practice'})
        self.assertEqual(status, 200)
        self.assertEqual(data['navigate'], 'practice')
        plan = data['practice'][0]
        self.assertEqual(len(plan['tasks']), 4)
        self.assertFalse(plan['tasks'][0]['completed'])
        self.assertEqual(self.request('/api/practice/check', {'plan_id': plan['id'],
            'task_id': '0', 'completed': True})[0], 200)
        self.assertTrue(self.session['practice'][0]['tasks'][0]['completed'])
        self.assertEqual(self.request('/api/learning', method='GET')[1]['practice'], self.session['practice'])
        self.assertEqual(self.request('/api/practice/check', {'plan_id': 'unknown',
            'task_id': '0', 'completed': True})[0], 400)

    def test_failed_requests_do_not_change_history_or_practice(self):
        self.start()
        before = copy.deepcopy(self.session)
        self.model.generate_content.side_effect = RuntimeError('offline')
        self.assertEqual(self.request('/api/learn/message', {'message': '/end'})[0], 502)
        self.assertEqual(self.session, before)
        self.assertEqual(self.request('/api/learn/message', {'message': '/practice'})[0], 502)
        self.assertEqual(self.session, before)
        self.model.generate_content.side_effect = None
        self.model.generate_content.return_value = SimpleNamespace(text='{"tasks": []}')
        self.assertEqual(self.request('/api/learn/message', {'message': '/practice'})[0], 400)
        self.assertEqual(self.session, before)

    def test_switch_source_and_no_source_guard(self):
        self.assertEqual(self.request('/api/learn/message', {'message': '/practice'})[0], 400)
        self.start()
        self.request('/api/learn/message', {'message': 'Earlier question'})
        other = {**SOURCE, 'url': 'https://example.org/new', 'title': 'New source'}
        with patch('server.fetch_learning_source', return_value=other):
            self.request('/api/learn/start', {'url': other['url']})
        self.assertEqual(len(self.session['history']), 2)
        self.assertEqual(self.session['source']['title'], 'New source')
        self.assertEqual(self.request('/api/learn/message', {'message': '/unknown'})[0], 400)

    def test_source_fetch_and_explicit_excerpt_fallback(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"markdown":"Actual full page text"}'
        with patch('fetch_interests.urlopen', return_value=response) as fetch:
            source = fetch_interests.fetch_learning_source(SOURCE['url'], 'Title', 'Snippet')
            self.assertEqual(source['content'], 'Actual full page text')
            self.assertIn('/v1/fetch?', fetch.call_args.args[0].full_url)
            self.assertIn('live=true', fetch.call_args.args[0].full_url)
        with patch('fetch_interests.urlopen', side_effect=URLError('offline')):
            fallback = fetch_interests.fetch_learning_source(SOURCE['url'], 'Title', 'Snippet')
            self.assertIn('only the search excerpt', fallback['warning'])
            self.assertIn('Snippet', fallback['content'])
            with self.assertRaises(RuntimeError):
                fetch_interests.fetch_learning_source(SOURCE['url'])
        with self.assertRaises(ValueError):
            fetch_interests.fetch_learning_source('file:///private/file')


if __name__ == '__main__':
    unittest.main()
