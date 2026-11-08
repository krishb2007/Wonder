"""Connect behavior adapted from connect.html; local JSON persistence."""
import copy
import json
import secrets
import hashlib
from datetime import datetime, timezone

SEED = {'people': [{'id': 'maya',
             'name': 'Dr. Maya Chen',
             'initials': 'MC',
             'role': 'Research scientist · Open Climate Lab',
             'type': 'mentor',
             'topics': ['Climate', 'Data science', 'Research'],
             'bio': 'I help early-career folks turn climate questions into useful, reproducible '
                    'research. Always happy to talk open science.',
             'availability': 'Mentoring',
             'match': 'Climate + research',
             'experience': '8 years in climate modeling and open research. I enjoy helping people find '
                           'a first project and build confidence sharing their work.',
             'interests': 'Climate data, science communication, responsible AI',
             'note': 'Mentoring availability is self-reported.'},
            {'id': 'samir',
             'name': 'Samir Patel',
             'initials': 'SP',
             'role': 'Product designer · Civic Studio',
             'type': 'mentor',
             'topics': ['Design', 'Technology', 'Civic tech'],
             'bio': 'Designer working at the intersection of public-interest tech and human-centered '
                    'design. Here to share what I’ve learned.',
             'availability': 'Open to chat',
             'match': 'Design + civic tech',
             'experience': 'I work with small teams building accessible digital public services. Happy '
                           'to offer portfolio feedback or discuss a design challenge.',
             'interests': 'Inclusive design, civic technology, prototyping',
             'note': 'Mentoring availability is self-reported.'},
            {'id': 'elena',
             'name': 'Elena Brooks',
             'initials': 'EB',
             'role': 'PhD candidate · North Coast University',
             'type': 'mentor',
             'topics': ['Health', 'Research', 'Writing'],
             'bio': 'Studying community health and translating research into clearer, more useful '
                    'public information.',
             'availability': 'Mentoring',
             'match': 'Health + research',
             'experience': 'My work looks at how local communities access health information. I can '
                           'share grad-school perspectives and research writing tips.',
             'interests': 'Public health, community research, science writing',
             'note': 'Mentoring availability is self-reported.'},
            {'id': 'noah',
             'name': 'Noah Williams',
             'initials': 'NW',
             'role': 'Learning data analyst · BrightPath',
             'type': 'peer',
             'topics': ['Data science', 'Technology', 'Learning'],
             'bio': 'Learning Python and building small projects around education data. Currently '
                    'figuring out the best way to show my work.',
             'availability': 'Building a project',
             'match': 'Both learning data science',
             'experience': 'Currently exploring data visualization and beginner-friendly Python '
                           'projects.',
             'interests': 'Python, education, visualization',
             'note': 'Profile details are self-described.'},
            {'id': 'aisha',
             'name': 'Aisha Rahman',
             'initials': 'AR',
             'role': 'Community researcher · Independent',
             'type': 'peer',
             'topics': ['Climate', 'Research', 'Community'],
             'bio': 'Working on a neighborhood heat-mapping project and looking to swap notes with '
                    'curious people.',
             'availability': 'Open to connect',
             'match': 'Both interested in climate',
             'experience': 'I’m learning qualitative research and mapping. Always glad to compare '
                           'methods and share resources.',
             'interests': 'Climate resilience, mapping, community research',
             'note': 'Profile details are self-described.'},
            {'id': 'leo',
             'name': 'Leo Martinez',
             'initials': 'LM',
             'role': 'Junior UX researcher · Loop',
             'type': 'peer',
             'topics': ['Design', 'Technology', 'Learning'],
             'bio': 'New to UX research, experienced in asking too many questions. Looking for kind '
                    'people to learn and make things with.',
             'availability': 'Learning UX',
             'match': 'Both exploring design',
             'experience': 'Practicing interview planning, synthesis, and communicating research '
                           'insights.',
             'interests': 'UX research, accessibility, learning in public',
             'note': 'Profile details are self-described.'},
            {'id': 'priya',
             'name': 'Priya Okafor',
             'initials': 'PO',
             'role': 'Science communicator · Fieldnotes',
             'type': 'mentor',
             'topics': ['Health', 'Writing', 'Research'],
             'bio': 'I make complex health and science topics easier to understand without losing the '
                    'nuance.',
             'availability': 'Open to chat',
             'match': 'Health + communication',
             'experience': 'A decade of editing and producing public-facing science communication. I’m '
                           'glad to help with clarity and storytelling.',
             'interests': 'Health research, writing, accessible communication',
             'note': 'Mentoring availability is self-reported.'},
            {'id': 'kai',
             'name': 'Kai Thompson',
             'initials': 'KT',
             'role': 'Graduate student · Lakeside Institute',
             'type': 'peer',
             'topics': ['Climate', 'Data science', 'Research'],
             'bio': 'Exploring how public datasets can help communities prepare for changing weather '
                    'patterns.',
             'availability': 'Seeking collaborators',
             'match': 'Both exploring climate data',
             'experience': 'Learning geospatial analysis and building my first public data project.',
             'interests': 'Climate adaptation, open data, GIS',
             'note': 'Profile details are self-described.'},
            {'id': 'amara',
             'name': 'Amara Singh',
             'initials': 'AS',
             'role': 'Accessibility specialist · Good Signal',
             'type': 'mentor',
             'topics': ['Design', 'Technology', 'Accessibility'],
             'bio': 'Helping teams make digital products work for more people. Available for occasional '
                    'portfolio reviews.',
             'availability': 'Portfolio reviews',
             'match': 'Design + accessibility',
             'experience': 'I support product teams with accessible design practices and usability '
                           'research.',
             'interests': 'Accessibility, inclusive research, design systems',
             'note': 'Mentoring availability is self-reported.'}],
 'discussions': [{'id': 'd1',
                  'author': 'Aisha Rahman',
                  'initials': 'AR',
                  'topic': 'Climate',
                  'time': '2 hours ago',
                  'title': 'What makes a neighborhood heat map useful to the people who live there?',
                  'body': 'I’m starting a small project mapping shade and temperature around local bus '
                          'stops. Curious what information would actually help your community—and what '
                          'I might be missing.',
                  'replies': 12,
                  'comments': ['I’d love to see bus frequency alongside shade. Waiting time changes '
                               'everything. — Noah',
                               'Consider asking a local community group what they already track before '
                               'building another map. — Maya']},
                 {'id': 'd2',
                  'author': 'Elena Brooks',
                  'initials': 'EB',
                  'topic': 'Health',
                  'time': 'Yesterday',
                  'title': 'How do you make a research summary clear without flattening the '
                           'uncertainty?',
                  'body': 'I’m editing a short explainer about community health evidence. Would love '
                          'examples of language that makes limitations feel useful rather than like '
                          'fine print.',
                  'replies': 8,
                  'comments': ["I try putting what we don't know right next to what we do know. — "
                               'Priya']},
                 {'id': 'd3',
                  'author': 'Samir Patel',
                  'initials': 'SP',
                  'topic': 'Design',
                  'time': 'Yesterday',
                  'title': 'A small accessibility check that changed how I design forms',
                  'body': 'Recently started testing forms with keyboard-only navigation early, not at '
                          'the end. What quick checks have made a lasting difference in your practice?',
                  'replies': 17,
                  'comments': ['Testing the error messages with a screen reader changed our whole '
                               'validation flow. — Amara']},
                 {'id': 'd4',
                  'author': 'Noah Williams',
                  'initials': 'NW',
                  'topic': 'Data science',
                  'time': '2 days ago',
                  'title': 'Beginner-friendly datasets for a first visualization project?',
                  'body': 'I’m looking for a dataset with a good story, manageable size, and enough '
                          'context to avoid making misleading charts. What helped you get started?',
                  'replies': 6,
                  'comments': ['Our World in Data has clear context and source links to explore. — '
                               'Kai']}]}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def load_state(root, sid):
    path = root / 'data/connect/users' / f'{sid}.json'
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return {'connections': [], 'following': [], 'blocked': [], 'reports': [],
            'joined': [], 'privacy': {'searchable': False, 'requests': 'everyone'}}


