"""Discover content using a Settings profile's CV, profession, and interests.

Usage: python fetch_interests.py [--profile data/profiles/PROFILE.json]
"""
import argparse
import json
import os
import hashlib
import io
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv
from pypdf import PdfReader
from gemini_chat import build_discovery_queries

ROOT = Path(__file__).resolve().parent


def extract_cv_text(pdf):
    """Extract a bounded amount of selectable text; no OCR is performed."""
    try:
        reader = PdfReader(io.BytesIO(pdf))
        if reader.is_encrypted and not reader.decrypt(''):
            raise ValueError('Upload a CV without a password.')
        text = ''
        for page in reader.pages:
            text += (page.extract_text() or '') + '\n'
            if len(text) >= 40000:
                return {'text': text[:40000], 'text_status': 'truncated'}
        return {'text': text.strip(), 'text_status': 'ready' if text.strip() else 'needs_ocr'}
    except ValueError:
        raise
    except Exception:
        raise ValueError('Could not read the PDF. Upload a valid, unencrypted PDF CV.') from None


def profile_fingerprint(profile):
    cv = profile.get('cv') or {}
    inputs = {'version': 2, 'profession': profile.get('profession', '').strip(),
              'interests': profile.get('interests', '').strip(),
              'cv_file': cv.get('stored_file'), 'cv_text': cv.get('text', '')}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()


def result_rows(response):
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        for key in ('results', 'sources', 'data'):
            value = response.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict) and isinstance(value.get('results'), list):
                return value['results']
    raise RuntimeError('Unexpected Keenable search response format.')


def search_interests(interests, max_results=5):
    """Send only interests to Keenable; return its search response unchanged."""
    if not isinstance(interests, str) or not interests.strip():
        raise ValueError('Add interests in Settings and save your profile first.')
    if not isinstance(max_results, int) or not 1 <= max_results <= 20:
        raise ValueError('Choose between 1 and 20 results.')
    load_dotenv(ROOT / '.env')
    key = os.getenv('KEENABLE_API_KEY')
    if not key:
        raise ValueError('Set KEENABLE_API_KEY in .env.')
    query = interests.strip()
    request = Request(
        'https://api.keenable.ai/v1/search',
        data=json.dumps({'query': query, 'max_results': max_results}).encode(),
        headers={'Content-Type': 'application/json', 'X-API-Key': key,
                 'X-Keenable-Title': 'Hackathon Learning Discovery'},
        method='POST',
    )
    try:
        with urlopen(request, timeout=60) as response:
            result = json.load(response)
    except HTTPError as exc:
        explanations = {401: 'API key is invalid.', 403: 'API access was denied.',
                        402: 'Your Keenable account is out of credits.',
                        429: 'Rate limit reached. Try again later.'}
        raise RuntimeError(explanations.get(exc.code, f'Keenable returned HTTP {exc.code}.')) from None
    except (URLError, TimeoutError):
        raise RuntimeError('Could not reach Keenable. Check your connection and retry.') from None
    except (ValueError, UnicodeError):
        raise RuntimeError('Keenable returned an invalid JSON response.') from None
    return {'query': query, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'response': result}


