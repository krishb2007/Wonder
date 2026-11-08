"""Connect directory and interactions for registered Wonder accounts."""
import copy
import json
import re
import secrets
from datetime import datetime, timezone

from auth import accounts


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def load_state(root, user_id):
    path = root / 'data/connect/users' / f'{user_id}.json'
    data = json.loads(path.read_text()) if path.exists() else {}
    return {'following': data.get('following', []), 'blocked': data.get('blocked', []),
            'reports': data.get('reports', []), 'joined': data.get('joined', []),
            'privacy': {'searchable': True, 'requests': 'everyone', 'mentor': False, **data.get('privacy', {})}}


def read_list(root, filename):
    path = root / 'data/connect' / filename
    return json.loads(path.read_text()) if path.exists() else []


def community(root):
    # Legacy illustrative discussions are not part of the real account community.
    return [d for d in read_list(root, 'community.json') if not d.get('sample', False)]


def public_people(root):
    people = {}
    for account in accounts(root):
        user_id = account['id']
        path = root / 'data/profiles' / f'{user_id}.json'
        profile = json.loads(path.read_text()) if path.exists() else {}
        name = profile.get('name') or account['name']
        profession = profile.get('profession', '')
        interests = profile.get('interests', '')
        state = load_state(root, user_id)
        people[user_id] = {'id': user_id, 'name': name,
            'initials': ''.join(word[0] for word in name.split()[:2]).upper(),
            'role': profession or 'Wonder member', 'type': 'mentor' if state['privacy']['mentor'] else 'peer',
            'topics': [t.strip() for t in re.split(r'[,;\n]+', interests) if t.strip()][:12],
            'interests': interests, 'bio': interests or 'Exploring new ideas on Wonder.',
            'experience': profession or 'This member has not added a profession yet.',
            'availability': 'Open to mentoring' if state['privacy']['mentor'] else 'Peer',
            'note': 'Registered member. Profession and mentoring availability are self-reported.'}
    return people


def is_blocked(root, actor, target):
    return target in load_state(root, actor)['blocked'] or actor in load_state(root, target)['blocked']


def snapshot(root, user_id):
    state = load_state(root, user_id)
    directory = public_people(root)
    people = [p for key, p in directory.items() if key != user_id
              and load_state(root, key)['privacy']['searchable'] and not is_blocked(root, user_id, key)]
    requests = read_list(root, 'requests.json')
    relationships, incoming = {}, []
    for request in requests:
        if user_id not in (request['from'], request['to']):
            continue
        other = request['to'] if request['from'] == user_id else request['from']
        if other not in directory or is_blocked(root, user_id, other):
            continue
        if request['status'] == 'accepted':
            relationships[other] = 'connected'
        elif request['status'] == 'pending':
            if request['to'] == user_id:
                relationships[other] = 'incoming'
                incoming.append({'id': request['id'], 'from': other, 'name': directory[other]['name'],
                                 'role': directory[other]['role']})
            else:
                relationships[other] = 'pending'
    state['connections'] = [key for key, value in relationships.items() if value == 'connected']
    discussions = []
    for original in community(root):
        if original['author_id'] not in directory or is_blocked(root, user_id, original['author_id']):
            continue
        item = copy.deepcopy(original)
        item['author'] = directory[item['author_id']]['name']
        visible_comments = []
        for comment in item['comments']:
            author = comment['author_id']
            if author in directory and not is_blocked(root, user_id, author):
                visible_comments.append({**comment, 'author': directory[author]['name']})
        item['comments'] = visible_comments
        item['replies'] = len(visible_comments)
        discussions.append(item)
    topics = {t for p in people for t in p['topics']} | set(directory.get(user_id, {}).get('topics', []))
    topics |= {d['topic'] for d in discussions} | set(state['joined'])
    blocked = [{'id': key, 'name': directory[key]['name']} for key in state['blocked'] if key in directory]
    return {'people': people, 'discussions': discussions, 'state': state, 'topics': sorted(topics),
            'relationships': relationships, 'incoming_requests': incoming, 'blocked_profiles': blocked,
            'directory_mode': 'registered', 'community_mode': 'registered'}


def text(body, key, maximum):
    value = body.get(key)
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise ValueError(f'{key} must contain 1 to {maximum} characters.')
    return value.strip()


