import os, json, logging, sqlite3, time, re, math
from datetime import datetime
import anthropic
import pandas as pd
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from recommendation_ai import (add_scores, greedy_tsp, search_courses, fixed_categories,
                               SLOT_CATEGORY_MAP, FOOD_CATS, route_metrics, distances_from)
from place_identity import quarantine_legacy

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
    return quarantine_legacy(df).drop_duplicates('place_id')

# ── Claude 클라이언트 ─────────────────────────────────────────
_claude = None
MODEL   = 'claude-haiku-4-5-20251001'

# spot 모드: 텍스트에서 장소 종류(카테고리)만 추출
SPOT_CATEGORY_SYSTEM = """\
사용자 입력에서 찾고 싶은 장소 종류만 JSON으로 반환하세요.

[category_filters 규칙]
- 사용자가 명시한 장소 종류만 포함. 상위/유사 카테고리 추가 금지.
- 예) "닭갈비" → ["닭갈비"]  ← "고기", "한식" 추가 금지
- 예) "카페" → ["카페"]  ← "음식점", "디저트" 추가 금지
- 부정·제외 표현의 제외 대상은 포함하지 마세요. "닭갈비 말고 카페" → ["카페"]
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



# 선택된 페르소나 태그 조합 → 블로그 해시태그 스타일 키워드 생성
TAG_BLOG_SYSTEM = """\
사용자가 선택한 여행 태그 조합을 보고, 네이버 블로그 게시물에 실제로 붙는 해시태그 스타일 키워드를 생성하세요.

[규칙]
- 반드시 1~3단어 이내 짧은 단어/구문만 생성. 긴 문장 금지.
- 태그 조합의 맥락을 반영하세요. 예) "연인과 + 로맨틱한 + 카페 투어" → 데이트 감성 키워드
- 지역명·계절은 단독 단어로만 포함 (예: "아산", "봄"). 복합어 금지 (예: "아산 봄 등산" X)
- 실제 블로그 태그에 등장할 법한 단어 위주로. 8~15개 생성.
- 예) "연인과, 로맨틱한, 카페 투어, 아산, 봄" → ["데이트", "커플", "로맨틱카페", "분위기카페", "봄나들이", "아산", "봄"]
- 예) "가족 나들이, 아이와 함께, 자연/산책, 천안, 여름" → ["가족나들이", "아이와", "자연", "나들이", "여름", "천안"]
- 예) "혼자, 힐링/여유, 등산/트레킹, 아산" → ["혼산", "힐링", "등산", "트레킹", "아산"]
- 태그가 없으면 빈 배열