def fetch_for_profile(profile_path, max_results=5):
    """Read the JSON created by Settings; save results separately from the profile."""
    profile_path = Path(profile_path)
    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    if not isinstance(profile, dict):
        raise ValueError('The profile must be a JSON object.')
    if not isinstance(max_results, int) or not 1 <= max_results <= 20:
        raise ValueError('Choose between 1 and 20 results.')
    cv = profile.get('cv')
    # Extract older uploaded CVs once, without requiring the user to re-upload.
    if cv and 'text' not in cv:
        cv.update(extract_cv_text((ROOT / 'data/cvs' / cv['stored_file']).read_bytes()))
        temporary = profile_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(profile, ensure_ascii=False, indent=2))
        temporary.replace(profile_path)
    if not any((profile.get('interests', '').strip(), profile.get('profession', '').strip(),
                (cv or {}).get('text', '').strip())):
        raise ValueError('Add interests, a profession, or a text-based CV in Settings first.')
    fingerprint = profile_fingerprint(profile)
    query_path = ROOT / 'data/discovery_queries' / f'{profile_path.stem}.json'
    cached = json.loads(query_path.read_text()) if query_path.exists() else {}
    if cached.get('profile_fingerprint') == fingerprint:
        queries = cached['queries']
    else:
        queries = build_discovery_queries(profile)
        query_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = query_path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'profile_fingerprint': fingerprint, 'queries': queries}, indent=2))
        temporary.replace(query_path)
    batches = [result_rows(search_interests(query, max_results)['response']) for query in queries]
    # Interleave queries so one topic cannot fill the entire result list.
    results, seen = [], set()
    for index in range(max((len(b) for b in batches), default=0)):
        for batch in batches:
            if index >= len(batch) or not isinstance(batch[index], dict):
                continue
            row = batch[index]
            url = row.get('url') or row.get('link')
            if not isinstance(url, str):
                continue
            try:
                parts = urlsplit(url)
                if parts.scheme not in ('http', 'https') or not parts.netloc:
                    continue
                identity = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), parts.query, ''))
            except ValueError:
                continue
            if identity not in seen:
                seen.add(identity)
                results.append(row)
    warnings = []
    if cv and cv.get('text_status') == 'needs_ocr':
        warnings.append('Your CV has no selectable text. Results use your profession and interests; upload a text-based PDF to include CV skills.')
    if cv and cv.get('text_status') == 'truncated':
        warnings.append('Only the first 40,000 extracted CV characters were used.')
    result = {'query': ' · '.join(queries), 'queries': queries,
              'profile_fingerprint': fingerprint, 'warnings': warnings,
              'retrieved_at': datetime.now(timezone.utc).isoformat(),
              'response': {'results': results[:max_results]}}
    destination = ROOT / 'data' / 'discovery' / f'{profile_path.stem}.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(destination)
    return result, destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, help='Settings profile JSON path')
    parser.add_argument('--max-results', type=int, default=5)
    args = parser.parse_args()
    profile_path = args.profile
    if profile_path is None:
        profiles = sorted((ROOT / 'data' / 'profiles').glob('*.json'))
        if not profiles:
            parser.error('Save a profile at http://127.0.0.1:8000/settings first.')
        if len(profiles) != 1:
            parser.error('Multiple profiles found. Choose one with --profile:\n' + '\n'.join(str(p) for p in profiles))
        profile_path = profiles[0]
    try:
        result, destination = fetch_for_profile(profile_path, args.max_results)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f'{exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f'\nSaved results: {destination}')


def fetch_learning_source(url, title='', excerpt=''):
    """Fetch source text through Keenable; explicitly label an excerpt fallback."""
    from urllib.parse import urlencode
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        raise ValueError('Choose a valid source URL.')
    load_dotenv(ROOT / '.env')
    key = os.getenv('KEENABLE_API_KEY')
    warning = ''
    text = ''
    if key:
        request = Request('https://api.keenable.ai/v1/fetch?' + urlencode(
            {'url': url, 'live': 'true', 'max_chars': 50000}),
            headers={'X-API-Key': key, 'X-Keenable-Title': 'Curio Learning'})
        try:
            with urlopen(request, timeout=60) as response:
                data = json.load(response)
            if isinstance(data, dict):
                nested = data.get('data') if isinstance(data.get('data'), dict) else data
                text = nested.get('markdown') or nested.get('content') or nested.get('text') or ''
            if not isinstance(text, str):
                text = ''
        except (HTTPError, URLError, TimeoutError, ValueError):
            pass
    if not text.strip():
        if not isinstance(excerpt, str) or not excerpt.strip():
            raise RuntimeError('Could not fetch readable source content. Try another source.')
        text = excerpt
        warning = 'Full page could not be retrieved. This lesson uses only the search excerpt; ask about missing details cautiously.'
    elif len(text) >= 50000:
        warning = 'Source text is limited to the first 50,000 characters; some details may be missing.'
    return {'content_id': url, 'title': title or parts.netloc, 'url': url,
            'content': ('Coverage note: ' + warning + '\n\n' if warning else '') + text[:50000],
            'warning': warning}


if __name__ == '__main__':
    main()
