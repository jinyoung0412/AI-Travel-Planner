import os, json, logging, sqlite3
import anthropic
import pandas as pd
from flask import Flask, request, jsonify
from geopy.distance import geodesic
from dotenv import load_dotenv

from recommendation_ai import add_scores, greedy_tsp, generate_fixed_courses
from clustering_ai import perform_clustering

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

# ── 데이터베이스 ──────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), 'places.db')


def get_df(region: str = '') -> pd.DataFrame:
    """SQLite에서 장소 데이터 조회. 지역 지정 시 해당 지역만 반환."""
    conn = sqlite3.connect(DB_PATH)
    if region and region != '내 주변':
        df = pd.read_sql('SELECT * FROM places WHERE 지역 = ?', conn, params=(region,))
    else:
        df = pd.read_sql('SELECT * FROM places', conn)
    conn.close()
    log.info(f"DB 조회: 지역={region or '전체'}, {len(df)}개")
    return df

# ── Claude 클라이언트 ─────────────────────────────────────────
_claude = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
MODEL   = 'claude-haiku-4-5-20251001'

# spot 모드: 텍스트에서 장소 종류(카테고리)만 추출
SPOT_CATEGORY_SYSTEM = """\
사용자 입력에서 찾고 싶은 장소 종류만 JSON으로 반환하세요.

[category_filters 규칙]
- 사용자가 명시한 장소 종류만 포함. 상위/유사 카테고리 추가 금지.
- 예) "닭갈비" → ["닭갈비"]  ← "고기", "한식" 추가 금지
- 예) "카페" → ["카페"]  ← "음식점", "디저트" 추가 금지
- 장소를 명시하지 않은 경우 빈 배열 []

JSON만 반환. 다른 텍스트 금지.
형식: {"category_filters": [...]}"""

# 텍스트 → 어울리는 페르소나 태그 자동 제안 (UI 자동 선택용)
TAG_SUGGEST_SYSTEM = """\
사용자 입력을 보고 어울리는 태그를 아래 목록에서 선택해 JSON으로 반환하세요.
반드시 아래 목록에 있는 태그 문자열 그대로만 사용하세요.

[누구와]
혼자, 친구와, 연인과, 부부끼리, 가족 나들이, 부모님 모시고, 아이와 함께, 유아/영아 동반,
단체/모임, 동아리/클럽, 회식, 소개팅/첫만남

[어떤 분위기]
힐링/여유, 활동적인, 감성적인, 로맨틱한, 조용한, 트렌디한, 고급스러운, 아늑한,
이색적인, 자연 친화적, 소소한 일상, 설레는, 멋진 야경

[특별한 날]
기념일, 생일, 졸업·입학 기념, 프로포즈, 첫 데이트, 오랜만에 만남, 일상 탈출

[실내·야외]
실내 위주, 야외 위주

[어떤 활동]
맛집 탐방, 카페 투어, 문화·역사 탐방, 박물관/전시, 쇼핑, 자연/산책, 등산/트레킹,
사진 명소, 야경, 스포츠/레저, 체험 공방, 전통/한옥, 노래방/실내 오락

관련 있는 태그만 선택. 목록 밖 단어 절대 금지.
JSON만 반환. 형식: {"tags": [...]}"""

# 선택된 페르소나 태그 → 블로그 검색 키워드 확장
TAG_BLOG_SYSTEM = """\
사용자가 선택한 여행 태그를 네이버 블로그 검색에 쓸 실제 키워드로 확장해 JSON으로 반환하세요.

[규칙]
- 태그의 의미를 블로그에 실제 쓰이는 짧은 단어로 확장. 중복 제거.
- 여러 태그가 비슷한 키워드를 공유하면 합쳐서 반환.
- 예) "연인과", "로맨틱한", "첫 데이트", "프로포즈" → ["연인", "데이트", "커플", "로맨틱"]
- 예) "부모님 모시고" → ["부모님", "효도"]
- 예) "아이와 함께", "유아/영아 동반", "아이 친화적" → ["아이", "키즈", "어린이", "유아"]
- 예) "힐링/여유", "조용한", "자연 친화적" → ["힐링", "여유", "자연", "힐링여행"]
- 예) "회식", "단체/모임", "동아리/클럽" → ["회식", "단체", "모임"]
- 예) "감성적인", "트렌디한" → ["감성", "인스타", "핫플", "트렌디"]
- 예) "사진 명소" → ["관광명소", "포토스팟", "인생샷", "전망", "뷰"]
- 예) "고급스러운" → ["고급", "파인다이닝", "럭셔리"]
- 예) "전통/한옥", "문화·역사 탐방" → ["전통", "한옥", "역사", "문화재"]
- 예) "등산/트레킹" → ["등산", "트레킹", "산행", "계곡"]
- 예) "스포츠/레저" → ["스포츠", "레저", "액티비티", "수영", "클라이밍"]
- 예) "멋진 야경" → ["야경", "야간", "밤 풍경", "야경 명소"]
- 예) "소개팅/첫만남" → ["소개팅", "첫만남", "데이트"]
- 예) "졸업·입학 기념", "기념일", "생일" → ["기념일", "생일", "축하", "특별한날"]
- 태그가 없으면 빈 배열

JSON만 반환. 형식: {"blog_tag_keywords": [...]}"""