JSON만 반환. 형식: {"blog_tag_keywords": [...]}"""


def _call_claude(system: str, user_msg: str, max_tokens: int = 512, max_retries: int = 3) -> dict:
    global _claude
    if _claude is None:
        key = os.getenv('ANTHROPIC_API_KEY')
        if not key:
            raise RuntimeError('ANTHROPIC_API_KEY가 없어 언어 해석을 사용할 수 없습니다.')
        _claude = anthropic.Anthropic(api_key=key)
    delay = 0.8
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
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
        except Exception as e:
            last_exc = e
            if attempt < max_retries - 1:
                log.warning(f"Claude 호출 실패 (시도 {attempt + 1}/{max_retries}): {e}")
                time.sleep(delay)
                delay *= 2
    raise last_exc  # type: ignore[misc]


def _string_list(value, field):
    if not isinstance(value, list) or len(value) > 50 or any(not isinstance(v, str) or not v.strip() or len(v) > 100 for v in value):
        raise ValueError(f'{field}는 비어 있지 않은 문자열의 배열이어야 합니다.')
    return list(dict.fromkeys(v.strip() for v in value))


def extract_spot_category(user_text):
    # Preserve known explicit terms offline, even when the LLM is unavailable.
    known = set(_FOOD_CAFE_CATS) | {c for cats in SLOT_CATEGORY_MAP.values() for c in cats}
    found = [c for c in sorted(known) if c in user_text and
             (c != '산' or re.search(r'(?:^|\s)산(?:$|\s)', user_text))]
    found = [c for c in found if not any(c != other and c in other for other in found)]
    if any(c in FOOD_CATS and c not in ('음식점', '식당') for c in found):
        found = [c for c in found if c not in ('음식점', '식당')]
    if found and not re.search(r'말고|제외|빼고|아닌|아니고|않', user_text):
        return found
    result = _call_claude(SPOT_CATEGORY_SYSTEM, f'입력: "{user_text}"')
    return _string_list(result.get('category_filters', []), 'category_filters')


def get_season() -> str:
    month = datetime.now().month
    if month in (3, 4, 5):  return '봄'
    if month in (6, 7, 8):  return '여름'
    if month in (9, 10, 11): return '가을'
    return '겨울'


def expand_persona_tags(persona_tags: list, region: str = '', season: str = '') -> list:
    if not persona_tags:
        return []
    tags_str = ', '.join(persona_tags)
    msg = f'선택된 태그: {tags_str}'
    if region and region != '내 주변':
        msg += f', 지역: {region}'
    if season:
        msg += f', 계절: {season}'
    try:
        result = _call_claude(TAG_BLOG_SYSTEM, msg)
        return _string_list(result.get('blog_tag_keywords', []), 'blog_tag_keywords')
    except Exception:
        return list(persona_tags)


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
    '쇼핑':           ['시장', '쇼핑', '백화점', '아울렛'],
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
# 이동 수단별 차등 반경. 대중교통은 도보·환승 부담을 고려해 좁게,
# 승용차는 자유로운 이동을 반영해 넓게 설정.
RADIUS_KM = {'차': 15.0, '대중교통': 4.5}

# ── 서비스 영역 경계 (천안·아산 포함 충남 지역) ──────────────────
_SERVICE_LAT = (36.55, 37.05)
_SERVICE_LNG = (126.80, 127.35)

def _in_service_area(lat: float, lng: float) -> bool:
    return (_SERVICE_LAT[0] <= lat <= _SERVICE_LAT[1] and
            _SERVICE_LNG[0] <= lng <= _SERVICE_LNG[1])


def filter_radius(df, lat, lng, transport):
    result = df.copy()
    for col in ('latitude', 'longitude'):
        result[col] = pd.to_numeric(result[col], errors='coerce')
    result = result[result['latitude'].between(-90, 90) & result['longitude'].between(-180, 180)]
    distances = distances_from((lat, lng), result[['latitude', 'longitude']].values)
    result['origin_distance_km'] = distances
    return result[distances <= RADIUS_KM[transport]].copy()


def category_matches(category, filters):
    value = str(category or '').lower()
    tokens = re.split(r'[,>/\s]+', value)
    for term in filters:
        term = term.lower()
        if term == '산':
            if '산' in tokens:
                return True
        elif term == '카페' and '키즈카페' in value:
            continue
        elif term in value:
            return True
    return False


def filter_keywords(df, category_filters, blog_tag_keywords):
    """Hard category constraints only; preferences are handled by add_scores.

    Actual category wins over the crawler search term. Search terms are used only
    when the actual category is missing. Literal matching avoids regex injection.
    """
    if not category_filters:
        return df.copy()
    category = df.get('카테고리', pd.Series('', index=df.index)).fillna('')
    fallback = df.get('search_category', pd.Series('', index=df.index)).fillna('')
    effective = category.where(category.str.strip().ne(''), fallback)
    return df[effective.map(lambda c: category_matches(c, category_filters)).astype(bool)].copy()


# ── 응답 포맷 ─────────────────────────────────────────────────
def _fmt(record: dict) -> dict:
    return {
        'place_id': record['place_id'],
        'identity_key': record['identity_key'],
        'name':     record['가게명'],
        'lat':      record['latitude'],
        'lng':      record['longitude'],
        'address':  record['주소'],
        'category': record['카테고리'],
        'score':    round(float(record.get('score', 0)), 3),
        'blog_tag_status': record.get('blog_tag_status', 'legacy_unverified'),
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
def _parse_request(course=False):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError('JSON 객체를 보내주세요.')
    for field in ('user_lat', 'user_lng'):
        value = data.get(field)
        if isinstance(value, bool):
            raise ValueError(f'{field}는 유효한 좌표여야 합니다.')
        try:
            data[field] = float(value)
        except (TypeError, ValueError):
            raise ValueError(f'{field}는 유효한 좌표여야 합니다.') from None
        if not math.isfinite(data[field]):
            raise ValueError(f'{field}는 유효한 좌표여야 합니다.')
    if not -90 <= data['user_lat'] <= 90 or not -180 <= data['user_lng'] <= 180:
        raise ValueError('좌표 범위를 확인해주세요.')
    data.setdefault('transport', '대중교통')
    if not isinstance(data['transport'], str) or data['transport'] not in RADIUS_KM:
        raise ValueError('transport는 차 또는 대중교통이어야 합니다.')
    data.setdefault('region', '')
    if not isinstance(data['region'], str) or data['region'] not in ('', '내 주변', '천안', '아산'):
        raise ValueError('region은 천안, 아산 또는 내 주변이어야 합니다.')
    data['persona_tags'] = _string_list(data.get('persona_tags', []), 'persona_tags')
    def integer(field, default, lo, hi):
        value = data.get(field, default)
        if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
            raise ValueError(f'{field}는 {lo}~{hi} 정수여야 합니다.')
        data[field] = value
    integer('count', 3 if course else 5, 1, 5 if course else 20)
    integer('seed', 0, 0, 2147483647)
    if course:
        slots = data.get('slot_types', [])
        if not isinstance(slots, list) or any(s not in SLOT_CATEGORY_MAP for s in slots if isinstance(s, str)) or any(not isinstance(s, str) for s in slots):
            raise ValueError('slot_types에 알 수 없는 슬롯이 있습니다.')
        data['slot_types'] = slots
        integer('spot_count', len(slots) if slots else 3, 3, 5)
        if slots and len(slots) != data['spot_count']:
            raise ValueError('slot_types 길이와 spot_count가 일치해야 합니다.')
    else:
        data.setdefault('user_text', '')
        if not isinstance(data['user_text'], str) or len(data['user_text']) > 1000:
            raise ValueError('user_text는 1000자 이내 문자열이어야 합니다.')
    return data


def _area_error(data):
    return not _in_service_area(data['user_lat'], data['user_lng'])


@app.route('/recommend/spot', methods=['POST'])
def recommend_spot():
    try:
        data = _parse_request()
    except ValueError as e:
        return jsonify(error=str(e), reason='invalid_request'), 400
    if _area_error(data):
        return jsonify(error='서비스 지역(천안·아산)을 벗어난 위치입니다.', reason='outside_service_area'), 422
    try:
        explicit = extract_spot_category(data['user_text']) if data['user_text'].strip() else []
    except Exception:
        log.exception('명시 카테고리 해석 실패')
        return jsonify(error='장소 종류를 해석하지 못했습니다. 구체적인 종류로 다시 입력해주세요.', reason='category_unavailable'), 503
    try:
        # Explicit kinds always take precedence over persona category hints.
        cats = explicit or derive_category_from_tags(data['persona_tags'])
        tags = expand_persona_tags(data['persona_tags'], data['region'], get_season())
        df = filter_radius(get_df(data['region']), data['user_lat'], data['user_lng'], data['transport'])
        if not cats and not any(t in _FOOD_CAFE_TAGS for t in data['persona_tags']):
            df = df[~df['카테고리'].map(lambda c: category_matches(c, _FOOD_CAFE_CATS)).astype(bool)]
        df = add_scores(filter_keywords(df, cats, []), tags)
        top = df.sort_values(['score', 'origin_distance_km', 'place_id'], ascending=[False, True, True]).head(data['count']).to_dict('records')
        route = greedy_tsp(top, (data['user_lat'], data['user_lng']))
        metadata = dict(requested_count=data['count'], returned_count=len(route),
                        category_filters=cats, constraints_relaxed=[],
                        reason=None if len(route) == data['count'] else 'insufficient_candidates')
        if not route:
            return jsonify(error='조건에 맞는 장소가 없습니다.', places=[], metadata=metadata), 422
        return jsonify(places=[_fmt(p) for p in route], metadata=metadata), 200
    except Exception:
        log.exception('[spot] 오류')
        return jsonify(error='추천 처리 중 오류가 발생했습니다.', reason='internal_error'), 500


@app.route('/recommend/course', methods=['POST'])
def recommend_course():
    try:
        data = _parse_request(course=True)
    except ValueError as e:
        return jsonify(error=str(e), reason='invalid_request'), 400
    if _area_error(data):
        return jsonify(error='서비스 지역(천안·아산)을 벗어난 위치입니다.', reason='outside_service_area'), 422
    try:
        tags = expand_persona_tags(data['persona_tags'], data['region'], get_season())
        df = filter_radius(get_df(data['region']), data['user_lat'], data['user_lng'], data['transport'])
        cats = ([SLOT_CATEGORY_MAP[s] for s in data['slot_types']] if data['slot_types']
                else fixed_categories(data['spot_count']))
        start = (data['user_lat'], data['user_lng'])
        courses, metadata = search_courses(df, cats, tags, filter_keywords, data['count'],
                                           start, data['transport'], data['seed'])
        metadata.update(requested_count=data['count'], returned_count=len(courses),
                        slot_types=data['slot_types'], radius_km=RADIUS_KM[data['transport']],
                        distance_method='coordinate_great_circle',
                        limitation='좌표 기반 직선거리 추정입니다. 도로·대중교통 경로시간과 영업시간은 확인되지 않았습니다.')
        metrics = [route_metrics(c, start) for c in courses]
        if not courses:
            return jsonify(error='슬롯 조건을 유지하는 코스를 구성할 장소가 부족합니다.',
                           courses=[], course_metrics=[], metadata=metadata), 422
        return jsonify(courses=[[_fmt(p) for p in c] for c in courses],
                       course_metrics=metrics, metadata=metadata), 200
    except Exception:
        log.exception('[course] 오류')
        return jsonify(error='추천 처리 중 오류가 발생했습니다.', reason='internal_error'), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
