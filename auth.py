"""Local accounts and revocable, hashed login sessions."""
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager

SESSION_AGE = 30 * 24 * 60 * 60
ITERATIONS = 600_000


@contextmanager
def database(root):
    path = root / 'data/auth.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                salt BLOB NOT NULL, password_hash BLOB NOT NULL, created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
        ''')
        with conn:
            yield conn
    finally:
        conn.close()


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)


def register(root, name, email, password):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
        raise ValueError('Enter your name (up to 200 characters).')
    if not isinstance(email, str) or len(email) > 254 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email.strip()):
        raise ValueError('Enter a valid email address.')
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise ValueError('Use a password with 8–128 characters.')
    user = {'id': secrets.token_urlsafe(16), 'name': name.strip(), 'email': email.strip().lower()}
    salt = secrets.token_bytes(16)
    try:
        digest = password_hash(password, salt)
        with database(root) as conn:
            conn.execute('INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?)',
                         (user['id'], user['name'], user['email'], salt, digest, int(time.time())))
    except UnicodeEncodeError:
        raise ValueError('Password must contain valid text.') from None
    except sqlite3.IntegrityError:
        raise ValueError('An account with that email already exists.') from None
    return user


def login(root, email, password):
    if not isinstance(email, str) or not isinstance(password, str) or not 1 <= len(password) <= 128:
        raise ValueError('Email or password is incorrect.')
    with database(root) as conn:
        row = conn.execute('SELECT id, name, email, salt, password_hash FROM accounts WHERE email=?',
                           (email.strip().lower(),)).fetchone()
    try:
        digest = password_hash(password, row[3] if row else b'\0' * 16)
    except UnicodeEncodeError:
        raise ValueError('Email or password is incorrect.') from None
    if not hmac.compare_digest(digest, row[4] if row else b'\0' * 32) or not row:
        raise ValueError('Email or password is incorrect.')
    return dict(zip(('id', 'name', 'email'), row[:3]))


def new_session(root, account_id):
    token = secrets.token_urlsafe(32)
    with database(root) as conn:
        conn.execute('DELETE FROM sessions WHERE expires_at<=?', (int(time.time()),))
        conn.execute('INSERT INTO sessions VALUES (?, ?, ?)',
                     (hashlib.sha256(token.encode()).hexdigest(), account_id, int(time.time()) + SESSION_AGE))
    return token


def user_for_token(root, token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None
    with database(root) as conn:
        row = conn.execute('''SELECT a.id, a.name, a.email FROM accounts a JOIN sessions s ON a.id=s.account_id
            WHERE s.token_hash=? AND s.expires_at>?''',
                           (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
    return dict(zip(('id', 'name', 'email'), row)) if row else None


def logout(root, token):
    with database(root) as conn:
        conn.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))


def accounts(root):
    """Directory-safe fields only; never return emails, hashes, or session tokens."""
    with database(root) as conn:
        return [{'id': row[0], 'name': row[1]} for row in conn.execute('SELECT id, name FROM accounts ORDER BY created_at, id')]
