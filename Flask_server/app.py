import os, json, math, logging
import anthropic
import pandas as pd
from flask import Flask, request, jsonify
from geopy.distance import geodesic
from dotenv import load_dotenv

from clustering_ai import perform_clustering
from recommendation_ai import add_scores, greedy_tsp, select_course

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

# ── 데이터 로드 ───────────────────────────────────────────────
_ROOT         = os.path.join(os.path.dirname(__file__), '..')
PLACES_CSV    = os.path.join(_ROOT, 'Preprocess', 'data', 'processed', 'chungnam_places_filtered.csv')
BLOG_TAGS_CSV = os.path.join(_ROOT, 'Preprocess', 'data', 'processed', 'blog_tags.csv')

_places    = pd.read_csv(PLACES_CSV, encoding='utf-8-sig')
_blog_tags = pd.read_csv(BLOG_TAGS_CSV, encoding='utf-8-sig')[['가게명', 'blog_tags']]
df_all     = _places.merge(_blog_tags, on='가게명', how='left')
log.info(f"데이터 로드 완료: {len(df_all)}개 장소")

# ── Claude 클라이언트 ─────────────────────────────────────────
_claude = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
MODEL   = 'claude-haiku-4-5-20251001'

SPOT_SYSTEM = """\
사용자 입력을 분석해 장소 검색 키워드를 JSON으로 반환하세요.

category_filters: 카카오맵 카테고리·검색어에 포함될 단어 (예: 육류, 고기, 카페, 공원, 술집, 호프, 이자카야)
blog_tag_keywords: 사회적 맥락·분위기 키워드 (예: 부모님, 가족, 데이트, 연인, 회식, 혼자, 아이)

JSON만 반환. 다른 텍스트 금지.
형식: {"category_filters": [...], "blog_tag_keywords": [...]}"""

COURSE_SYSTEM = """\
사용자 입력을 분석해 하루 코스 3곳을 설계하고 JSON으로 반환하세요.
각 stop은 서로 다른 카테고리여야 합니다 (음식점 + 카페 + 자연/문화 등).

JSON만 반환. 다른 텍스트 금지.
형식: {"stops": [{"category_filters": [...], "blog_tag_keywords": [...]}, ...]}"""


