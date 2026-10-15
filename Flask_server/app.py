import os
import logging
import sqlite3
import re
from contextlib import closing
from pathlib import Path
from datetime import datetime
import pandas as pd
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from werkzeug.exceptions import HTTPException

from api_request import (CategoryRequired, json_object, user_text, parse_recommendation,
                         string_list as _string_list)

from recommendation_ai import (add_scores, greedy_tsp, search_courses, fixed_categories,
                               SLOT_CATEGORY_MAP, FOOD_CATS, RADIUS_KM, route_metrics, distances_from)
from place_identity import quarantine_legacy

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from runtime_llm import (call_claude as _call_claude, SPOT_CATEGORY_SYSTEM,
                         TAG_SUGGEST_SYSTEM, TAG_BLOG_SYSTEM, PERSONA_TAGS as _ALLOWED_TAGS)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

DB_PATH = os.getenv('PLACES_DB_PATH', str(Path(__file__).with_name('places.db')))


def get_df(region: str = '') -> pd.DataFrame:
    """SQLite에서 장소 데이터 조회. 지역 지정 시 해당 지역만 반환."""
    with closing(sqlite3.connect(Path(DB_PATH).resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        if region and region != '내 주변':
            df = pd.read_sql('SELECT * FROM places WHERE 지역 = ?', conn, params=(region,))
        else:
            df = pd.read_sql('SELECT * FROM places', conn)
    log.info('DB 조회: 지역=%s, %s개', region or '전체', len(df))
    return quarantine_legacy(df).drop_duplicates('place_id')


def extract_spot_category(user_text):
    # Preserve known explicit terms offline, even when the LLM is unavailable.
    known = (set(_FOOD_CAFE_CATS) | {c for cats in SLOT_CATEGORY_MAP.values() for c in cats}
             | {c for cats in _TAG_CATEGORY_MAP.values() for c in cats})
    found = [c for c in sorted(known) if c in user_text and
             (c != '산' or re.search(r'(?:^|\s)산(?:$|\s)', user_text))]
    found = [c for c in found if not any(c != other and c in other for other in found)]
    if any(c in FOOD_CATS and c not in ('음식점', '식당') for c in found):
        found = [c for c in found if c not in ('음식점', '식당')]
    if found and not re.search(r'말고|제외|빼고|아닌|아니|않|싫|없이|없는|말아|대신|원치|안\s*(?:가|갈|좋|먹|원)|싶지', user_text):
        return found
    result = _call_claude(SPOT_CATEGORY_SYSTEM, f'입력: "{user_text}"')
    filters = _string_list(result.get('category_filters'), 'category_filters')
    if found and not filters:
        raise CategoryRequired('찾고 싶은 장소 종류를 구체적으로 입력해주세요.')
    return filters


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
        return _string_list(result.get('blog_tag_keywords'), 'blog_tag_keywords')
    except Exception:
        return list(persona_tags)


_FOOD_CAFE_CATS = [
    '한식', '중식', '일식', '양식', '고기', '닭갈비', '해산물',
    '국밥', '음식점', '식당', '술집', '호프', '카페', '베이커리',
    '분식', '피자', '파스타', '뷔페', '치킨', '햄버거', '패스트푸드',
    '커피', '디저트', '아이스크림', '주스', '차(음료)', '바(Bar)',
    '포차', '막걸리', '해물', '족발', '삼겹살', '샐러드', '도시락',
]

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
    return list(dict.fromkeys(cats))


# Coarse service guard, not an administrative boundary or road-reachability test.
_SERVICE_LAT = (36.55, 37.05)
_SERVICE_LNG = (126.80, 127.35)

def _in_service_area(lat: float, lng: float) -> bool:
    return (_SERVICE_LAT[0] <= lat <= _SERVICE_LAT[1] and
            _SERVICE_LNG[0] <= lng <= _SERVICE_LNG[1])


def filter_radius(df, lat, lng, transport):
    """Use the engine's shared radius: tighter for walking/transfers than car travel."""
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


@app.errorhandler(HTTPException)
def http_error(error):
    messages = {400: 'JSON 요청을 확인해주세요.', 404: '요청한 경로가 없습니다.',
                405: '지원하지 않는 요청 방식입니다.', 413: '요청 크기는 16KB 이하여야 합니다.'}
    return jsonify(error=messages.get(error.code, '요청을 처리하지 못했습니다.'),
                   reason='invalid_request'), error.code


@app.route('/suggest/tags', methods=['POST'])
def suggest_tags():
    try:
        text = user_text(json_object(request.get_json(silent=True)))
    except ValueError as exc:
        return jsonify(error=str(exc), reason='invalid_request'), 400
    if not text:
        return jsonify(tags=[]), 200
    try:
        result = _call_claude(TAG_SUGGEST_SYSTEM, f'입력: "{text}"')
        tags = _string_list(result.get('tags'), 'tags')
        return jsonify(tags=[tag for tag in tags if tag in _ALLOWED_TAGS]), 200
    except Exception:
        log.warning('태그 제안 서비스 사용 불가')
        return jsonify(tags=[], error='태그 제안을 사용할 수 없습니다.', reason='tags_unavailable'), 503


def _parse_request(course=False):
    return parse_recommendation(request.get_json(silent=True), course)


def _preference_keywords(df, data):
    # Expansion cannot affect scores without verified evidence in the candidate pool.
    verified = df.get('blog_tag_status', pd.Series('', index=df.index)).eq('verified')
    return (expand_persona_tags(data['persona_tags'], data['region'], get_season())
            if verified.any() else [])


def _preference_metadata(df, persona_tags):
    verified = df.get('blog_tag_status', pd.Series('', index=df.index)).eq('verified')
    count = int(verified.sum())
    return {'verified_tag_candidate_count': count,
            'preference_evidence': 'verified_tags_available' if count else 'unavailable',
            'preference_requested': bool(persona_tags),
            'preference_limitation': (None if count else
                '검증된 블로그 태그가 없어 취향 일치 근거가 없습니다. 카테고리·인기도·거리로 추천합니다.')}


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
        explicit = extract_spot_category(data['user_text']) if data['user_text'] else []
    except CategoryRequired as exc:
        return jsonify(error=str(exc), reason='category_required'), 422
    except Exception:
        log.warning('명시 카테고리 해석 서비스 사용 불가')
        return jsonify(error='장소 종류를 해석하지 못했습니다. 구체적인 종류로 다시 입력해주세요.', reason='category_unavailable'), 503
    try:
        # Explicit kinds always take precedence over persona category hints.
        cats = explicit or derive_category_from_tags(data['persona_tags'])
        df = filter_radius(get_df(data['region']), data['user_lat'], data['user_lng'], data['transport'])
        if not cats:
            df = df[~df['카테고리'].map(lambda c: category_matches(c, _FOOD_CAFE_CATS)).astype(bool)]
        df = filter_keywords(df, cats, [])
        tags = _preference_keywords(df, data)
        preference = _preference_metadata(df, data['persona_tags'])
        df = add_scores(df, tags)
        top = df.sort_values(['score', 'origin_distance_km', 'place_id'], ascending=[False, True, True]).head(data['count']).to_dict('records')
        route = greedy_tsp(top, (data['user_lat'], data['user_lng']))
        metadata = dict(requested_count=data['count'], returned_count=len(route),
                        category_filters=cats, constraints_relaxed=[], **preference,
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
        df = filter_radius(get_df(data['region']), data['user_lat'], data['user_lng'], data['transport'])
        cats = ([SLOT_CATEGORY_MAP[s] for s in data['slot_types']] if data['slot_types']
                else fixed_categories(data['spot_count']))
        candidates = filter_keywords(df, list(dict.fromkeys(c for slot in cats for c in slot)), [])
        tags = _preference_keywords(candidates, data)
        start = (data['user_lat'], data['user_lng'])
        courses, metadata = search_courses(df, cats, tags, filter_keywords, data['count'],
                                           start, data['transport'], data['seed'])
        metadata.update(**_preference_metadata(candidates, data['persona_tags']),
                        requested_count=data['count'], returned_count=len(courses),
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
    app.run(host=os.getenv('FLASK_HOST', '127.0.0.1'),
            port=int(os.getenv('FLASK_PORT', '5001')),
            debug=os.getenv('FLASK_DEBUG', '').lower() in ('1', 'true'))