def _call_claude(system: str, user_msg: str, max_tokens: int = 512) -> dict:
    resp = _claude.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = resp.content[0].text.strip()
    if '```' in text:
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
    return json.loads(text.strip())


def extract_spot_category(user_text: str) -> list:
    result = _call_claude(SPOT_CATEGORY_SYSTEM, f'입력: "{user_text}"')
    return result.get('category_filters', [])


def expand_persona_tags(persona_tags: list) -> list:
    if not persona_tags:
        return []
    tags_str = ', '.join(f'"{t}"' for t in persona_tags)
    result = _call_claude(TAG_BLOG_SYSTEM, f'선택된 태그: [{tags_str}]')
    return result.get('blog_tag_keywords', [])


# ── 음식점·카페 카테고리 (명시 선택 없으면 제외 대상) ────────────
_FOOD_CAFE_CATS = [
    '한식', '중식', '일식', '양식', '고기', '닭갈비', '해산물',
    '국밥', '음식점', '식당', '술집', '호프', '카페', '베이커리',
    '분식', '피자', '파스타', '뷔페', '치킨', '햄버거', '패스트푸드',
    '커피', '디저트', '아이스크림', '주스', '차(음료)', '바(Bar)',
    '포차', '막걸리', '해물', '족발', '삼겹살', '샐러드', '도시락',
]
_FOOD_CAFE_TAGS = {'맛집 탐방', '카페 투어'}

# ── 활동 태그 → 카테고리 필터 매핑 ──────────────────────────────
_TAG_CATEGORY_MAP = {
    '맛집 탐방':      ['한식', '중식', '일식', '양식', '고기', '닭갈비', '해산물', '국밥', '음식점', '식당'],
    '카페 투어':      ['카페', '베이커리'],
    '박물관/전시':    ['박물관', '미술관', '전시'],
    '문화·역사 탐방': ['문화재', '유적', '기념관', '역사'],
    '쇼핑':           ['시장', '쇼핑'],
    '자연/산책':      ['공원', '산책로', '수목원', '산', '계곡', '호수', '자연', '생태'],
    '등산/트레킹':    ['산', '등산', '트레킹', '계곡'],
    '사진 명소':      [
        '미술관', '박물관', '전시관', '전시',
        '국가유산', '문화재', '기념관', '기념물',
        '테마공원', '수목원', '식물원', '정원',
        '복합문화', '광장', '도보코스', '산책로',
        '산', '저수지', '하천', '자연공원', '생태공원',
    ],
    '멋진 야경':      [
        '공원', '테마공원', '광장', '저수지', '하천',
        '자연공원', '도보코스', '박물관', '미술관',
    ],
    '스포츠/레저':    ['스포츠', '레저', '수영', '볼링', '클라이밍', '체육', '경기장', '골프', '테니스'],
    '체험 공방':      ['체험', '공방'],
    '전통/한옥':      ['한옥', '전통', '문화재'],
    '노래방/실내 오락': ['노래방', '볼링', '오락'],
}


def derive_category_from_tags(persona_tags: list) -> list:
    """텍스트 카테고리가 없을 때 페르소나 태그에서 카테고리 힌트 추출."""
    cats = []
    for tag in persona_tags:
        cats.extend(_TAG_CATEGORY_MAP.get(tag, []))
    return list(dict.fromkeys(cats))  # 중복 제거, 순서 유지


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
    if category_filters:
        pat = '|'.join(category_filters)
        cat_mask = (
            df['카테고리'].str.contains(pat, case=False, na=False) |
            df['search_category'].str.contains(pat, case=False, na=False)
        )
    else:
        cat_mask = pd.Series(True, index=df.index)

    if blog_tag_keywords:
        tag_mask = df['blog_tags'].apply(lambda x: _tag_has_any(x, blog_tag_keywords))
    else:
        tag_mask = pd.Series(True, index=df.index)

    result = df[cat_mask & tag_mask]
    if len(result) < 3 and blog_tag_keywords:
        result = df[cat_mask]
    return result.copy()


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
# POST /suggest/tags — 텍스트 → 페르소나 태그 자동 제안
# ─────────────────────────────────────────────────────────────
@app.route('/suggest/tags', methods=['POST'])
def suggest_tags():
    try:
        data      = request.get_json()
        user_text = data.get('user_text', '').strip()
        if not user_text:
            return jsonify({'tags': []}), 200
        result = _call_claude(TAG_SUGGEST_SYSTEM, f'입력: "{user_text}"')
        return jsonify({'tags': result.get('tags', [])}), 200
    except Exception:
        log.exception('[tags] 오류')
        return jsonify({'tags': []}), 200  # 실패해도 빈 태그로 무시


