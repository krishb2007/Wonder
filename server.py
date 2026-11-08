"""Start the browser chat with: python server.py"""
import json
import secrets
import base64
import sqlite3
import time
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from gemini_chat import (GeminiConfigurationError, reply,
                        LEARNING_INTRO_PROMPT, LEARNING_END_PROMPT, generate_practice)
from fetch_interests import extract_cv_text, fetch_for_profile, profile_fingerprint, fetch_learning_source
from connect_backend import snapshot as connect_snapshot, perform as connect_action
import auth

ROOT = Path(__file__).resolve().parent
# Each browser session has a list of user/model message dictionaries.
conversations = {}
auth_attempts = {}


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
    def auth_token(self):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
        except Exception:
            return None
        return cookies['wonder_session'].value if 'wonder_session' in cookies else None

    def require_user(self):
        self.user = auth.user_for_token(ROOT, self.auth_token())
        return self.user

    def session(self):
        self.sid = self.user['id']
        if self.sid not in conversations:
            conversations[self.sid] = {'history': [], 'source': None, 'ended': False, 'practice': []}
        return conversations[self.sid]

    def redirect(self, location):
        self.send_response(302)
        self.send_header('Location', location)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()

    def send(self, status, data, content_type='application/json', auth_cookie=None):
        payload = json.dumps(data).encode() if content_type == 'application/json' else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        if auth_cookie is not None:
            age = auth.SESSION_AGE if auth_cookie else 0
            self.send_header('Set-Cookie', f'wonder_session={auth_cookie}; HttpOnly; SameSite=Strict; Path=/; Max-Age={age}')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.headers.get('Host') != '127.0.0.1:8000':
            self.send(403, {'error': 'Open http://127.0.0.1:8000.'})
            return
        try:
            user = self.require_user()
            if self.path in ('/login', '/register'):
                if user:
                    self.redirect('/')
                else:
                    self.send(200, (ROOT / 'static/login.html').read_bytes(), 'text/html; charset=utf-8')
                return
            if self.path == '/api/auth/me':
                self.send(200, {'authenticated': bool(user), 'user': user})
                return
            if not user:
                if self.path.startswith('/api/'):
                    self.send(401, {'error': 'Please sign in first.'})
                else:
                    self.redirect('/login')
                return
            session = self.session()
            if self.path in ('/', '/interface', '/interface.html'):
                self.send(200, (ROOT / 'static/wonder.html').read_bytes(), 'text/html; charset=utf-8')
            elif self.path == '/settings':
                self.send_response(302)
                self.send_header('Location', '/#/settings')
                self.end_headers()
            elif self.path == '/api/discovery':
                path = ROOT / 'data/discovery' / f'{self.sid}.json'
                cached = json.loads(path.read_text()) if path.exists() else None
                if cached and cached.get('profile_fingerprint') != profile_fingerprint(load_profile(self.sid)):
                    cached = None
                self.send(200, cached)
            elif self.path == '/api/profile':
                self.send(200, load_profile(self.sid))
            elif self.path == '/api/profile/cv':
                cv = load_profile(self.sid).get('cv')
                if cv:
                    self.send(200, (ROOT / 'data/cvs' / cv['stored_file']).read_bytes(), 'application/pdf')
                else:
                    self.send(404, {'error': 'No CV uploaded.'})
            elif self.path == '/api/learning':
                self.send(200, session)
            elif self.path == '/api/connect':
                self.send(200, connect_snapshot(ROOT, self.sid))
            else:
                self.send(404, {'error': 'Not found.'})
        except (OSError, ValueError, sqlite3.Error):
            self.send(500, {'error': 'Could not load saved data. Please try again.'})

    def read_json(self):
        limit = (16_384 if self.path.startswith('/api/auth/') else
                 28_100_000 if self.path == '/api/profile' else 1_000_000)
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= limit:
            raise ValueError('Request is empty or too large.')
        body = json.loads(self.rfile.read(length))
        if not isinstance(body, dict):
            raise ValueError('Expected a JSON object.')
        return body

    def do_POST(self):
        if self.headers.get('Host') != '127.0.0.1:8000' or self.headers.get('Origin') != 'http://127.0.0.1:8000':
            self.send(403, {'error': 'Open http://127.0.0.1:8000.'})
            return
        if self.path in ('/api/auth/register', '/api/auth/login', '/api/auth/logout'):
            self.auth_action()
            return
        try:
            if not self.require_user():
                self.send(401, {'error': 'Please sign in first.'})
                return
        except sqlite3.Error:
            self.send(500, {'error': 'Could not check your sign-in. Please retry.'})
            return
        routes = {'/api/discovery', '/api/profile', '/api/connect',
                  '/api/learn/start', '/api/learn/message', '/api/practice/check'}
        if self.path not in routes:
            self.send(404, {'error': 'Not found.'})
            return
        session = self.session()
        try:
            body = self.read_json()
            if self.path == '/api/discovery':
                if not profile_path(self.sid).exists():
                    raise ValueError('Save your profile in Settings first.')
                result, _ = fetch_for_profile(profile_path(self.sid), max_results=10)
                self.send(200, result)
            elif self.path == '/api/profile':
                self.send(200, save_profile(self.sid, body))
            elif self.path == '/api/connect':
                self.send(200, connect_action(ROOT, self.sid, body, load_profile(self.sid)))
            else:
                self.learning_action(session, body)
        except GeminiConfigurationError as exc:
            self.send(503, {'error': str(exc)})
        except (ValueError, TypeError) as exc:
            message = ('Invalid learning request or practice response. Please retry.'
                       if self.path.startswith('/api/learn/') or self.path == '/api/practice/check'
                       else str(exc))
            self.send(400, {'error': message})
        except OSError:
            self.send(500, {'error': 'Could not read or save data. Please try again.'})
        except RuntimeError as exc:
            message = (str(exc) if self.path == '/api/discovery'
                       else 'Could not complete this action. Check your API connection, model, and quota, then retry.')
            self.send(502, {'error': message})
        except Exception:
            self.send(502, {'error': 'Could not complete this action. Check your API connection, model, and quota, then retry.'})

    def auth_action(self):
        try:
            if self.path == '/api/auth/logout':
                if not self.require_user():
                    self.send(401, {'error': 'Please sign in first.'})
                    return
                auth.logout(ROOT, self.auth_token())
                self.send(200, {'ok': True}, auth_cookie='')
                return
            address = getattr(self, 'client_address', ('local', 0))[0]
            now = time.monotonic()
            recent = [t for t in auth_attempts.get(address, []) if now - t < 60]
            auth_attempts[address] = recent
            if len(recent) >= 10:
                self.send(429, {'error': 'Too many sign-in attempts. Wait one minute and retry.'})
                return
            recent.append(now)
            body = self.read_json()
            if self.path == '/api/auth/register':
                user = auth.register(ROOT, body.get('name'), body.get('email'), body.get('password'))
                try:
                    save_profile(user['id'], {'name': user['name']})
                    token = auth.new_session(ROOT, user['id'])
                except Exception:
                    with auth.database(ROOT) as conn:
                        conn.execute('DELETE FROM accounts WHERE id=?', (user['id'],))
                    profile_path(user['id']).unlink(missing_ok=True)
                    raise
            else:
                user = auth.login(ROOT, body.get('email'), body.get('password'))
                token = auth.new_session(ROOT, user['id'])
            auth_attempts.pop(address, None)
            self.send(200, {'user': user}, auth_cookie=token)
        except ValueError as exc:
            self.send(401 if self.path == '/api/auth/login' else 400, {'error': str(exc)})
        except (OSError, sqlite3.Error):
            self.send(500, {'error': 'Could not sign in or create your account. Please retry.'})

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
