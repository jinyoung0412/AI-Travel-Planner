"""Collect per-identity tags only from posts with name and address evidence."""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from place_identity import ensure_ids, text
from blog_evidence import address_anchor, name_matches, provider_url_matches, tags_from_posts

load_dotenv(ROOT / '.env')
INPUT_CSV = ROOT / 'Preprocess/data/processed/chungnam_places_filtered.csv'
OUTPUT_CSV = ROOT / 'Preprocess/data/processed/blog_tags.csv'
PAGE_HEADERS = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile Safari/604.1'}


def search_blog_urls(place, display=30):
    query = ' '.join([text(place['가게명']), text(place['주소']), '후기'])
    response = requests.get('https://openapi.naver.com/v1/search/blog.json',
        headers={'X-Naver-Client-Id': os.environ['NAVER_API_ID'],
                 'X-Naver-Client-Secret': os.environ['NAVER_API_SECRET']},
        params={'query': query, 'display': display, 'sort': 'sim'}, timeout=10)
    response.raise_for_status()
    urls = [item['link'] for item in response.json().get('items', [])
            if urlparse(item.get('link', '')).hostname in ('blog.naver.com', 'm.blog.naver.com')]
    return list(dict.fromkeys(urls)), query


def fetch_post(url, place, query):
    mobile = url.replace('://blog.naver.com', '://m.blog.naver.com')
    response = requests.get(mobile, headers=PAGE_HEADERS, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    # Page chrome/search snippets/hashtags alone are not identity evidence.
    body = soup.select_one('.se-main-container, #postViewArea, .post_ct')
    if body is None:
        return None
    body_text = body.get_text(' ', strip=True)
    name = text(place['가게명'])
    anchor = address_anchor(place)
    # Keep short source excerpts, including separate name/address paragraphs.
    paragraphs = [p.get_text(' ', strip=True) for p in body.select('p, div.se-text-paragraph')]
    paragraphs = paragraphs or [body_text]
    name_excerpt = next((p[:1000] for p in paragraphs if name_matches(name, p)), '')
    road_name = anchor[1].rsplit(' ', 1)[0] if anchor else ''
    addr_paragraph = next((p for p in paragraphs if road_name and road_name in p), '')
    # City may be in the preceding line of the post: preserve local context.
    index = body_text.find(addr_paragraph) if addr_paragraph else -1
    address_excerpt = body_text[max(0, index - 200):index + len(addr_paragraph) + 200][:1500] if index >= 0 else ''
    tag_match = re.search(r'var gsTagName\s*=\s*"([^"]*)"', response.text)
    tags = [t.strip() for t in tag_match.group(1).split(',') if t.strip()] if tag_match else []
    pid = text(place.get('provider_place_id'))
    provider_url = next((a.get('href', '') for a in body.select('a[href]')
                         if provider_url_matches(pid, a.get('href', ''))), '')
    return {'url': url, 'query': query, 'fetched_at': datetime.now(timezone.utc).isoformat(),
            'name_excerpt': name_excerpt, 'address_excerpt': address_excerpt,
            'provider_url': provider_url, 'tags': tags}


def collect_place_tags(place, delay=0.2):
    posts, errors = [], 0
    try:
        urls, query = search_blog_urls(place)
    except (requests.RequestException, KeyError):
        return {'blog_tags': '{}', 'verified_posts': '[]', 'blog_tag_status': 'fetch_error'}
    for url in urls:
        try:
            post = fetch_post(url, place, query)
            if post:
                posts.append(post)
        except requests.RequestException:
            errors += 1
        time.sleep(delay)
    tags, verified = tags_from_posts(place, posts)
    return {'blog_tags': json.dumps(tags, ensure_ascii=False),
            'verified_posts': json.dumps(verified, ensure_ascii=False),
            'blog_tag_status': 'verified' if verified else 'fetch_error' if errors else 'no_verified_posts'}


def load_done_set(path=OUTPUT_CSV, retry_unverified=False):
    if not Path(path).exists():
        return set()
    df = pd.read_csv(path, encoding='utf-8-sig', dtype={'place_id': str})
    if 'place_id' not in df or 'blog_tag_status' not in df:
        return set()  # name-only legacy rows never suppress recollection
    terminal = ['verified'] if retry_unverified else ['verified', 'no_verified_posts']
    latest = df.drop_duplicates('place_id', keep='last')
    return set(latest.loc[latest['blog_tag_status'].isin(terminal), 'place_id'])


def main(input_path=INPUT_CSV, output_path=OUTPUT_CSV, limit=None, retry_unverified=False, status=None):
    if not os.getenv('NAVER_API_ID') or not os.getenv('NAVER_API_SECRET'):
        raise SystemExit('NAVER_API_ID / NAVER_API_SECRET가 필요합니다. 외부 호출은 수행하지 않았습니다.')
    df = ensure_ids(pd.read_csv(input_path, encoding='utf-8-sig', dtype={'provider_place_id': str, 'place_id': str})).drop_duplicates('place_id')
    if status:
        if 'blog_tag_status' not in df:
            raise SystemExit('--status 필터에는 blog_tag_status 컬럼이 필요합니다.')
        df = df[df['blog_tag_status'].eq(status)]
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and 'verified_posts' not in pd.read_csv(output_path, nrows=0).columns:
        from datetime import datetime
        output_path.rename(str(output_path) + f'.legacy-{datetime.now():%Y%m%d%H%M%S%f}.csv')
    done = load_done_set(output_path, retry_unverified)
    remaining = df[~df['place_id'].isin(done)]
    if limit is not None:
        remaining = remaining.head(limit)
    for place in tqdm(remaining.to_dict('records'), desc='장소 ID별 수집'):
        result = collect_place_tags(place)
        row = {k: place.get(k, '') for k in ('place_id', 'identity_key', '가게명', '주소', 'provider', 'provider_place_id')}
        row.update(result)
        row['collected_at'] = datetime.now(timezone.utc).isoformat()
        pd.DataFrame([row]).to_csv(output_path, mode='a', header=not output_path.exists(),
                                 index=False, encoding='utf-8-sig')
        time.sleep(0.5)


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