def _call_claude(system: str, user_msg: str) -> dict:
    resp = _claude.messages.create(
        model=MODEL,
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = resp.content[0].text.strip()
    if '```' in text:
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
    return json.loads(text.strip())


def extract_spot_keywords(user_text: str) -> dict:
    return _call_claude(SPOT_SYSTEM, f'입력: "{user_text}"')


def extract_course_plan(user_text: str) -> dict:
    return _call_claude(COURSE_SYSTEM, f'입력: "{user_text}"')


# ── 반경 필터 ─────────────────────────────────────────────────
RADIUS_KM = {'차': 15.0, '대중교통': 5.0}


def filter_radius(df: pd.DataFrame, lat: float, lng: float, transport: str) -> pd.DataFrame:
    r = RADIUS_KM.get(transport, 5.0)
    mask = df.apply(
        lambda row: geodesic((lat, lng), (row['latitude'], row['longitude'])).kilometers <= r,
        axis=1,
    )
    return df[mask].copy()


# ── 키워드 필터 ───────────────────────────────────────────────
def _tag_has_any(tags_json, keywords: list) -> bool:
    if pd.isna(tags_json):
        return False
    try:
        keys = ' '.join(json.loads(tags_json).keys())
        return any(kw in keys for kw in keywords)
    except Exception:
        return False


def filter_keywords(df: pd.DataFrame, category_filters: list, blog_tag_keywords: list) -> pd.DataFrame:
    # 카테고리 필터 (카테고리 + search_category 둘 다 검색)
    if category_filters:
        pat = '|'.join(category_filters)
        cat_mask = (
            df['카테고리'].str.contains(pat, case=False, na=False) |
            df['search_category'].str.contains(pat, case=False, na=False)
        )
    else:
        cat_mask = pd.Series(True, index=df.index)

    # 블로그 태그 키워드 필터
    if blog_tag_keywords:
        tag_mask = df['blog_tags'].apply(lambda x: _tag_has_any(x, blog_tag_keywords))
    else:
        tag_mask = pd.Series(True, index=df.index)

    result = df[cat_mask & tag_mask]
    # 결과 부족 시 블로그 태그 조건 완화
    if len(result) < 3 and blog_tag_keywords:
        result = df[cat_mask]
    return result.copy()


# ── 스코어링 ──────────────────────────────────────────────────
def add_scores(df: pd.DataFrame, blog_tag_keywords: list) -> pd.DataFrame:
    df = df.copy()

    # 인기도 정규화: log(방문자수 + 블로그수×0.3 + 1)
    raw = (df['방문자수'].fillna(0) + df['블로그수'].fillna(0) * 0.3 + 1).apply(math.log)
    mn, mx = raw.min(), raw.max()
    df['pop_score'] = ((raw - mn) / (mx - mn)).clip(0, 1) if mx > mn else 0.0

    # 블로그 태그 매칭 점수
    if blog_tag_keywords:
        def _match(tags_json):
            if pd.isna(tags_json):
                return 0.0
            try:
                keys = ' '.join(json.loads(tags_json).keys())
                return sum(1 for kw in blog_tag_keywords if kw in keys) / len(blog_tag_keywords)
            except Exception:
                return 0.0
        df['tag_score'] = df['blog_tags'].apply(_match)
    else:
        df['tag_score'] = 0.0

    df['score'] = 0.4 * df['pop_score'] + 0.6 * df['tag_score']
    return df


# ── Greedy TSP ────────────────────────────────────────────────
def greedy_tsp(records: list, start: tuple) -> list:
    route, current, remaining = [], start, list(records)
    while remaining:
        nearest = min(
            remaining,
            key=lambda p: geodesic(current, (p['latitude'], p['longitude'])).kilometers,
        )
        route.append(nearest)
        remaining.remove(nearest)
        current = (nearest['latitude'], nearest['longitude'])
    return route


# ── 응답 포맷 ─────────────────────────────────────────────────
def _fmt(record: dict) -> dict:
    return {
        'name':     record['가게명'],
        'lat':      record['latitude'],
        'lng':      record['longitude'],
        'address':  record['주소'],
        'category': record['카테고리'],
        'score':    round(float(record.get('score', 0)), 3),
    }


# ─────────────────────────────────────────────────────────────
# POST /recommend/spot — 지금 당장 뭘 할지 (상위 5곳)
# ─────────────────────────────────────────────────────────────
@app.route('/recommend/spot', methods=['POST'])
def recommend_spot():
    try:
        data      = request.get_json()
        user_text = data['user_text']
        transport = data.get('transport', '대중교통')
        user_lat  = float(data['user_lat'])
        user_lng  = float(data['user_lng'])

        log.info(f"[spot] {user_text}")

        kw    = extract_spot_keywords(user_text)
        cat_f = kw.get('category_filters', [])
        tag_f = kw.get('blog_tag_keywords', [])
        log.info(f"[spot] cat={cat_f} | tag={tag_f}")

        df = filter_radius(df_all, user_lat, user_lng, transport)
        df = filter_keywords(df, cat_f, tag_f)
        df = add_scores(df, tag_f)

        if df.empty:
            return jsonify({'error': '조건에 맞는 장소가 없습니다.'}), 404

        top5  = df.nlargest(5, 'score').to_dict('records')
        route = greedy_tsp(top5, (user_lat, user_lng))

        return jsonify({'places': [_fmt(p) for p in route]}), 200

    except Exception as e:
        log.exception(f"[spot] 오류")
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────
# POST /recommend/course — 오늘 뭘 할지 (3-stop 코스)
# ─────────────────────────────────────────────────────────────
@app.route('/recommend/course', methods=['POST'])
def recommend_course():
    try:
        data      = request.get_json()
        user_text = data['user_text']
        transport = data.get('transport', '대중교통')
        user_lat  = float(data['user_lat'])
        user_lng  = float(data['user_lng'])

        log.info(f"[course] {user_text}")

        plan  = extract_course_plan(user_text)
        stops = plan.get('stops', [])
        if len(stops) != 3:
            return jsonify({'error': f'Claude 응답 오류: stop 수={len(stops)}'}), 500
        log.info(f"[course] 코스 설계: {stops}")

        radius_df = filter_radius(df_all, user_lat, user_lng, transport)
        if len(radius_df) < 5:
            return jsonify({'error': '반경 내 장소가 너무 적습니다.'}), 404

        clustered    = perform_clustering(radius_df, transport=transport)
        best_selected = select_course(clustered, stops, filter_keywords)

        if not best_selected:
            return jsonify({'error': '코스를 구성할 장소가 부족합니다.'}), 404

        route = greedy_tsp(best_selected, (user_lat, user_lng))

        return jsonify({'course': [_fmt(p) for p in route]}), 200

    except Exception as e:
        log.exception(f"[course] 오류")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
