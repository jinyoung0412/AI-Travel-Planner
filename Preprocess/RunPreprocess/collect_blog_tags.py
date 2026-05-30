"""
장소별 네이버 블로그 태그 수집 파이프라인.
- 입력: chungnam_places_filtered.csv (14,270개)
- 필터: 방문자수==0 AND 블로그수==0 제거
- 수집 대상: 블로그수 >= 5 인 장소
- 출력: blog_tags.csv (장소명, 태그 빈도 상위 20개)
- 이어하기 지원: 이미 처리된 장소는 건너뜀
"""
import os, sys, re, time, io, json
import requests
import pandas as pd
from tqdm import tqdm

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

NAVER_ID     = os.environ['NAVER_API_ID']
NAVER_SECRET = os.environ['NAVER_API_SECRET']

BLOG_SEARCH_URL = 'https://openapi.naver.com/v1/search/blog.json'
BLOG_HEADERS = {
    'X-Naver-Client-Id':     NAVER_ID,
    'X-Naver-Client-Secret': NAVER_SECRET,
}
PAGE_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
    )
}

INPUT_CSV  = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'chungnam_places_filtered.csv')
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'blog_tags.csv')

N_POSTS  = 30  # 장소당 검색 포스트 수 (API 1회로 최대 수집)
MAX_TAGS = 20  # 저장할 상위 태그 수
SEARCH_DELAY = 0.5  # API 호출 간격 (초)
PAGE_DELAY   = 0.2  # 페이지 요청 간격 (초)


def search_blog_urls(place_name: str, display: int = N_POSTS) -> list[str]:
    """
    네이버 검색 API로 '{장소명} 후기' 검색 → 네이버 블로그 URL 목록을 반환.
    - '후기'를 함께 질의해 실제 방문자 리뷰 게시물 위주로 수집한다.
    - sort='sim' (정확도순)으로 관련성 높은 게시물을 우선 확보.
    - 외부 블로그 플랫폼(티스토리 등)은 태그 구조가 달라 제외, blog.naver.com만 사용.
    """
    try:
        resp = requests.get(
            BLOG_SEARCH_URL,
            headers=BLOG_HEADERS,
            params={'query': f'{place_name} 후기', 'display': display, 'sort': 'sim'},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get('items', [])
        return [
            it['link'] for it in items
            if 'blog.naver.com' in it.get('link', '')
        ]
    except Exception as e:
        tqdm.write(f'  [검색 오류] {place_name}: {e}')
        return []


def fetch_tags(blog_url: str) -> list[str]:
    """
    개별 블로그 게시물 HTML에서 작성자가 등록한 해시태그 목록을 추출.

    핵심 기법 2가지:
    1) 모바일 페이지(m.blog.naver.com) 사용:
       - PC 페이지는 본문이 iframe + 동적 렌더링으로 감싸여 있어 정적 파싱이 어렵다.
       - 모바일 페이지는 HTML 본문에 태그 정보가 그대로 노출되어 단일 HTTP 요청만으로 파싱 가능.
       - 모바일 User-Agent를 함께 위장해야 정상 응답을 받을 수 있음.
    2) 정규표현식 기반 직접 추출:
       - 네이버 블로그는 HTML 본문에 `var gsTagName = "태그1,태그2,..."` 형태의
         JavaScript 변수로 태그 목록을 노출한다.
       - 이 변수의 값만 정규식으로 추출 후 쉼표 분리하면 태그 리스트 확보 완료.
    """
    mobile = blog_url.replace('blog.naver.com', 'm.blog.naver.com')
    try:
        page = requests.get(mobile, headers=PAGE_HEADERS, timeout=8)
        match = re.search(r'var gsTagName\s*=\s*"([^"]+)"', page.text)
        if match:
            return [t.strip() for t in match.group(1).split(',') if t.strip()]
    except Exception:
        pass
    return []


def collect_place_tags(place_name: str, post_bar: tqdm) -> str:
    """
    한 장소에 대한 블로그 게시물들로부터 태그를 종합 수집해 JSON 형태로 반환.

    절차:
    1) search_blog_urls: 장소명으로 관련 블로그 URL 확보
    2) fetch_tags: 각 URL에서 태그 추출
    3) 수집된 태그를 후속 매칭 처리에 적합한 형태로 정제하여 반환
    """
    urls = search_blog_urls(place_name)
    all_tags: dict[str, int] = {}
    post_bar.reset(total=len(urls))
    post_bar.set_description(f'  포스트 fetch')
    for url in urls:
        tags = fetch_tags(url)
        for t in tags:
            all_tags[t] = all_tags.get(t, 0) + 1
        post_bar.update(1)
        time.sleep(PAGE_DELAY)  # 블로그 페이지 연속 요청 시 차단 방지를 위한 지연

    # 후속 매칭 처리에 사용할 형태로 정제
    sorted_tags = sorted(all_tags.items(), key=lambda x: -x[1])[:MAX_TAGS]
    return json.dumps({t: c for t, c in sorted_tags}, ensure_ascii=False)


def load_done_set() -> set[str]:
    if not os.path.exists(OUTPUT_CSV):
        return set()
    try:
        df = pd.read_csv(OUTPUT_CSV, encoding='utf-8-sig')
        return set(df['가게명'].tolist())
    except Exception:
        return set()


def main(test: bool = False):
    df = pd.read_csv(INPUT_CSV, encoding='utf-8-sig')

    # 1) 방문자수==0 AND 블로그수==0 제거
    before = len(df)
    df = df[~((df['방문자수'] == 0) & (df['블로그수'] == 0))].reset_index(drop=True)
    print(f'데이터 로드: {before}개 → 필터 후 {len(df)}개')

    # 2) 전체 대상 (사전 필터 없음 — 랭킹 알고리즘에서 자연 탈락)
    targets = df['가게명'].tolist()
    print(f'수집 대상: {len(targets)}개')

    if test:
        targets = targets[:5]
        print(f'[테스트 모드] 상위 5개만 수집: {targets}\n')

    # 3) 이미 처리된 장소 제외 (이어하기)
    done = load_done_set()
    remaining = [p for p in targets if p not in done]
    print(f'이미 완료: {len(done)}개 / 남은 작업: {len(remaining)}개\n')

    if not remaining:
        print('모든 장소 처리 완료.')
        return

    # 4) 처리 루프 — 진행도 바 2개 (장소 / 포스트)
    write_header = not os.path.exists(OUTPUT_CSV)
    place_bar = tqdm(total=len(remaining), desc='장소', unit='곳', position=0)
    post_bar  = tqdm(total=0, desc='  포스트 fetch', unit='개', position=1, leave=False)

    for place in remaining:
        place_bar.set_postfix_str(place[:20])
        tags_json = collect_place_tags(place, post_bar)

        top3 = list(json.loads(tags_json).keys())[:3]
        tqdm.write(f'  ✓ {place} → {top3}')

        row = pd.DataFrame([{'가게명': place, 'blog_tags': tags_json}])
        row.to_csv(
            OUTPUT_CSV,
            mode='a',
            header=write_header,
            index=False,
            encoding='utf-8-sig',
        )
        write_header = False

        place_bar.update(1)
        time.sleep(SEARCH_DELAY)

    post_bar.close()
    place_bar.close()
    print(f'\n완료. 결과 저장: {OUTPUT_CSV}')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='테스트 모드: 상위 5개 장소만 수집')
    args = parser.parse_args()
    main(test=args.test)
