"""Collect per-identity tags only from posts with name and address evidence."""
import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from place_identity import ensure_ids, text
from blog_evidence import address_evidence_excerpt, name_matches, provider_url_matches, tags_from_posts

from Preprocess.crawler.http_client import get as _get
from Preprocess.crawler.storage import atomic_output
INPUT_CSV = ROOT / 'Preprocess/data/processed/chungnam_places_filtered.csv'
OUTPUT_CSV = ROOT / 'Preprocess/data/processed/blog_tags.csv'
PAGE_HEADERS = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile Safari/604.1'}


def canonical_blog_url(url):
    parsed = urlparse(url)
    if (parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or
            parsed.hostname not in ('blog.naver.com', 'm.blog.naver.com')):
        return ''
    parts = parsed.path.strip('/').split('/')
    if parsed.path.lower() == '/postview.naver':
        query = parse_qs(parsed.query)
        parts = [query.get('blogId', [''])[0], query.get('logNo', [''])[0]]
    if len(parts) != 2 or not re.fullmatch(r'[a-zA-Z0-9_-]+', parts[0]) or not parts[1].isdigit():
        return ''
    return f'https://blog.naver.com/{parts[0]}/{parts[1]}'


def search_blog_urls(place, display=30, trace=None):
    if not 1 <= display <= 30:
        raise ValueError('장소당 고유 글은 최대 30개입니다.')
    load_dotenv(ROOT / '.env')
    query = ' '.join([text(place['가게명']), text(place['주소']), '후기'])
    response = _get('https://openapi.naver.com/v1/search/blog.json', kind='search', trace=trace,
        headers={'X-Naver-Client-Id': os.environ['NAVER_API_ID'],
                 'X-Naver-Client-Secret': os.environ['NAVER_API_SECRET']},
        params={'query': query, 'display': display, 'sort': 'sim'}, timeout=10)
    items = response.json().get('items', [])
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError('Unsupported search payload')
    urls = [canonical_blog_url(item.get('link', '')) for item in items]
    urls = [url for url in urls if url]
    return list(dict.fromkeys(urls))[:display], query


def parse_post_html(html, url, place, query):
    """Keep short identity excerpts and tags, never a whole article in output."""
    soup = BeautifulSoup(html, 'html.parser')
    body = soup.select_one('.se-main-container, #postViewArea, .post_ct')
    if body is None:
        return None
    body_text = body.get_text(' ', strip=True)
    name = text(place['가게명'])
    paragraphs = [p.get_text(' ', strip=True) for p in body.select('p, div.se-text-paragraph')]
    paragraphs = paragraphs or [body_text]
    name_excerpt = next((p[:1000] for p in paragraphs if name_matches(name, p)), '')
    address_excerpt = address_evidence_excerpt(place, body_text)
    tag_match = re.search(r'var gsTagName\s*=\s*"([^"\n]*)"', html)
    tags = [t.strip() for t in tag_match.group(1).split(',') if t.strip()] if tag_match else []
    pid = text(place.get('provider_place_id'))
    provider_url = next((a.get('href', '') for a in body.select('a[href]')
                         if provider_url_matches(pid, a.get('href', ''))), '')
    return {'url': url, 'query': query, 'fetched_at': datetime.now(timezone.utc).isoformat(),
            'name_excerpt': name_excerpt, 'address_excerpt': address_excerpt,
            'provider_url': provider_url, 'tags': tags,
            'tag_parser': 'gsTagName' if tag_match else 'no_supported_tag_payload'}


def fetch_post(url, place, query, trace=None):
    url = canonical_blog_url(url)
    if not url:
        raise ValueError('Unsupported blog URL')
    mobile = url.replace('://blog.naver.com', '://m.blog.naver.com')
    response = _get(mobile, headers=PAGE_HEADERS, timeout=10, trace=trace)
    return parse_post_html(response.text, url, place, query)


def _failure(exc):
    response = getattr(exc, 'response', None)
    return {'error_type': type(exc).__name__, 'http_status': getattr(response, 'status_code', None)}


class CollectionInterrupted(KeyboardInterrupt):
    def __init__(self, result):
        super().__init__('Collection interrupted; audit checkpoint available')
        self.result = result


def _collection_result(place, audit, interrupted=False):
    verified = [post for post in audit['posts'] if post['outcome'] == 'identity_accepted']
    tags, verified = tags_from_posts(place, verified)
    status = ('interrupted' if interrupted else 'fetch_error' if audit.get('search_error') else
              'verified' if tags else 'fetch_error' if audit['fetch_failure'] else
              'parse_unavailable' if audit['body_unavailable'] or audit['tag_payload_unavailable'] else
              'no_verified_posts')
    audit.update(unique_tag_count=len(tags), finished_at=datetime.now(timezone.utc).isoformat(), status=status)
    return {'record': {'blog_tags': json.dumps(tags, ensure_ascii=False),
                       'verified_posts': json.dumps(verified, ensure_ascii=False), 'blog_tag_status': status},
            'audit': audit}


