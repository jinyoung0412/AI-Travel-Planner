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

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from place_identity import ensure_ids, text, place_id as canonical_place_id
from blog_evidence import address_evidence_excerpt, name_matches, provider_url_matches, tags_from_posts, post_url_key

from Preprocess.RunPreprocess.collection_state import (
    identity_snapshot, audit_matches_place, retryable_post, has_retryable_failures, archive_file,
)
from Preprocess.crawler.http_client import get as _get
from Preprocess.crawler.storage import atomic_output, exclusive_output
INPUT_CSV = ROOT / 'Preprocess/data/processed/chungnam_places_filtered.csv'
OUTPUT_CSV = ROOT / 'Preprocess/data/processed/blog_tags.csv'
PAGE_HEADERS = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile Safari/604.1'}


def canonical_blog_url(url):
    key = post_url_key(url)
    return f'https://blog.naver.com/{key}' if key else ''


def search_blog_urls(place, display=30, trace=None):
    if not 1 <= display <= 30:
        raise ValueError('장소당 고유 글은 최대 30개입니다.')
    load_dotenv(ROOT / '.env')
    query = ' '.join([text(place['가게명']), text(place['주소']), '후기'])
    response = _get('https://openapi.naver.com/v1/search/blog.json', kind='search', trace=trace,
        headers={'X-Naver-Client-Id': os.environ['NAVER_API_ID'],
                 'X-Naver-Client-Secret': os.environ['NAVER_API_SECRET']},
        params={'query': query, 'display': display, 'sort': 'sim'}, timeout=10)
    payload = response.json()
    if not isinstance(payload, dict) or 'items' not in payload:
        raise ValueError('Unsupported search payload')
    items = payload['items']
    if not isinstance(items, list) or any(not isinstance(item, dict) or
            not isinstance(item.get('link'), str) or not item['link'] for item in items):
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
            'tag_scope': 'whole_post_unreviewed',
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
    posts = audit['posts']
    # These are latest unique-URL outcomes, never cumulative HTTP-attempt counts.
    audit.update(fetch_success=sum(p['outcome'] != 'fetch_error' for p in posts),
                 fetch_failure=sum(p['outcome'] == 'fetch_error' for p in posts),
                 identity_accepted=sum(p['outcome'] == 'identity_accepted' for p in posts),
                 identity_rejected=sum(p['outcome'] == 'identity_rejected' for p in posts),
                 body_unavailable=sum(p['outcome'] == 'body_unavailable' for p in posts),
                 tag_payload_unavailable=sum(p['outcome'] in ('identity_accepted', 'identity_rejected') and
                     p.get('tag_parser', 'gsTagName') != 'gsTagName' for p in posts))
    verified = [post for post in posts if post['outcome'] == 'identity_accepted']
    tags, verified = tags_from_posts(place, verified)
    pending_review = sum(p['outcome'] == 'identity_accepted' and bool(p.get('tags'))
                         and p not in verified for p in posts)
    audit['tag_review_pending'] = pending_review
    status = ('interrupted' if interrupted else 'fetch_error' if audit.get('search_error') else
              'verified' if tags else 'fetch_error' if audit['fetch_failure'] else
              'needs_review' if pending_review else
              'parse_unavailable' if audit['body_unavailable'] or audit['tag_payload_unavailable'] else
              'no_verified_posts')
    audit.update(unique_tag_count=len(tags), finished_at=datetime.now(timezone.utc).isoformat(), status=status)
    return {'record': {'blog_tags': json.dumps(tags, ensure_ascii=False),
                       'verified_posts': json.dumps(verified, ensure_ascii=False), 'blog_tag_status': status},
            'audit': audit}


def _check_urls(audit, max_posts):
    urls = audit.get('urls')
    if urls is None:
        return
    if (not isinstance(urls, list) or len(urls) > max_posts or len(set(urls)) != len(urls) or
            any(canonical_blog_url(url) != url for url in urls)):
        raise ValueError('재개 URL 제한 또는 정규화 불일치')
    posts = audit['posts']
    if (any(not isinstance(post, dict) or post.get('url') not in urls for post in posts) or
            len({post['url'] for post in posts}) != len(posts) or
            any(entry['post']['url'] not in urls for entry in audit.get('post_history', []))):
        raise ValueError('재개 글이 고정된 URL 목록 밖에 있거나 중복입니다.')