# ─────────────────────────────────────────────────────────────
# POST /recommend/spot — 지금 당장 뭘 할지 (상위 5곳)
# ─────────────────────────────────────────────────────────────
@app.route('/recommend/spot', methods=['POST'])
def recommend_spot():
    try:
        data         = request.get_json()
        user_text    = data.get('user_text', '')
        transport    = data.get('transport', '대중교통')
        region       = data.get('region', '')
        user_lat     = float(data['user_lat'])
        user_lng     = float(data['user_lng'])
        persona_tags = data.get('persona_tags', [])
        count        = max(1, min(int(data.get('count', 5)), 20))

        log.info(f"[spot] region={region} | text={user_text!r} | tags={persona_tags} | count={count}")

        # Claude 호출 #1: 텍스트 → 카테고리 필터
        cat_f = extract_spot_category(user_text) if user_text else []
        # 텍스트 카테고리 없으면 페르소나 태그에서 카테고리 힌트 추출
        if not cat_f:
            cat_f = derive_category_from_tags(persona_tags)
        # Claude 호출 #2: 선택 페르소나 태그 → 블로그 검색 키워드
        tag_f = expand_persona_tags(persona_tags)

        log.info(f"[spot] cat={cat_f} | blog_kw={tag_f}")

        df = filter_radius(get_df(region), user_lat, user_lng, transport)

        # 맛집/카페 태그 미선택 + 텍스트에도 음식 카테고리 없으면 → 음식점·카페 제외
        food_cafe_selected = any(t in _FOOD_CAFE_TAGS for t in persona_tags)
        food_in_cat_f = any(c in set(_FOOD_CAFE_CATS) for c in cat_f)
        if not food_cafe_selected and not food_in_cat_f:
            excl_pat = '|'.join(_FOOD_CAFE_CATS)
            df = df[~(
                df['카테고리'].str.contains(excl_pat, case=False, na=False) |
                df['search_category'].str.contains(excl_pat, case=False, na=False)
            )]

        df = filter_keywords(df, cat_f, tag_f)
        df = add_scores(df, tag_f)

        if df.empty:
            return jsonify({'error': '조건에 맞는 장소가 없습니다.'}), 404

        top_n = df.nlargest(count, 'score').to_dict('records')
        route = greedy_tsp(top_n, (user_lat, user_lng))

        return jsonify({'places': [_fmt(p) for p in route]}), 200

    except Exception as e:
        log.exception('[spot] 오류')
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────
# POST /recommend/course — 오늘 뭘 할지 (5-stop 코스 × 3개)
# ─────────────────────────────────────────────────────────────
@app.route('/recommend/course', methods=['POST'])
def recommend_course():
    try:
        data         = request.get_json()
        transport    = data.get('transport', '대중교통')
        region       = data.get('region', '')
        user_lat     = float(data['user_lat'])
        user_lng     = float(data['user_lng'])
        persona_tags = data.get('persona_tags', [])
        count        = max(1, min(int(data.get('count', 3)), 5))

        log.info(f"[course] region={region} | tags={persona_tags} | count={count}")

        # Claude 호출: 선택 페르소나 태그 → 블로그 검색 키워드
        tag_f = expand_persona_tags(persona_tags)
        log.info(f"[course] blog_kw={tag_f}")

        radius_df = filter_radius(get_df(region), user_lat, user_lng, transport)
        if len(radius_df) < 5:
            return jsonify({'error': '반경 내 장소가 너무 적습니다.'}), 404

        clustered_df = perform_clustering(radius_df, transport)
        courses = generate_fixed_courses(clustered_df, tag_f, filter_keywords, n=count)

        if not courses:
            return jsonify({'error': '코스를 구성할 장소가 부족합니다.'}), 404

        return jsonify({'courses': [[_fmt(p) for p in course] for course in courses]}), 200

    except Exception as e:
        log.exception('[course] 오류')
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