def community(root):
    path = root / 'data/connect/community.json'
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    discussions = copy.deepcopy(SEED['discussions'])
    for item in discussions:
        item['sample'] = True
        item['author_id'] = next((p['id'] for p in SEED['people'] if p['name'] == item['author']), 'sample')
        item['comments'] = [{'id': f"{item['id']}-{i}", 'text': text, 'author': 'Sample contributor',
                             'author_id': 'sample'} for i, text in enumerate(item['comments'])]
    return discussions


def public_id(sid):
    return 'local-' + hashlib.sha256(sid.encode()).hexdigest()[:24]


def snapshot(root, sid):
    state = load_state(root, sid)
    people = [{**p, 'sample': True} for p in SEED['people'] if p['id'] not in state['blocked']]
    discussions = []
    for item in community(root):
        if item['author_id'] in state['blocked']:
            continue
        item = copy.deepcopy(item)
        item['comments'] = [c for c in item['comments'] if c['author_id'] not in state['blocked']]
        item['replies'] = len(item['comments'])
        discussions.append(item)
    return {'people': people, 'discussions': discussions, 'state': state,
            'topics': sorted({topic for p in SEED['people'] for topic in p['topics']}),
            'directory_mode': 'sample', 'community_mode': 'local_server'}


def text(body, key, maximum):
    value = body.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f'{key} must contain 1 to {maximum} characters.')
    return value.strip()