def _save_post(audit, post):
    for index, previous in enumerate(audit['posts']):
        if previous['url'] == post['url']:
            audit.setdefault('post_history', []).append({
                'post': previous, 'superseded_at': datetime.now(timezone.utc).isoformat()})
            audit['posts'][index] = post
            return
    audit['posts'].append(post)


def collect_with_audit(place, delay=0.2, max_posts=30, previous=None, retry_failed=False):
    """Resume untouched URLs; retry transient failures only on explicit request.

    Each selected URL gets one logical fetch per call (HTTP boundary: <=2 tries).
    Latest outcomes stay unique; superseded failures and every HTTP trace survive.
    """
    from blog_evidence import verify_post
    if not 1 <= max_posts <= 30:
        raise ValueError('장소당 고유 글은 최대 30개입니다.')
    audit = copy.deepcopy(previous) if previous is not None else {
        'place_id': place['place_id'], 'place_identity': identity_snapshot(place),
        'started_at': datetime.now(timezone.utc).isoformat(),
        'query': '', 'search_returned_urls': 0, 'posts': [], 'request_trace': []}
    if not audit_matches_place(audit, place):
        raise ValueError('재개할 장소 ID가 다릅니다.')
    _check_urls(audit, max_posts)
    if audit.get('search_error') and not audit.get('search_history'):
        audit['search_history'] = [dict(audit['search_error'])]
    try:
        if audit.get('urls') is None:
            if previous is not None and audit.get('search_error') and not retry_failed:
                return _collection_result(place, audit)
            try:
                urls, query = search_blog_urls(place, display=max_posts, trace=audit['request_trace'])
                audit.update(query=query, urls=urls, search_returned_urls=len(urls))
                audit.pop('search_error', None)
                _check_urls(audit, max_posts)
            except (requests.RequestException, KeyError, ValueError, TypeError, AttributeError) as exc:
                audit['search_error'] = _failure(exc)
                audit.setdefault('search_history', []).append(dict(audit['search_error']))
                return _collection_result(place, audit)
        query = audit['query']
        latest = {post['url']: post for post in audit['posts']}
        for url in audit['urls']:
            if url in latest and not (retry_failed and retryable_post(latest[url])):
                continue
            trace_start = len(audit['request_trace'])
            try:
                post = fetch_post(url, place, query, trace=audit['request_trace'])
                if post is None:
                    result = {'url': url, 'outcome': 'body_unavailable'}
                else:
                    accepted = verify_post(place, post)
                    result = {**post, 'url': url,
                              'outcome': 'identity_accepted' if accepted else 'identity_rejected'}
            except (requests.RequestException, ValueError) as exc:
                result = {'url': url, 'outcome': 'fetch_error', **_failure(exc)}
            except KeyboardInterrupt:
                audit.setdefault('interrupted_fetches', []).append({
                    'url': url, 'request_trace_range': [trace_start, len(audit['request_trace'])]})
                raise
            result['request_trace_range'] = [trace_start, len(audit['request_trace'])]
            _save_post(audit, result)
            time.sleep(delay)
    except KeyboardInterrupt:
        raise CollectionInterrupted(_collection_result(place, audit, interrupted=True)) from None
    return _collection_result(place, audit)


def collect_place_tags(place, delay=0.2):
    return collect_with_audit(place, delay)['record']


def _verified_complete(row, current):
    if text(row.get('blog_tag_status')) != 'verified':
        return False
    try:
        if canonical_place_id(current) != current.get('place_id'):
            return False
        snapshot = identity_snapshot(current)
        current = {**current, 'provider': snapshot['provider'], 'provider_place_id': snapshot['provider_place_id']}
        tags, posts = tags_from_posts(current, row.get('verified_posts'))
        return bool(tags and posts)
    except (TypeError, ValueError, AttributeError):
        return False


def _done_ids(df, retry_unverified=False, current_places=None):
    if 'place_id' not in df or 'blog_tag_status' not in df:
        return set()  # name-only legacy rows never suppress recollection
    current = (None if current_places is None else
               {row['place_id']: row for row in current_places.to_dict('records')})
    done = set()
    for row in df.drop_duplicates('place_id', keep='last').to_dict('records'):
        place = row if current is None else current.get(row['place_id'])
        if place is None or (current is not None and identity_snapshot(row) != identity_snapshot(place)):
            continue
        if (_verified_complete(row, place) or
                (not retry_unverified and row.get('blog_tag_status') == 'no_verified_posts')):
            done.add(row['place_id'])
    return done


