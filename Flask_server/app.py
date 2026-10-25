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
from place_identity import quarantine_legacy, local_aliases, alias_conflicts
from place_quality import (coordinate_quality, filter_coordinate_candidates,
                           display_name, display_address)
from category_policy import (category_matches, normalize_filters, ALIASES, NEGATION,
                             FOOD_BEVERAGE_CATS as _FOOD_CAFE_CATS, GENERIC_FOOD_TERMS,
                             concrete_food_terms, directly_excluded, landmark_suffix,
                             SPATIAL_RELATION)
from recommender.diversity import BRAND_SOURCE_NAMES, select_diverse_spots
from recommender.constants import INDOOR_ACTIVITY_CATS
from recommendation_review import filter_reviewed_candidates

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


def _known_categories():
    return (set(_FOOD_CAFE_CATS) | {c for cats in SLOT_CATEGORY_MAP.values() for c in cats}
             | {c for cats in _TAG_CATEGORY_MAP.values() for c in cats} | {'주택전시관'})


def _category_mentions(user_text):
    known = _known_categories()
    mentions = [(c, m.start(), m.end()) for c in sorted(known | ALIASES.keys())
                for m in re.finditer(re.escape(c), user_text)
                if not (c == '맥주' and re.match(r'\s*(?:박물관|전시|양조장|공장)', user_text[m.end():]))
                if c != '산' or (m.start() == 0 or user_text[m.start()-1].isspace())
                and (m.end() == len(user_text) or user_text[m.end()].isspace())]
    # Resolve overlaps per occurrence: a separate "카페" before "키즈카페"
    # must remain available for interpreting its own exclusion.
    return [(c, start, end) for c, start, end in mentions
            if not any(a <= start and end <= b and b-a > end-start for _, a, b in mentions)]


def _mentioned_categories(user_text):
    return list(dict.fromkeys(c for c, _, _ in _category_mentions(user_text)))


def excluded_categories(user_text):
    excluded = [c for c, _, end in _category_mentions(user_text)
                if directly_excluded(user_text[end:])]
    return normalize_filters(excluded, _known_categories())


def extract_spot_category(user_text):
    # Preserve known explicit terms offline, even when the LLM is unavailable.
    known = _known_categories()
    mentions = _category_mentions(user_text)
    found = list(dict.fromkeys(c for c, _, end in mentions
                               if not landmark_suffix(user_text[end:])))
    if found and not re.search(NEGATION, user_text):
        return normalize_filters(found, known)
    result = _call_claude(SPOT_CATEGORY_SYSTEM, f'입력: "{user_text}"')
    filters = _string_list(result.get('category_filters'), 'category_filters')
    if mentions and not filters:
        raise CategoryRequired('찾고 싶은 장소 종류를 구체적으로 입력해주세요.')
    banned = excluded_categories(user_text)
    concrete = concrete_food_terms([c for c in found if not category_matches(c, banned)])
    if concrete and any(c in GENERIC_FOOD_TERMS for c in filters):
        filters = [c for c in filters if c not in _FOOD_CAFE_CATS and c not in GENERIC_FOOD_TERMS] + concrete
    try:
        filters = normalize_filters(filters, known)
    except ValueError:
        raise CategoryRequired('해석된 장소 종류를 지원하지 않습니다. 구체적인 종류로 다시 입력해주세요.') from None
    # The model cannot reintroduce a directly negated category, even if its JSON
    # is well-formed. Ambiguous negation still requires the bounded model path.
    filters = [c for c in filters if not category_matches(c, banned)]
    if mentions and not filters:
        raise CategoryRequired('제외할 종류 외에 찾고 싶은 장소 종류를 입력해주세요.')
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
    '노래방/실내 오락': INDOOR_ACTIVITY_CATS,
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


def filter_keywords(df, category_filters, blog_tag_keywords):
    """Hard category constraints only; preferences are handled by add_scores.

    Actual category wins over the crawler search term. Search terms are used only
    when the actual category is missing. Literal matching avoids regex injection.
    """
    category = df.get('카테고리', pd.Series('', index=df.index)).fillna('')
    fallback = df.get('search_category', pd.Series('', index=df.index)).fillna('')
    effective = category.where(category.str.strip().ne(''), fallback)
    if not category_filters:
        return df[~effective.map(lambda c: category_matches(c, ['주택전시관'])).astype(bool)].copy()
    names = df.get('가게명', pd.Series('', index=df.index)).fillna('')
    matched = pd.Series([category_matches(c, category_filters, name)
                        for c, name in zip(effective, names)], index=df.index, dtype=bool)
    return df[matched].copy()