def collect_with_audit(place, delay=0.2, max_posts=30, previous=None):
    from blog_evidence import verify_post
    if not 1 <= max_posts <= 30:
        raise ValueError('장소당 고유 글은 최대 30개입니다.')
    audit = copy.deepcopy(previous) if previous is not None else {
        'place_id': place['place_id'],
        'place_identity': {key: text(place.get(key)) for key in ('identity_key', '가게명', '주소')},
        'started_at': datetime.now(timezone.utc).isoformat(),
        'query': '', 'search_returned_urls': 0, 'fetch_success': 0, 'fetch_failure': 0,
        'identity_accepted': 0, 'identity_rejected': 0, 'body_unavailable': 0,
        'tag_payload_unavailable': 0, 'posts': [], 'request_trace': []}
    if (audit['place_id'] != place['place_id'] or
            audit.get('place_identity') != {key: text(place.get(key)) for key in ('identity_key', '가게명', '주소')}):
        raise ValueError('재개할 장소 ID가 다릅니다.')
    urls = audit.get('urls')
    if urls is not None and (len(urls) > max_posts or len(set(urls)) != len(urls) or
                             any(canonical_blog_url(url) != url for url in urls)):
        raise ValueError('재개 URL 제한 또는 정규화 불일치')
    try:
        if urls is None:
            try:
                urls, query = search_blog_urls(place, display=max_posts, trace=audit['request_trace'])
                audit.update(query=query, urls=urls, search_returned_urls=len(urls))
                audit.pop('search_error', None)
            except (requests.RequestException, KeyError, ValueError, TypeError, AttributeError) as exc:
                audit['search_error'] = _failure(exc)
                return _collection_result(place, audit)
        query = audit['query']
        finished = {post['url'] for post in audit['posts']}
        if not finished.issubset(set(urls)):
            raise ValueError('재개 글이 고정된 URL 목록 밖에 있습니다.')
        for url in urls:
            if url in finished:
                continue
            try:
                post = fetch_post(url, place, query, trace=audit['request_trace'])
                audit['fetch_success'] += 1
                if post is None:
                    audit['body_unavailable'] += 1
                    audit['identity_rejected'] += 1
                    audit['posts'].append({'url': url, 'outcome': 'body_unavailable'})
                else:
                    accepted = verify_post(place, post)
                    audit['identity_accepted' if accepted else 'identity_rejected'] += 1
                    audit['tag_payload_unavailable'] += post['tag_parser'] != 'gsTagName'
                    audit['posts'].append({**post, 'outcome': 'identity_accepted' if accepted else 'identity_rejected'})
            except (requests.RequestException, ValueError) as exc:
                audit['fetch_failure'] += 1
                audit['posts'].append({'url': url, 'outcome': 'fetch_error', **_failure(exc)})
            time.sleep(delay)
    except KeyboardInterrupt:
        raise CollectionInterrupted(_collection_result(place, audit, interrupted=True)) from None
    return _collection_result(place, audit)


def collect_place_tags(place, delay=0.2):
    return collect_with_audit(place, delay)['record']


def _done_ids(df, retry_unverified=False):
    if 'place_id' not in df or 'blog_tag_status' not in df:
        return set()  # name-only legacy rows never suppress recollection
    terminal = ['verified'] if retry_unverified else ['verified', 'no_verified_posts']
    latest = df.drop_duplicates('place_id', keep='last')
    return set(latest.loc[latest['blog_tag_status'].isin(terminal), 'place_id'])


def load_done_set(path=OUTPUT_CSV, retry_unverified=False):
    if not Path(path).exists():
        return set()
    return _done_ids(pd.read_csv(path, encoding='utf-8-sig', dtype={'place_id': str}), retry_unverified)