def perform(root, sid, body, profile):
    if not isinstance(body, dict):
        raise ValueError('Invalid Connect action.')
    action = body.get('action')
    state = load_state(root, sid)
    person_ids = {p['id'] for p in SEED['people']}
    items = community(root)
    community_changed = False
    message = 'Saved.'
    target = body.get('target')
    if action in ('connect', 'follow', 'block', 'unblock'):
        valid_authors = person_ids | {d['author_id'] for d in items}
        if not isinstance(target, str) or target not in valid_authors:
            raise ValueError('Profile not found.')
        if action in ('connect', 'follow') and target not in person_ids:
            raise ValueError('Only sample directory profiles support this action.')
        if action in ('connect', 'follow') and target in state['blocked']:
            raise ValueError('Unblock this profile first.')
        if action == 'connect':
            if target not in state['connections']:
                state['connections'].append(target)
            message = 'Request saved locally for this sample profile. No external request was sent.'
        elif action == 'follow':
            if target in state['following']:
                state['following'].remove(target)
            else:
                state['following'].append(target)
            message = 'Follow preference saved.'
        elif action == 'block':
            if target not in state['blocked']:
                state['blocked'].append(target)
            for key in ('connections', 'following'):
                state[key] = [x for x in state[key] if x != target]
            message = 'Profile hidden from your Connect view.'
        else:
            state['blocked'] = [x for x in state['blocked'] if x != target]
            message = 'Profile unblocked.'
    elif action == 'report':
        if not isinstance(target, str) or target not in person_ids | {d['id'] for d in items}:
            raise ValueError('Profile or discussion not found.')
        reason = text(body, 'reason', 500)
        state['reports'].append({'target': target, 'reason': reason,
                                'created_at': datetime.now(timezone.utc).isoformat()})
        message = 'Report saved locally. No external moderation service is connected.'
    elif action == 'join':
        topic = text(body, 'topic', 80)
        allowed = {t for p in SEED['people'] for t in p['topics']}
        if topic not in allowed:
            raise ValueError('Choose an available topic.')
        if topic in state['joined']:
            state['joined'].remove(topic)
        else:
            state['joined'].append(topic)
        message = 'Topic membership saved.'
    elif action == 'privacy':
        if type(body.get('searchable')) is not bool or body.get('requests') not in ('everyone', 'followed', 'none'):
            raise ValueError('Invalid privacy preferences.')
        state['privacy'] = {'searchable': body['searchable'], 'requests': body['requests']}
        message = 'Preferences saved. Public profile discovery and real request delivery are not connected.'
    elif action in ('discussion', 'comment'):
        author = profile.get('name', '').strip()
        if not author:
            raise ValueError('Save your name in Settings before posting.')
        author_id = public_id(sid)
        if action == 'discussion':
            title = text(body, 'title', 120)
            content = text(body, 'body', 700)
            topic = text(body, 'topic', 80)
            if topic not in {t for p in SEED['people'] for t in p['topics']}:
                raise ValueError('Choose an available topic.')
            items.insert(0, {'id': secrets.token_urlsafe(12), 'title': title, 'body': content,
                            'topic': topic, 'author': author, 'author_id': author_id,
                            'initials': ''.join(n[0] for n in author.split()[:2]).upper(),
                            'time': datetime.now(timezone.utc).isoformat(), 'sample': False,
                            'comments': []})
            message = 'Discussion posted to this local server.'
        else:
            comment = text(body, 'text', 500)
            item = next((d for d in items if d['id'] == target), None)
            if not item or item['author_id'] in state['blocked']:
                raise ValueError('Discussion not available.')
            item['comments'].append({'id': secrets.token_urlsafe(12), 'text': comment,
                                     'author': author, 'author_id': author_id})
            message = 'Reply posted to this local server.'
        community_changed = True
    else:
        raise ValueError('Unknown Connect action.')
    if community_changed:
        write_json(root / 'data/connect/community.json', items)
    else:
        write_json(root / 'data/connect/users' / f'{sid}.json', state)
    return {**snapshot(root, sid), 'message': message}