def filter_excluded_categories(df, excluded):
    if not excluded:
        return df
    matched = filter_keywords(df, excluded, [])
    return df.loc[~df.index.isin(matched.index)].copy()


def _fmt(record: dict) -> dict:
    return {
        'place_id': record['place_id'],
        'identity_key': record['identity_key'],
        'identity_aliases': sorted(local_aliases(record)),
        'identity_alias_conflicts': {alias: sorted(owners) for alias, owners in alias_conflicts(record).items()},
        'name':     display_name(record['가게명'], record['카테고리']),
        'lat':      record['latitude'],
        'lng':      record['longitude'],
        'address':  display_address(record['주소']),
        'source_name': record['가게명'],
        'source_address': record['주소'],
        'coordinate_quality': coordinate_quality(record),
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


def _preference_metadata(df, persona_tags, category_tags=()):
    verified = df.get('blog_tag_status', pd.Series('', index=df.index)).eq('verified')
    count = int(verified.sum())
    return {'verified_tag_candidate_count': count,
            'preference_evidence': 'verified_tags_available' if count else 'unavailable',
            'preference_requested': bool(persona_tags),
            'category_preference_tags_applied': list(category_tags),
            'preference_limitation': (None if count else
                (f'활동 태그({", ".join(category_tags)})는 장소 종류에 반영했습니다. ' if category_tags else '') +
                '검증된 블로그 태그가 없어 동행·분위기를 포함한 취향 일치 근거는 없습니다. '
                '장소 종류·인기도·거리로 추천합니다.')}


def _requested_brand_families(text):
    # A positive named-brand search may intentionally want multiple branches.
    # Negation or landmark searches are ambiguous and retain the variety policy.
    if re.search(NEGATION, text) or re.search(SPATIAL_RELATION, text):
        return []
    return [family for family in BRAND_SOURCE_NAMES
            if re.search(r'(?<![가-힣a-zA-Z0-9])' + re.escape(family), text)]


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
        excluded = excluded_categories(data['user_text'])
        df, identity_review = filter_reviewed_candidates(get_df(data['region']))
        df, quality = filter_coordinate_candidates(df)
        df = filter_radius(df, data['user_lat'], data['user_lng'], data['transport'])
        if not cats:
            df = df[~df['카테고리'].map(lambda c: category_matches(c, _FOOD_CAFE_CATS)).astype(bool)]
        df = filter_keywords(df, cats, [])
        df = filter_excluded_categories(df, excluded)
        tags = _preference_keywords(df, data)
        category_tags = ([tag for tag in data['persona_tags'] if tag in _TAG_CATEGORY_MAP]
                         if not explicit else [])
        preference = _preference_metadata(df, data['persona_tags'], category_tags)
        df = add_scores(df, tags)
        ranked = df.sort_values(['score', 'origin_distance_km', 'place_id'], ascending=[False, True, True])
        selected, diversity = select_diverse_spots(ranked, data['count'],
                                                  _requested_brand_families(data['user_text']))
        top = selected.to_dict('records')
        route = greedy_tsp(top, (data['user_lat'], data['user_lng']))
        metadata = dict(requested_count=data['count'], returned_count=len(route),
                        category_filters=cats, constraints_relaxed=[], **preference,
                        excluded_category_filters=excluded,
                        diversity=diversity,
                        candidate_quality=quality,
                        identity_review=identity_review,
                        spatial_relation_limitation=('주변 장소와의 거리는 적용하지 않았습니다. 출발 위치 반경 안에서 요청한 종류를 추천합니다.'
                            if re.search(SPATIAL_RELATION, data['user_text']) else None),
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
        df, identity_review = filter_reviewed_candidates(get_df(data['region']))
        df, quality = filter_coordinate_candidates(df)
        df = filter_radius(df, data['user_lat'], data['user_lng'], data['transport'])
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
                        candidate_quality=quality,
                        identity_review=identity_review,
                        limitation='좌표 기반 직선거리 추정입니다. 장소와 좌표의 실제 일치·도로·대중교통 경로시간·영업시간은 확인되지 않았습니다.')
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