def main(input_path=INPUT_CSV, output_path=OUTPUT_CSV, limit=None, retry_unverified=False, status=None):
    load_dotenv(ROOT / '.env')
    if not os.getenv('NAVER_API_ID') or not os.getenv('NAVER_API_SECRET'):
        raise SystemExit('NAVER_API_ID / NAVER_API_SECRET가 필요합니다. 외부 호출은 수행하지 않았습니다.')
    if limit is not None and limit < 0:
        raise ValueError('limit은 0 이상이어야 합니다.')
    df = ensure_ids(pd.read_csv(input_path, encoding='utf-8-sig', dtype={'provider_place_id': str, 'place_id': str})).drop_duplicates('place_id')
    if status:
        if 'blog_tag_status' not in df:
            raise SystemExit('--status 필터에는 blog_tag_status 컬럼이 필요합니다.')
        df = df[df['blog_tag_status'].eq(status)]
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ['place_id', 'identity_key', '가게명', '주소', 'provider', 'provider_place_id',
              'blog_tags', 'verified_posts', 'blog_tag_status', 'collected_at']
    existing = pd.DataFrame(columns=fields)
    if output_path.exists():
        existing = pd.read_csv(output_path, encoding='utf-8-sig', dtype={'place_id': str, 'provider_place_id': str})
        if not set(fields).issubset(existing.columns):
            import shutil
            backup = str(output_path) + f'.legacy-{datetime.now():%Y%m%d%H%M%S%f}.csv'
            shutil.copy2(output_path, backup)
            # ID-based history survives schema upgrades. Name-only rows remain in the backup.
            if 'place_id' not in existing or 'verified_posts' not in existing:
                existing = pd.DataFrame(columns=fields)
    audit_dir = output_path.with_name(output_path.stem + '.audit')
    dirty = False

    def upsert(row):
        nonlocal existing, dirty
        existing = pd.concat([existing[existing['place_id'].ne(row['place_id'])], pd.DataFrame([row])], ignore_index=True)
        dirty = True

    def flush():
        nonlocal dirty
        if dirty:
            with atomic_output(output_path, encoding='utf-8-sig') as stream:
                existing.to_csv(stream, index=False)
            dirty = False

    # Per-place journals are durable before CSV snapshots. Recover a crash between them.
    for audit_path in sorted(audit_dir.glob('*.json')):
        if '.history-' in audit_path.name:
            continue
        checkpoint = json.loads(audit_path.read_text(encoding='utf-8'))
        if checkpoint.get('status') == 'interrupted' or not {'record', 'place', 'collected_at'}.issubset(checkpoint):
            continue
        row = {**checkpoint['place'], **checkpoint['record'], 'collected_at': checkpoint['collected_at']}
        previous = existing[existing['place_id'].eq(row['place_id'])]
        if previous.empty or text(previous.iloc[-1].get('collected_at')) < row['collected_at']:
            upsert(row)
    done = _done_ids(existing, retry_unverified)
    by_id = existing.drop_duplicates('place_id', keep='last').set_index('place_id')
    for place in df.to_dict('records'):
        if place['place_id'] in done:
            prior = by_id.loc[place['place_id']]
            if any(text(prior.get(key)) != text(place.get(key)) for key in ('identity_key', '가게명', '주소')):
                done.remove(place['place_id'])
    remaining = df[~df['place_id'].isin(done)]
    if limit is not None:
        remaining = remaining.head(limit)
    try:
        for index, place in enumerate(tqdm(remaining.to_dict('records'), desc='장소 ID별 수집'), 1):
            audit_path = audit_dir / (hashlib.sha256(place['place_id'].encode()).hexdigest() + '.json')
            previous = None
            if audit_path.exists():
                checkpoint = json.loads(audit_path.read_text(encoding='utf-8'))
                if checkpoint.get('status') == 'interrupted':
                    previous = {key: value for key, value in checkpoint.items()
                                if key not in ('record', 'place', 'collected_at')}
                else:
                    import shutil
                    shutil.copy2(audit_path, audit_path.with_name(
                        audit_path.stem + f'.history-{datetime.now():%Y%m%d%H%M%S%f}.json'))
            interrupted = None
            try:
                result = collect_with_audit(place, previous=previous)
            except CollectionInterrupted as exc:
                result, interrupted = exc.result, exc
            place_fields = {key: place.get(key, '') for key in fields[:6]}
            collected_at = datetime.now(timezone.utc).isoformat()
            with atomic_output(audit_path) as stream:
                json.dump({**result['audit'], 'record': result['record'], 'place': place_fields,
                           'collected_at': collected_at}, stream, ensure_ascii=False, indent=2)
            if interrupted is not None:
                raise interrupted
            upsert({**place_fields, **result['record'], 'collected_at': collected_at})
            if index % 25 == 0:
                flush()
            time.sleep(0.5)
    finally:
        flush()



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=INPUT_CSV)
    parser.add_argument('--output', type=Path, default=OUTPUT_CSV)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--test', action='store_true', help='실제 API 호출을 최대 5개로 제한')
    parser.add_argument('--retry-unverified', action='store_true')
    parser.add_argument('--status', choices=['ambiguous_legacy', 'legacy_unverified', 'needs_collection'])
    args = parser.parse_args()
    main(args.input, args.output, 5 if args.test else args.limit, args.retry_unverified, args.status)
