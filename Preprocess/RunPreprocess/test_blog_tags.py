"""
네이버 블로그 태그 수집 파이프라인 테스트.
장소 5개에 대해 블로그 검색 → 포스트별 gsTagName 추출 → 태그 집계까지 전체 흐름 확인.
"""
import os, sys, re, time, io
import requests

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

NAVER_ID     = os.environ['NAVER_API_ID']
NAVER_SECRET = os.environ['NAVER_API_SECRET']

BLOG_SEARCH_URL = 'https://openapi.naver.com/v1/search/blog.json'
BLOG_HEADERS    = {
    'X-Naver-Client-Id':     NAVER_ID,
    'X-Naver-Client-Secret': NAVER_SECRET,
}
PAGE_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
    )
}

TEST_PLACES = [
    '독립기념관',
    '현충사',
    '신사우물갈비 불당본점',
    '공세리성당',
    '뚜쥬루 빵돌가마마을',
]


def search_blog_urls(place_name: str, display=5) -> list[str]:
    resp = requests.get(
        BLOG_SEARCH_URL,
        headers=BLOG_HEADERS,
        params={'query': f'{place_name} 후기', 'display': display, 'sort': 'sim'},
        timeout=10,
    )
    resp.raise_for_status()
    items = resp.json().get('items', [])
    # 네이버 블로그만 필터링
    return [
        it['link'] for it in items
        if 'blog.naver.com' in it.get('link', '')
    ]


def fetch_tags(blog_url: str) -> list[str]:
    mobile = blog_url.replace('blog.naver.com', 'm.blog.naver.com')
    try:
        page = requests.get(mobile, headers=PAGE_HEADERS, timeout=8)
        match = re.search(r'var gsTagName\s*=\s*"([^"]+)"', page.text)
        if match:
            return [t.strip() for t in match.group(1).split(',') if t.strip()]
    except Exception:
        pass
    return []


def collect_place_tags(place_name: str, n_posts=5) -> dict:
    urls = search_blog_urls(place_name, display=n_posts)
    all_tags: dict[str, int] = {}
    post_results = []

    for url in urls:
        tags = fetch_tags(url)
        post_results.append({'url': url, 'tags': tags})
        for t in tags:
            all_tags[t] = all_tags.get(t, 0) + 1
        time.sleep(0.2)

    # 빈도 내림차순
    sorted_tags = sorted(all_tags.items(), key=lambda x: -x[1])
    return {
        'posts': len(post_results),
        'naver_posts': len(urls),
        'tag_freq': sorted_tags,
        'detail': post_results,
    }


def main():
    for place in TEST_PLACES:
        print(f'\n{"="*55}')
        print(f'  {place}')
        print('='*55)

        result = collect_place_tags(place, n_posts=5)
        print(f'  수집 포스트: {result["naver_posts"]}개 (네이버 블로그)')

        if result['tag_freq']:
            print(f'  태그 ({len(result["tag_freq"])}종):')
            for tag, cnt in result['tag_freq'][:20]:
                bar = '■' * cnt
                print(f'    {bar} ({cnt})  #{tag}')
        else:
            print('  태그 없음')

        print()
        for i, p in enumerate(result['detail'], 1):
            print(f'  [{i}] {p["url"].split("/")[-2]}/... → {p["tags"][:5]}')

        time.sleep(0.3)


if __name__ == '__main__':
    main()