def load_done_set(path=OUTPUT_CSV, retry_unverified=False):
    if not Path(path).exists():
        return set()
    return _done_ids(pd.read_csv(path, encoding='utf-8-sig', dtype={'place_id': str, 'provider_place_id': str}), retry_unverified)


def _resume_plan(checkpoint, place, retry_unverified, retry_failed):
    if not audit_matches_place(checkpoint, place):
        return True, None
    # Explicit broad recollection is distinct from retrying frozen failed URLs.
    recollect = retry_unverified and checkpoint.get('status') in ('no_verified_posts', 'parse_unavailable')
    invalid_verified = (checkpoint.get('status') == 'verified' and
                        not _verified_complete(checkpoint.get('record', {}), place))
    if recollect or invalid_verified:
        return True, None
    urls = checkpoint.get('urls')
    pending_urls = (urls is None and not checkpoint.get('search_error')) or bool(
        set(urls or []) - {post['url'] for post in checkpoint.get('posts', [])})
    if (checkpoint.get('status') != 'interrupted' and not pending_urls and
            not (retry_failed and has_retryable_failures(checkpoint))):
        return False, None
    previous = {key: value for key, value in checkpoint.items()
                if key not in ('record', 'place', 'collected_at')}
    return True, previous


def main(input_path=INPUT_CSV, output_path=OUTPUT_CSV, limit=None, retry_unverified=False, status=None, retry_failed=False):
    # One owner covers CSV read/merge, per-place journals, history and snapshots.
    with exclusive_output(output_path):
        return _main(input_path, output_path, limit, retry_unverified, status, retry_failed)


def _main(input_path, output_path, limit, retry_unverified, status, retry_failed):
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
    done = _done_ids(existing, retry_unverified, current_places=df)
    if retry_failed:
        for place in df.to_dict('records'):
            journal = audit_dir / (hashlib.sha256(place['place_id'].encode()).hexdigest() + '.json')
            if journal.exists():
                audit = json.loads(journal.read_text(encoding='utf-8'))
                if audit_matches_place(audit, place) and has_retryable_failures(audit):
                    done.discard(place['place_id'])

    def work():
        selected = 0
        for place in df[~df['place_id'].isin(done)].to_dict('records'):
            if limit is not None and selected >= limit:
                break
            audit_path = audit_dir / (hashlib.sha256(place['place_id'].encode()).hexdigest() + '.json')
            previous = None
            if audit_path.exists():
                checkpoint = json.loads(audit_path.read_text(encoding='utf-8'))
                actionable, previous = _resume_plan(checkpoint, place, retry_unverified, retry_failed)
                if not actionable:
                    continue
            selected += 1
            # Keep only this place's audit in memory; a full batch can contain
            # thousands of journals, each with up to 30 article excerpts.
            yield place, audit_path, previous

    try:
        for index, (place, audit_path, previous) in enumerate(tqdm(work(), desc='장소 ID별 수집'), 1):
            if audit_path.exists():
                # A stale identity starts fresh; exact old bytes remain recoverable.
                archive_file(audit_path)
            interrupted = None
            try:
                result = collect_with_audit(place, previous=previous, **({'retry_failed': True} if retry_failed else {}))
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
    parser.add_argument('--test', action='store_true', help=(
        '장소 최대 5곳 수집(HTTP 5회 제한 아님). 장소당 최대 30개 글과 검색 각 최대 2회 시도; '
        '한 실행의 HTTP 요청은 재시도 포함 최대 310회'))
    parser.add_argument('--retry-unverified', action='store_true')
    parser.add_argument('--retry-failed', action='store_true', help='고정 URL의 일시적 실패만 한 번 재시도; 정상 글은 다시 요청하지 않음')
    parser.add_argument('--status', choices=['ambiguous_legacy', 'legacy_unverified', 'needs_collection'])
    args = parser.parse_args()
    main(args.input, args.output, 5 if args.test else args.limit, args.retry_unverified, args.status, args.retry_failed)
