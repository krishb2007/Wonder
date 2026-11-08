"""Start the browser chat with: python server.py"""
import json
import secrets
import base64
import re
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from gemini_chat import (GeminiConfigurationError, prepare_source, reply,
                        LEARNING_INTRO_PROMPT, LEARNING_END_PROMPT, generate_practice)
from fetch_interests import extract_cv_text, fetch_for_profile, profile_fingerprint, fetch_learning_source
from connect_backend import snapshot as connect_snapshot, perform as connect_action

ROOT = Path(__file__).resolve().parent
# Each browser session has a list of user/model message dictionaries.
conversations = {}


def profile_path(sid):
    return ROOT / 'data' / 'profiles' / f'{sid}.json'


def load_profile(sid):
    path = profile_path(sid)
    return json.loads(path.read_text()) if path.exists() else {
        'name': '', 'interests': '', 'profession': '', 'cv': None}


def save_profile(sid, body):
    if not isinstance(body, dict):
        raise ValueError('Invalid profile.')
    profile = load_profile(sid)
    for field, limit in [('name', 200), ('interests', 5000), ('profession', 300)]:
        value = body.get(field, '')
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f'Invalid {field} (maximum {limit} characters).')
        profile[field] = value.strip()
    if not profile['name']:
        raise ValueError('Please enter your name.')
    cv = body.get('cv')
    new_path = None
    old_cv = profile.get('cv')
    if cv is not None:
        if not isinstance(cv, dict) or not isinstance(cv.get('filename'), str) or not isinstance(cv.get('data'), str):
            raise ValueError('Choose a PDF file.')
        try:
            pdf = base64.b64decode(cv['data'], validate=True)
        except ValueError:
            raise ValueError('Invalid PDF upload.')
        if not cv['filename'].lower().endswith('.pdf') or not pdf.startswith(b'%PDF-'):
            raise ValueError('Your CV must be a PDF file.')
        if not 0 < len(pdf) <= 20 * 1024 * 1024:
            raise ValueError('The PDF must be 20 MB or smaller.')
        extracted = extract_cv_text(pdf)
        directory = ROOT / 'data' / 'cvs'
        directory.mkdir(parents=True, exist_ok=True)
        new_path = directory / f'{secrets.token_hex(16)}.pdf'
        new_path.write_bytes(pdf)
        profile['cv'] = {'filename': cv['filename'].replace('\\', '/').split('/')[-1][:200],
                         'stored_file': new_path.name, 'size_bytes': len(pdf), **extracted}
    profile['updated_at'] = datetime.now(timezone.utc).isoformat()
    path = profile_path(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    try:
        temporary.write_text(json.dumps(profile, indent=2, ensure_ascii=False))
        temporary.replace(path)
    except OSError:
        if new_path:
            new_path.unlink(missing_ok=True)
        raise
    if new_path and old_cv:
        (ROOT / 'data' / 'cvs' / old_cv['stored_file']).unlink(missing_ok=True)
    return profile


class Handler(BaseHTTPRequestHandler):
    def session(self):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
        except Exception:
            pass
        sid = cookies['chat_session'].value if 'chat_session' in cookies else None
        if not sid or not re.fullmatch(r'[A-Za-z0-9_-]{43}', sid):
            sid = secrets.token_urlsafe(32)
        if sid not in conversations:
            conversations[sid] = {'history': [], 'source': None, 'ended': False, 'practice': []}
        self.sid = sid
        return conversations[sid]

    def send(self, status, data, content_type='application/json'):
        payload = json.dumps(data).encode() if content_type == 'application/json' else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        if hasattr(self, 'sid'):
            self.send_header('Set-Cookie', f'chat_session={self.sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.headers.get('Host') != '127.0.0.1:8000':
            self.send(403, {'error': 'Open http://127.0.0.1:8000.'})
            return
        session = self.session()
        if self.path in ('/', '/interface', '/interface.html'):
            self.send(200, (ROOT/'static/interface.html').read_bytes(), 'text/html; charset=utf-8')
        elif self.path in ('/static/base.css', '/static/library.css', '/static/app.js', '/static/library.js'):
            content_type = 'text/css; charset=utf-8' if self.path.endswith('.css') else 'text/javascript; charset=utf-8'
            self.send(200, (ROOT / self.path.lstrip('/')).read_bytes(), content_type)
        elif self.path == '/chat':
            self.send(200, (ROOT/'static/index.html').read_bytes(), 'text/html; charset=utf-8')
        elif self.path == '/settings':
            self.send_response(302)
            self.send_header('Location', '/#/settings')
            self.end_headers()
        elif self.path == '/api/discovery':
            path = ROOT / 'data/discovery' / f'{self.sid}.json'
            profile = load_profile(self.sid)
            cached = json.loads(path.read_text()) if path.exists() else None
            if cached and cached.get('profile_fingerprint') != profile_fingerprint(profile):
                cached = None
            self.send(200, cached)
        elif self.path == '/api/profile':
            self.send(200, load_profile(self.sid))
        elif self.path == '/api/profile/cv':
            cv = load_profile(self.sid).get('cv')
            if not cv:
                self.send(404, {'error': 'No CV uploaded.'})
            else:
                self.send(200, (ROOT/'data/cvs'/cv['stored_file']).read_bytes(), 'application/pdf')
        elif self.path == '/api/history':
            self.send(200, session['history'])
        elif self.path == '/api/learning':
            self.send(200, session)
        elif self.path == '/api/connect':
            try:
                self.send(200, connect_snapshot(ROOT, self.sid))
            except (OSError, ValueError):
                self.send(500, {'error': 'Could not load Connect data.'})
        elif self.path == '/api/source':
            self.send(200, session['source'])
        else:
            self.send(404, {'error': 'Not found.'})

    def do_POST(self):
        if self.headers.get('Host') != '127.0.0.1:8000' or self.headers.get('Origin') != 'http://127.0.0.1:8000':
            self.send(403, {'error': 'Open http://127.0.0.1:8000.'})
            return
        session = self.session()
        history = session['history']
        if self.path == '/api/discovery':
            try:
                result, _ = fetch_for_profile(profile_path(self.sid), max_results=10)
                self.send(200, result)
            except (ValueError, RuntimeError, OSError) as exc:
                self.send(400, {'error': str(exc) if not isinstance(exc, OSError) else 'Save your profile and interests in Settings first.'})
            return
        if self.path == '/api/reset':
            history.clear()
            session['ended'] = False
            self.send(200, {'ok': True})
            return
        if self.path not in ('/api/chat', '/api/source', '/api/profile', '/api/learn/start', '/api/learn/message', '/api/practice/check', '/api/connect'):
            self.send(404, {'error': 'Not found.'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            limit = 28_100_000 if self.path == '/api/profile' else 1_000_000
            if not 0 < length <= limit:
                raise ValueError()
            body = json.loads(self.rfile.read(length))
            if self.path == '/api/connect':
                try:
                    self.send(200, connect_action(ROOT, self.sid, body, load_profile(self.sid)))
                except ValueError as exc:
                    self.send(400, {'error': str(exc)})
                except OSError:
                    self.send(500, {'error': 'Could not save Connect changes. Please retry.'})
                return
            if self.path.startswith('/api/learn/') or self.path == '/api/practice/check':
                if not isinstance(body, dict):
                    raise ValueError()
                try:
                    self.learning_action(session, body)
                except GeminiConfigurationError as exc:
                    self.send(503, {'error': str(exc)})
                except ValueError:
                    self.send(400, {'error': 'Invalid learning request or practice response. Please retry.'})
                except Exception:
                    self.send(502, {'error': 'Could not complete this learning action. Check your API connection, model, and quota, then retry.'})
                return
            if self.path == '/api/profile':
                try:
                    profile = save_profile(self.sid, body)
                except ValueError as exc:
                    self.send(400, {'error': str(exc)})
                    return
                except OSError:
                    self.send(500, {'error': 'Could not save your profile. Please try again.'})
                    return
                self.send(200, profile)
                return
            if self.path == '/api/source':
                source = prepare_source(body)
                if source != session['source']:
                    session['source'] = source
                    history.clear()
                    session['ended'] = False
                self.send(200, {'ok': True, 'source': source})
                return
            prompt = body.get('message') if isinstance(body, dict) else None
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError()
        except (ValueError, TypeError):
            self.send(400, {'error': 'Pass source content or a nonempty message (maximum request size: 1 MB).'})
            return
        try:
            answer = reply(history, prompt.strip(), source=session['source'])
            self.send(200, {'answer': answer})
        except GeminiConfigurationError as exc:
            self.send(503, {'error': str(exc)})
        except Exception:
            self.send(502, {'error': 'Gemini could not respond. Check your connection, model availability, and quota, then retry. Your message was not added to memory.'})

    def learning_action(self, session, body):
        if self.path == '/api/learn/start':
            url, title, excerpt = (body.get(k, '') for k in ('url', 'title', 'excerpt'))
            if not all(isinstance(v, str) for v in (url, title, excerpt)):
                raise ValueError()
            if session['source'] and session['source']['url'] == url and session['history'] and not body.get('restart'):
                self.send(200, session)
                return
            source = (session['source'] if session['source'] and session['source']['url'] == url
                      else fetch_learning_source(url, title, excerpt))
            history = []
            reply(history, LEARNING_INTRO_PROMPT, source)
            history[0]['text'] = 'Help me learn about this source.'
            session.update(source=source, history=history, ended=False)
            self.send(200, session)
            return
        if self.path == '/api/practice/check':
            if type(body.get('completed')) is not bool:
                raise ValueError()
            for plan in session['practice']:
                if plan['id'] == body.get('plan_id'):
                    for task in plan['tasks']:
                        if task['id'] == body.get('task_id'):
                            task['completed'] = body['completed']
                            self.send(200, session)
                            return
            raise ValueError()
        if not session['source']:
            self.send(400, {'error': 'Choose Learn on a discovery card first.'})
            return
        message = body.get('message')
        if not isinstance(message, str) or not message.strip():
            raise ValueError()
        command = message.strip().lower()
        if command == '/practice':
            plan = generate_practice(session['source'], session['history'])
            plan.update(id=secrets.token_urlsafe(12), source_title=session['source']['title'],
                        source_url=session['source']['url'])
            for index, task in enumerate(plan['tasks']):
                task.update(id=str(index), completed=False)
            session['practice'].append(plan)
            session['history'].extend([{'role': 'user', 'text': '/practice'},
                {'role': 'model', 'text': 'Your practice checklist is ready: ' + plan['title'] + '. Open Practice to work through it. Return here to ask questions or type /end when ready.'}])
            self.send(200, {**session, 'navigate': 'practice'})
            return
        if session['ended']:
            self.send(409, {'error': 'This lesson has ended. Generate practice or restart the lesson to ask more questions.'})
            return
        if command.startswith('/') and command != '/end':
            self.send(400, {'error': 'Use /end to finish, /practice for a checklist, or type a question.'})
            return
        reply(session['history'], LEARNING_END_PROMPT if command == '/end' else message.strip(), session['source'])
        if command == '/end':
            session['history'][-2]['text'] = '/end'
            session['ended'] = True
        self.send(200, session)


if __name__ == '__main__':
    print('Open http://127.0.0.1:8000 in your browser.', flush=True)
    try:
        HTTPServer(('127.0.0.1', 8000), Handler).serve_forever()
    except KeyboardInterrupt:
        print('\nChat stopped. In-memory history cleared.')