def perform(root, user_id, body, profile):
    if not isinstance(body, dict):
        raise ValueError('Invalid Connect action.')
    action = body.get('action')
    state = load_state(root, user_id)
    directory = public_people(root)
    if user_id not in directory:
        raise ValueError('Please sign in first.')
    items = community(root)
    requests = read_list(root, 'requests.json')
    target = body.get('target')
    output = None
    message = 'Saved.'
    if action in ('connect', 'follow', 'block', 'unblock'):
        if not isinstance(target, str) or target not in directory or target == user_id:
            raise ValueError('Choose another registered user.')
        if action in ('connect', 'follow') and (is_blocked(root, user_id, target) or not load_state(root, target)['privacy']['searchable']):
            raise ValueError('This profile is not available.')
        if action == 'connect':
            recipient = load_state(root, target)
            rule = recipient['privacy']['requests']
            if rule == 'none' or (rule == 'followed' and user_id not in recipient['following']):
                raise ValueError('This user is not accepting your connection request.')
            existing = next((r for r in requests if {r['from'], r['to']} == {user_id, target}
                             and r['status'] in ('pending', 'accepted')), None)
            if not existing:
                requests.append({'id': secrets.token_urlsafe(16), 'from': user_id, 'to': target,
                                 'status': 'pending', 'created_at': datetime.now(timezone.utc).isoformat()})
            output = ('requests.json', requests)
            message = 'Connection request sent. The recipient can respond in Connect.'
        elif action == 'follow':
            if target in state['following']:
                state['following'].remove(target)
            else:
                state['following'].append(target)
            message = 'Follow preference updated.'
        elif action == 'block':
            if target not in state['blocked']:
                state['blocked'].append(target)
            state['following'] = [key for key in state['following'] if key != target]
            for request in requests:
                if {request['from'], request['to']} == {user_id, target} and request['status'] in ('pending', 'accepted'):
                    request['status'] = 'blocked'
            output = ('requests.json', requests)
            message = 'User blocked. Connections and pending requests with them were removed.'
        else:
            state['blocked'] = [key for key in state['blocked'] if key != target]
            message = 'User unblocked.'
    elif action in ('accept', 'decline'):
        request = next((r for r in requests if r['id'] == target and r['to'] == user_id and r['status'] == 'pending'), None)
        if not request or is_blocked(root, user_id, request['from']):
            raise ValueError('Incoming request not found.')
        request['status'] = 'accepted' if action == 'accept' else 'declined'
        output = ('requests.json', requests)
        message = 'Connection accepted.' if action == 'accept' else 'Request declined.'
    elif action == 'report':
        if not isinstance(target, str) or (target not in directory and not any(d['id'] == target for d in items)):
            raise ValueError('Profile or discussion not found.')
        state['reports'].append({'target': target, 'reason': text(body, 'reason', 500),
                                'created_at': datetime.now(timezone.utc).isoformat()})
        message = 'Report recorded. Automated moderation is not available.'
    elif action == 'join':
        topic = text(body, 'topic', 80)
        if topic in state['joined']:
            state['joined'].remove(topic)
        else:
            state['joined'].append(topic)
        message = 'Topic membership updated.'
    elif action == 'privacy':
        if type(body.get('searchable')) is not bool or type(body.get('mentor')) is not bool or body.get('requests') not in ('everyone', 'followed', 'none'):
            raise ValueError('Invalid privacy preferences.')
        state['privacy'] = {key: body[key] for key in ('searchable', 'requests', 'mentor')}
        message = 'Profile visibility, request preferences, and mentoring availability updated.'
    elif action in ('discussion', 'comment'):
        author = directory[user_id]['name']
        if action == 'discussion':
            items.insert(0, {'id': secrets.token_urlsafe(12), 'title': text(body, 'title', 120),
                'body': text(body, 'body', 700), 'topic': text(body, 'topic', 80), 'author': author,
                'author_id': user_id, 'time': datetime.now(timezone.utc).isoformat(), 'comments': []})
            message = 'Discussion posted.'
        else:
            comment = text(body, 'text', 500)
            item = next((d for d in items if d['id'] == target), None)
            if not item or item['author_id'] not in directory or is_blocked(root, user_id, item['author_id']):
                raise ValueError('Discussion not available.')
            item['comments'].append({'id': secrets.token_urlsafe(12), 'text': comment, 'author': author, 'author_id': user_id})
            message = 'Reply posted.'
        output = ('community.json', items)
    else:
        raise ValueError('Unknown Connect action.')
    write_json(root / 'data/connect/users' / f'{user_id}.json', state)
    if output:
        write_json(root / 'data/connect' / output[0], output[1])
    return {**snapshot(root, user_id), 'message': message}
