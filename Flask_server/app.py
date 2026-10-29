import os
import logging
import sqlite3
import re
import time
import hashlib
from contextlib import closing
from functools import partial
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
                             SPATIAL_RELATION, generic_food_modifier)
from recommender.diversity import BRAND_SOURCE_NAMES, select_diverse_spots
from recommender import spot_quality
from recommender.constants import (ACTIVITY_TAG_CATEGORIES, ACTIVITY_CATS,
                                   activity_tag_label, CORE_ACTIVITY_TAG_SLOTS)
from recommendation_review import filter_reviewed_candidates
from family_policy import filter_child_candidates, child_venue, children_allowed
import travel_intent as intent
from selection_wire import MAX_OUTPUT_TOKENS as SELECTION_OUTPUT_TOKENS
from intent_context import normalize_context, context_only, grounded_tags, source_preferences
from service_area import filter_service_candidates, candidate_city
from recommendation_context import build_context, apply_context, order_spots, context_cost, resolve_generic_meal_ambiguities

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
        return normalize_filters(found, known, text=user_text)
    result = _call_claude(SPOT_CATEGORY_SYSTEM, f'입력: "{user_text}"')
    filters = _string_list(result.get('category_filters'), 'category_filters')
    if mentions and not filters:
        raise CategoryRequired('찾고 싶은 장소 종류를 구체적으로 입력해주세요.')
    banned = excluded_categories(user_text)
    concrete = concrete_food_terms([c for c in found if not category_matches(c, banned)])
    if (concrete and not any(c in GENERIC_FOOD_TERMS for c in normalize_filters(found, known, text=user_text))
            and any(c in GENERIC_FOOD_TERMS for c in filters)):
        filters = [c for c in filters if c not in _FOOD_CAFE_CATS and c not in GENERIC_FOOD_TERMS] + concrete
    try:
        filters = normalize_filters(filters, known, text=user_text)
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


_TAG_CATEGORY_MAP = ACTIVITY_TAG_CATEGORIES


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
    # Explicit provenance proves this label was a search query, not a provider
    # category. Do not turn it back into factual purpose via the legacy fallback.
    source = df.get('category_source', pd.Series('', index=df.index)).fillna('')
    effective = effective.mask(source.eq('search_fallback'), '')
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
        return jsonify(tags=grounded_tags([t for t in tags if t in _ALLOWED_TAGS], text, directly_excluded)), 200
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
    category_labels = [activity_tag_label(tag) for tag in category_tags]
    return {'verified_tag_candidate_count': count,
            'preference_evidence': 'verified_tags_available' if count else 'unavailable',
            'preference_requested': bool(persona_tags),
            'category_preference_tags_applied': list(category_tags),
            'preference_limitation': (None if count else
                (f'활동 태그({", ".join(category_labels)})는 장소 종류에 반영했습니다. ' if category_tags else '') +
                '검증된 블로그 태그가 없어 동행·분위기를 포함한 취향 일치 근거는 없습니다. '
                '실내·야외 여부와 특별한 날 적합성도 확인하지 못했습니다. '
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


def _intent_error(exc, **extra):
    if exc.failure_code:
        extra['metadata'] = dict(failure_code=exc.failure_code)
    return jsonify(error=str(exc), reason=exc.reason, **extra), exc.status


def _interpret(data, mode):
    if not data['user_text']:
        raise intent.IntentError('intent_conflict', '원하는 여행을 문장으로 입력해주세요.')
    source_text = data['user_text']
    interpretation_text = source_text
    original = None
    choice = data.get('activity_choice')
    if choice:
        if mode == 'course' and data['plan_mode'] == 'manual':
            raise intent.IntentError('intent_conflict', '직접 구성에서는 방문 활동과 순서를 직접 선택해주세요.')
        original_data = {k: v for k, v in data.items() if k != 'activity_choice'}
        original = intent.read_plan(data.get('clarification_token', ''), original_data, mode,
                                    purpose='activity_clarification')
        if original['stages'] or original['unsupported'] or not original['ambiguities']:
            raise intent.IntentError('intent_conflict', '활동 선택 내용을 다시 확인해주세요.')
        if original.get('requested_visit_count') and original['requested_visit_count']['value'] != 1:
            raise intent.IntentError('intent_conflict', '여러 곳을 방문하려면 각 방문에서 원하는 활동과 순서를 문장에 적어주세요.')
        if context_only(source_text):
            # A validated button is already a structured activity selection.
            # Context-only dates need no second interpretation of its UI label.
            import copy
            plan = copy.deepcopy(original)
            excluded = {c for e in plan['exclusions'] for c in e['category_filters']}
            plan['stages'] = [dict(id='s1', activity=intent.CORE_ACTIVITY_LABELS[choice], quote=None,
                category_filters=[c for c in SLOT_CATEGORY_MAP[choice] if c not in excluded],
                conditions=[], preferences=source_preferences(source_text))]
            plan['ambiguities'] = []
            plan['source_text'] = source_text
            plan['activity_choice'] = choice
            plan['activity_choice_label'] = intent.CORE_ACTIVITY_LABELS[choice]
            return intent.apply_controls(plan, data, mode)
        interpretation_text += '\n추가로 직접 선택한 활동: ' + intent.CORE_ACTIVITY_LABELS[choice]
    elif data.get('clarification_token'):
        raise intent.IntentError('intent_conflict', '원하는 활동을 하나 선택해주세요.')
    try:
        system = intent.interpretation_system(_known_categories())
        payload = {'source_text': interpretation_text, 'region': data['region']}
        if choice:
            system += intent.CLARIFIED_ACTIVITY_SYSTEM
            payload['activity_choice'] = {'value': choice, 'label': intent.CORE_ACTIVITY_LABELS[choice],
                'visit_count': 1, 'category_filters_any_of': SLOT_CATEGORY_MAP[choice],
                'label_is_not_visit_sequence': True}
        raw = intent.bounded_model(_call_claude, system, payload, 7)
        plan = intent.validate_interpretation(raw, interpretation_text, _known_categories(),
                                              excluded_categories(source_text))
        plan = resolve_generic_meal_ambiguities(normalize_context(plan))
        if plan['stages']:
            _validate_literal_intent(plan, source_text)
        elif _positive_category_mentions(source_text):
            raise ValueError('intent_dropped_kind')
        if choice and plan['stages']:
            if len(plan['stages']) != 1 or not set(plan['stages'][0]['category_filters']).issubset(SLOT_CATEGORY_MAP[choice]):
                raise ValueError('intent_activity_choice')
            _validate_clarified_conditions(plan, source_text, original)
    except Exception as error:
        code = intent.interpretation_failure_code(error)
        log.warning('여행 문장 해석 실패 (%s)', code)
        action = ('문장을 다시 확인하거나 활동을 직접 선택해주세요.' if mode == 'spot' else
                  '문장을 다시 확인하거나 방문 활동과 순서를 직접 선택해주세요.')
        raise intent.IntentError('intent_unavailable', '여행 문장을 해석하지 못했어요. ' + action, 503,
                                 failure_code=code) from None
    plan['source_text'] = source_text
    if choice:
        if not plan['stages']:
            raise intent.IntentError('intent_conflict', '선택한 활동과 문장의 조건을 함께 확인해주세요.')
        plan['activity_choice'] = choice
        plan['activity_choice_label'] = intent.CORE_ACTIVITY_LABELS[choice]
    if not plan['stages']:
        if mode == 'spot' and context_only(source_text) and not plan['unsupported']:
            activities = [CORE_ACTIVITY_TAG_SLOTS[t] for t in data['persona_tags'] if t in CORE_ACTIVITY_TAG_SLOTS]
            if len(activities) == 1:
                activity = activities[0]
                plan['stages'] = [dict(id='s1', activity=intent.CORE_ACTIVITY_LABELS[activity], quote=None,
                    category_filters=SLOT_CATEGORY_MAP[activity], conditions=[], preferences=source_preferences(source_text))]
                plan['ambiguities'] = []
                return intent.apply_controls(plan, data, mode)
        if mode == 'course' and data['plan_mode'] == 'manual':
            if not data['slot_types']:
                raise intent.IntentError('intent_conflict', '방문할 활동과 순서를 직접 선택해주세요.')
            if context_only(source_text) and not plan['unsupported']:
                plan['ambiguities'] = []
                plan = intent.apply_controls(plan, data, mode)
                if not any(t in ('조용한', '로맨틱한', '힐링/여유', '활동적인') for t in data['persona_tags']):
                    for stage in plan['stages']:
                        stage['preferences'] = [dict(pref, id=f'{stage["id"]}.p{i+1}')
                            for i, pref in enumerate(source_preferences(source_text))]
                return plan
            # An unresolved hard sentence has not attached conditions to slots.
            raise intent.IntentError('intent_conflict', '문장의 조건에 맞는 활동을 방문 순서에 추가해주세요.')
        return intent.apply_controls(plan, data, 'spot')
    return intent.apply_controls(plan, data, mode)


def _validate_clarified_conditions(plan, text, original):
    """A selected activity must not erase the original companion or explicit indoor/mood request."""
    companion = original.get('companion')
    if companion and companion.get('source') != 'manual' and (
            not plan['companion'] or plan['companion']['value'] != companion['value']):
        raise ValueError('intent_dropped_companion')
    for word, field in (('실내', 'indoor'), ('야외', 'outdoor')):
        positive = any(not directly_excluded(text[m.end():]) and not landmark_suffix(text[m.end():])
                       for m in re.finditer(word, text))
        if positive and not any(c['field'] == field and c['value'] and
                (c['required'] or '가능하면' in text) for s in plan['stages'] for c in s['conditions']):
            raise ValueError('intent_dropped_condition')
    if re.search(r'조용(?:한|하게)', text) and not any(p['field'] == 'quiet'
            for s in plan['stages'] for p in s['preferences']):
        raise ValueError('intent_dropped_preference')


def _positive_category_mentions(text):
    return list(dict.fromkeys(c for c, _, end in _category_mentions(text)
        if not directly_excluded(text[end:]) and not landmark_suffix(text[end:])
        and not re.match(r'\s*보다', text[end:])))


def _validate_literal_intent(plan, text):
    """Reject dropped explicit kinds/conditions; this is not an intent parser.

    Qualified negatives and landmark relations remain with the model. These
    conservative guards only prevent a valid-looking plan losing literal hard
    requirements before its review screen is shown.
    """
    # An unrelated "nearby"/negative clause must not disable a positive yard
    # seating requirement elsewhere. A yard used only as a landmark or an
    # explicitly excluded alternative is still delegated to interpretation.
    positive_yard = any(
        not directly_excluded(text[m.end():])
        and not landmark_suffix(text[m.end():])
        and not re.match(r'\s*보다', text[m.end():])
        for m in re.finditer('야장', text))
    if positive_yard and not any(c['field'] == 'outdoor_seating' and c['value'] and c['required']
                                 for s in plan['stages'] for c in s['conditions']):
        raise ValueError('intent_dropped_outdoor')
    selected = {c for s in plan['stages'] for c in s['category_filters']}
    mentions = _positive_category_mentions(text)
    concrete = concrete_food_terms(mentions)
    for mention in mentions:
        if generic_food_modifier(mention, concrete, text):
            continue
        positive = set(normalize_filters([mention], _known_categories()))
        # A broad activity alias is OR: "식사" may become 한식 and "실내
        # 놀거리" may become 볼링. A concrete literal still must be retained.
        if (not positive.intersection(selected) if len(positive) > 1
                else not positive.issubset(selected)):
            raise ValueError('intent_dropped_kind')
    for stage in plan['stages']:
        scope = stage.get('quote') or (text if len(plan['stages']) == 1 else '')
        explicit = _positive_category_mentions(scope)
        if concrete_food_terms(explicit):
            allowed = set(normalize_filters(explicit, _known_categories(), text=scope))
            selected_food = set(stage['category_filters']).intersection(_FOOD_CAFE_CATS)
            if not selected_food.issubset(allowed):
                raise ValueError('intent_broadened_kind')
    positive_walk = any(not directly_excluded(text[m.end():]) and not landmark_suffix(text[m.end():])
                        and not re.match(r'\s*보다', text[m.end():]) for m in re.finditer('산책', text))
    if positive_walk and not any(set(s['category_filters']).intersection(SLOT_CATEGORY_MAP['자연·산책']) for s in plan['stages']):
        raise ValueError('intent_dropped_walk')


@app.route('/travel/interpret', methods=['POST'])
def interpret_travel():
    try:
        value = json_object(request.get_json(silent=True))
        mode = value.get('mode', 'spot')
        if mode not in ('spot', 'course') or value.get('intent_version') != 1:
            raise ValueError('여행 요청 형식을 확인해주세요.')
        data = parse_recommendation(value, mode == 'course')
        if _area_error(data):
            raise intent.IntentError('outside_service_area', '서비스 지역(천안·아산)을 벗어난 위치입니다.')
        plan = _interpret(data, mode)
        if not plan['stages']:
            return jsonify(intent.activity_clarification(plan, data, mode)), 200
        switch = mode == 'spot' and len(plan['stages']) > 1
        if switch:
            # A switch is only executed by the UI's explicit course action.
            mode = 'course'
            data = {**data, 'count': 1, 'spot_count': 3, 'slot_types': [], 'plan_mode': 'natural'}
            plan = intent.apply_controls(plan, data, mode)
        token = intent.sign_plan(plan, data, mode)
        if len(token) > 12000:
            raise intent.IntentError('intent_conflict', '여행 조건이 너무 길어요. 문장을 간단히 나눠 입력해주세요.')
        return jsonify(travel_request=plan, intent_token=token, clarification_required=False, mode_switch_required=switch,
                       target_mode=mode, target_count=data['count']), 200
    except ValueError as exc:
        if isinstance(exc, intent.IntentError):
            return _intent_error(exc)
        return jsonify(error=str(exc), reason='invalid_request'), 400


def _recommend_intent(data, mode):
    started = time.monotonic()
    try:
        if data.get('accept_unverified') and not data.get('intent_token'):
            raise intent.IntentError('intent_expired', '미확인 대안을 보기 전에 여행 해석을 확인해주세요.', 400)
        plan = (intent.read_plan(data['intent_token'], data, mode) if data.get('intent_token')
                else _interpret(data, mode))
        if not plan['stages']:
            raise intent.IntentError('activity_clarification_required', '먼저 원하는 활동을 선택하고 여행 문장을 확인해주세요.')
        base = dict(travel_request=plan, constraints_relaxed=[],
                    intent_status='pending', selection_method=None, selection_fallback_reason=None,
                    selection_validation_reason=None,
                    model_budget={'interpretation_calls_max': 1, 'selection_calls_max': 1,
                                  'retries': 0, 'search_calls': 0, 'candidate_limit': 30,
                                  'input_bytes_max': 36000, 'output_bytes_max': 24000,
                                  'interpretation_output_tokens_max': 2300, 'selection_output_tokens_max': SELECTION_OUTPUT_TOKENS,
                                  'selection_transport': 'validated_order_v1',
                                  'selection_scope': 'rank_validated_recommendations',
                                  'request_deadline_seconds': 22})
        if mode == 'spot' and len(plan['stages']) > 1:
            raise intent.IntentError('course_confirmation_required', '여러 장소를 순서대로 방문하는 요청이에요. 코스로 전환해 확인해주세요.')
        if plan['ambiguities'] or plan['unsupported']:
            return jsonify(error='확인이 필요한 조건이 있어요. 문장을 수정해주세요.',
                           reason='intent_conflict', metadata=base), 422
        df, service_area = filter_service_candidates(get_df(data['region']), data['region'])
        df, identity_review = filter_reviewed_candidates(df)
        base['model_budget']['db_reads_max_per_request'] = 1
        df, quality = filter_coordinate_candidates(df)
        df, family_policy = filter_child_candidates(df, data, plan)
        df = filter_radius(df, data['user_lat'], data['user_lng'], data['transport'])
        excluded = list(dict.fromkeys(c for e in plan['exclusions'] for c in e['category_filters']))
        df = filter_excluded_categories(df, excluded)
        # Search-query fallback is not factual category evidence for AI reasons.
        df = df[df.get('카테고리', pd.Series('', index=df.index)).fillna('').str.strip().ne('')]
        context = build_context(data, plan, _positive_category_mentions(data['user_text']))
        df, context_metadata = apply_context(df, context)
        df = add_scores(df, [])
        pools, eligible_counts, global_spot = [], [], None
        full_course_pools = []
        for i, stage in enumerate(plan['stages']):
            stage_df = df.copy()
            stage_df['_request_context_cost'] = [context_cost(r, stage['id']) for r in df.to_dict('records')]
            size = intent.MAX_CANDIDATES // len(plan['stages']) + (i < intent.MAX_CANDIDATES % len(plan['stages']))
            rows = intent.pool_for_stage(stage_df, stage['category_filters'], size, filter_keywords, eligible_counts)
            if mode == 'course':
                full_rows = intent.distinct_visits(filter_keywords(
                    stage_df, stage['category_filters'], [])).to_dict('records')
                full_course_pools.append([dict(row=r, public=intent.candidate_record(r, stage, intent.DATA_VERSION))
                                          for r in full_rows])
            if mode == 'spot' and rows:
                # Apply the quality/history choice to the full eligible pool
                # before the model's 30-ID cap can hide valid alternatives.
                eligible = intent.distinct_visits(filter_keywords(stage_df, stage['category_filters'], []))
                exemptions = _requested_brand_families(data['user_text'])
                baseline, policy = select_diverse_spots(spot_quality.rank(eligible, data['transport']),
                                                        data['count'], exemptions)
                limits = sorted(spot_quality.cost(row, data['transport']) + spot_quality.QUALITY_WINDOW
                                for row in baseline.to_dict('records'))
                selected, policy, variation = spot_quality.prefer_new(eligible, data['count'], data['transport'],
                    data['recent_place_ids'], data['seed'], data['randomize'], exemptions)
                global_spot = (selected, policy, variation, limits)
                merged, seen = [], set()
                for row in selected.to_dict('records') + baseline.to_dict('records') + rows:
                    if row['place_id'] not in seen:
                        merged.append(row)
                        seen.add(row['place_id'])
                    if len(merged) == size:
                        break
                rows = merged
            if mode == 'course' and data['randomize']:
                # Keep the bounded candidate coverage; change order only.
                rows.sort(key=lambda r: hashlib.sha256(f'{data["seed"]}:{r["place_id"]}'.encode()).hexdigest())
            pools.append([dict(row=r, public=intent.candidate_record(r, stage, intent.DATA_VERSION)) for r in rows])
        brand_policy, spot_limits, variation = None, None, None
        if mode == 'spot' and pools[0]:
            frame = pd.DataFrame([r['row'] for r in pools[0]])
            exemptions = _requested_brand_families(data['user_text'])
            baseline = spot_quality.rank(frame, data['transport'])
            baseline_selected, brand_policy = select_diverse_spots(baseline, data['count'], exemptions)
            spot_limits = sorted(spot_quality.cost(r, data['transport']) + spot_quality.QUALITY_WINDOW
                                 for r in baseline_selected.to_dict('records'))
            if global_spot:
                spot_limits = global_spot[3]
            ranked = spot_quality.rank(frame, data['transport'], data['seed'], data['randomize'])
            ordered, _ = select_diverse_spots(ranked, len(frame), exemptions)
            by_id = {r['public']['place_id']: r for r in pools[0]}
            if data['recent_place_ids']:
                selected, brand_policy, variation, _ = global_spot
                chosen_ids = selected['place_id'].tolist()
                ordered = pd.concat([selected, ordered[~ordered['place_id'].isin(chosen_ids)]])
            pools[0] = [by_id[pid] for pid in ordered['place_id']]
        base.update(identity_review=identity_review, candidate_quality=quality, family_policy=family_policy,
                    request_context=context_metadata,
                    candidate_service_area=service_area,
                    **_preference_metadata(df, data['persona_tags']),
                    candidate_counts=[len(p) for p in pools], requested_count=data['count'],
                    eligible_candidate_counts=eligible_counts,
                    recommendation_variation=variation,
                    radius_km=RADIUS_KM[data['transport']],
                    request_key=intent.request_key(data, mode, plan, pools),
                    limitation='저장된 장소 분류와 좌표의 직선거리가 근거입니다. 현장 상태·영업·도로 이동시간은 확인하지 않았습니다.')
        base['preference_limitation'] = '동행·목적을 후보 비교에 보존하고 기념일 식사의 종류별 우선순위를 반영합니다. 검증된 분위기·가격 자료가 없어 실제 취향 일치를 입증하지는 못합니다.'
        required_unknown = [dict(stage_id=s['id'], condition_id=c['id'], label=intent.condition_label(c))
                            for s in plan['stages'] for c in s['conditions'] if c['required']]
        if any(not p for p in pools):
            return jsonify(error='조건을 유지하는 단계별 후보가 부족해요.', reason='insufficient_candidates',
                           metadata={**base, 'reason': 'missing_slot_candidates', 'intent_status': 'unsatisfied'},
                           **({'places': []} if mode == 'spot' else {'courses': [], 'course_metrics': []})), 422
        if required_unknown and not data.get('accept_unverified', False):
            return jsonify(error='필수 조건을 입증할 자료가 없어요. 미확인 대안을 볼지 선택해주세요.',
                           reason='unverified_conditions', metadata={**base, 'intent_status': 'needs_confirmation',
                           'unverified_conditions': required_unknown},
                           alternatives=[{'stage_id': s['id'], 'names': [r['public']['name'] for r in p[:3]]}
                                         for s, p in zip(plan['stages'], pools)]), 422
        fallback, _course_search = (intent.course_rule_selection(
            full_course_pools, plan, data['count'], (data['user_lat'], data['user_lng']),
            data['transport'], data['seed'], data['randomize'], data['recent_place_ids']) if mode == 'course' else
            (intent.rule_selection(pools, plan, data['count']), None))
        if _course_search:
            base['recommendation_variation'] = _course_search['recommendation_variation']
            base['route_coherence'] = _course_search['route_coherence']
            # Route allocation sees every eligible venue. Only after allocation
            # do we compact model/validation records; preserve all selected IDs.
            for i, full_pool in enumerate(full_course_pools):
                chosen_ids = {course[i]['place_id'] for course in fallback}
                chosen = [r for r in full_pool if r['public']['place_id'] in chosen_ids]
                rest = [r for r in pools[i] if r['public']['place_id'] not in chosen_ids]
                pools[i] = chosen + rest[:max(0, len(pools[i]) - len(chosen))]
            base.update(candidate_counts=[len(p) for p in pools],
                        course_search_candidate_counts=_course_search['slot_candidate_counts'],
                        request_key=intent.request_key(data, mode, plan, pools))
        method = 'ai_candidates'
        selection_started = time.monotonic()
        try:
            if time.monotonic() - started > 12:
                raise TimeoutError()
            selection = intent.bounded_model(partial(_call_claude, compact_selection=True), intent.SELECTION_SYSTEM,
                {'mode': mode, 'count': data['count'], 'expected_count': len(fallback), 'selection_seed': data['seed'],
                 'stages': [{'id': s['id'], 'category_filters': s['category_filters'],
                             'preferences': [p['field'] for p in s['preferences']]} for s in plan['stages']],
                 'request_context': context,
                 'candidates': [[r['public'] for r in p] for p in pools],
                 'reference_indices': [[next(j for j, r in enumerate(pools[i])
                     if r['public']['place_id'] == choice['place_id'])
                     for i, choice in enumerate(course)] for course in fallback]},
                 min(9, 22 - (time.monotonic()-started)), max_tokens=SELECTION_OUTPUT_TOKENS,
                 provider_timeout_seconds=8)
            courses = intent.validate_selection(selection, pools, plan, data['count'], mode,
                expected=len(fallback), diversity_reference=fallback if mode == 'course' else None,
                quality_limit=_course_search.get('quality_limit') if _course_search else None,
                start=(data['user_lat'], data['user_lng']), transport=data['transport'],
                spot_quality_limits=spot_limits)
            if mode == 'course' and data['recent_place_ids']:
                history = set(data['recent_place_ids'])
                overlap = lambda chosen: len({c['place_id'] for path in chosen for c in path} & history)
                if overlap(courses) > overlap(fallback):
                    raise ValueError('selection_recent_overlap')
            if mode == 'spot':
                chosen = pd.DataFrame([next(r['row'] for r in pools[0] if r['public']['place_id'] == c[0]['place_id']) for c in courses])
                _, chosen_policy = select_diverse_spots(chosen, data['count'], _requested_brand_families(data['user_text']))
                if variation and len(set(chosen['place_id']) & set(data['recent_place_ids'])) > variation['repeated_count']:
                    raise ValueError('selection_recent_overlap')
                if chosen_policy['repeated_brand_backfill_count'] > brand_policy['repeated_brand_backfill_count']:
                    raise ValueError('selection_brand_variety')
        except Exception as error:
            method = 'rules_fallback'
            base['selection_fallback_reason'] = intent.selection_fallback_reason(error)
            base['selection_validation_reason'] = intent.selection_validation_reason(error)
            courses = (intent.validate_selection({'courses': fallback}, pools, plan, data['count'], mode,
                       expected=len(fallback))
                       if fallback else [])
        base['selection_elapsed_ms'] = round((time.monotonic() - selection_started) * 1000)
        if mode == 'spot':
            courses = order_spots(courses, pools)
        elif _course_search:
            from recommender.route_coherence import metadata as coherence_metadata
            paths = [[next(r['row'] for r in pools[i] if r['public']['place_id'] == c['place_id'])
                      for i, c in enumerate(course)] for course in courses]
            base['route_coherence'].update(coherence_metadata(paths,
                (data['user_lat'], data['user_lng']), data['transport']))
        if time.monotonic() - started > 22:
            raise intent.IntentError('intent_unavailable', '추천 처리 시간이 초과됐어요. 다시 시도해주세요.', 503)
        built = []
        for course in courses:
            visits = []
            for i, choice in enumerate(course):
                record = next(r for r in pools[i] if r['public']['place_id'] == choice['place_id'])
                # Recheck hard constraints against the original server rows.
                row = record['row']
                if (not math_is_finite_distance(row['origin_distance_km'], RADIUS_KM[data['transport']])
                        or (data['region'] not in ('', '내 주변') and row.get('지역', data['region']) != data['region'])
                        or candidate_city(row) not in ([data['region']] if data['region'] in ('천안', '아산') else ['천안', '아산'])
                        or not len(filter_keywords(pd.DataFrame([row]), plan['stages'][i]['category_filters'], []))
                        or (bool(excluded) and len(filter_keywords(pd.DataFrame([row]), excluded, [])))):
                    raise ValueError('final_constraint')
                if child_venue(row) and not children_allowed(data, plan):
                    raise ValueError('final_child_constraint')
                place = _fmt(row)
                place['travel_explanation'] = dict(stage_id=choice['stage_id'], activity=plan['stages'][i]['activity'],
                    reason='등록된 장소 분류 기준으로 요청한 종류에 해당합니다.' + (' 출발점에서의 직선거리를 함께 비교했어요.'
                        if 'distance' in choice['reason_codes'] else ''),
                    evidence=record['public']['evidence'],
                    evidence_refs=choice['evidence_refs'], reason_codes=choice['reason_codes'],
                    satisfied_conditions=['장소 종류'],
                    unverified_conditions=[intent.condition_label(c) for c in
                                           plan['stages'][i]['conditions'] + plan['stages'][i]['preferences']],
                    selection_method=method)
                visits.append(place)
            built.append(visits)
        diversity = None
        if mode == 'spot' and built:
            ranked = pd.DataFrame([next(r['row'] for r in pools[0] if r['public']['place_id'] == c[0]['place_id']) for c in built])
            varied, diversity = select_diverse_spots(ranked, data['count'], _requested_brand_families(data['user_text']))
            by_id = {c[0]['place_id']: c for c in built}
            built = [by_id[pid] for pid in varied['place_id']]
            diversity = {**brand_policy, 'returned_known_brand_counts': diversity['returned_known_brand_counts'],
                         'repeated_brand_backfill_count': diversity['repeated_brand_backfill_count']}
        base.update(returned_count=len(built), selection_method=method, diversity=diversity,
                    intent_status=('unverified_alternative' if required_unknown else
                                   'rules_fallback' if method == 'rules_fallback' else 'grounded_selection'),
                    unverified_conditions=required_unknown,
                    user_accepted_unverified=bool(required_unknown and data.get('accept_unverified')),
                    reason=None if len(built) == data['count'] else 'insufficient_candidates')
        if base.get('recommendation_variation'):
            chosen_ids = {choice['place_id'] for course in courses for choice in course}
            recent = set(data['recent_place_ids'])
            base['recommendation_variation'].update(repeated_count=len(chosen_ids & recent),
                new_count=len(chosen_ids - recent))
        if mode == 'spot':
            base.update(display_order='ai_candidate_order' if method == 'ai_candidates' else 'rule_quality_order',
                        spot_quality=spot_quality.metadata(data['randomize']), seed=data['seed'])
        if mode == 'course':
            base.update(seed=data['seed'], course_diversity=intent.selection_diversity(
                courses, pools, data['randomize']))
            if _course_search:
                for key, value in _course_search['course_diversity'].items():
                    if key.startswith('minimum_reuse_') or key in (
                            'zero_overlap_feasible', 'zero_area_overlap_feasible',
                            'overlap_fallback', 'overlap_reason', 'allocation_matching_checks'):
                        base['course_diversity'][key] = value
        if not built:
            base.update(reason='insufficient_distinct_places', intent_status='unsatisfied')
        body = ({'places': [c[0] for c in built]} if mode == 'spot' else
                {'courses': built, 'course_metrics': [route_metrics(c, (data['user_lat'], data['user_lng'])) for c in
                    [[dict(latitude=p['lat'], longitude=p['lng']) for p in course] for course in built]]})
        return jsonify(**body, metadata=base, **({'error': '서로 다른 방문 장소를 구성할 수 없어요.'} if not built else {})), 200 if built else 422
    except intent.IntentError as exc:
        return _intent_error(exc)
    except Exception:
        log.warning('자연어 추천 조건 검증 실패')
        return jsonify(error='추천 조건 검증에 실패했어요. 요청을 다시 확인해주세요.', reason='intent_unavailable'), 503


def math_is_finite_distance(value, radius):
    import math
    return isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= radius


@app.route('/recommend/spot', methods=['POST'])
def recommend_spot():
    try:
        data = _parse_request()
    except ValueError as e:
        return jsonify(error=str(e), reason='invalid_request'), 400
    if _area_error(data):
        return jsonify(error='서비스 지역(천안·아산)을 벗어난 위치입니다.', reason='outside_service_area'), 422
    if data.get('intent_version') == 1:
        return _recommend_intent(data, 'spot')
    try:
        explicit = extract_spot_category(data['user_text']) if data['user_text'] else []
    except CategoryRequired as exc:
        return jsonify(error=str(exc), reason='category_required'), 422
    except Exception:
        log.warning('명시 카테고리 해석 서비스 사용 불가')
        return jsonify(error='장소 종류를 해석하지 못했습니다. 구체적인 종류로 다시 입력해주세요.', reason='category_unavailable'), 503
    try:
        # Explicit kinds always take precedence over persona category hints.
        cats = explicit or derive_category_from_tags(data['persona_tags']) or ACTIVITY_CATS
        excluded = excluded_categories(data['user_text'])
        df, service_area = filter_service_candidates(get_df(data['region']), data['region'])
        df, identity_review = filter_reviewed_candidates(df)
        df, quality = filter_coordinate_candidates(df)
        df, family_policy = filter_child_candidates(df, data)
        df = filter_radius(df, data['user_lat'], data['user_lng'], data['transport'])
        df = filter_keywords(df, cats, [])
        df = filter_excluded_categories(df, excluded)
        tags = _preference_keywords(df, data)
        category_tags = ([tag for tag in data['persona_tags'] if tag in _TAG_CATEGORY_MAP]
                         if not explicit else [])
        preference = _preference_metadata(df, data['persona_tags'], category_tags)
        df, context_metadata = apply_context(df, build_context(data, explicit_categories=explicit))
        df = add_scores(df, tags)
        ranked = (spot_quality.rank(df, data['transport'], data['seed'], data['randomize']) if data['randomize'] or context_metadata['celebration_dining'] else
                  df.sort_values(['score', 'origin_distance_km', 'place_id'], ascending=[False, True, True]))
        selected, diversity = select_diverse_spots(ranked, data['count'],
                                                  _requested_brand_families(data['user_text']))
        variation = None
        if data['recent_place_ids']:
            selected, diversity, variation = spot_quality.prefer_new(df, data['count'], data['transport'],
                data['recent_place_ids'], data['seed'], data['randomize'], _requested_brand_families(data['user_text']))
        top = selected.to_dict('records')
        # Spots are alternatives, not an itinerary. Preserve recommendation rank.
        route = top
        metadata = dict(requested_count=data['count'], returned_count=len(route),
                        category_filters=cats, constraints_relaxed=[], **preference,
                        excluded_category_filters=excluded,
                        diversity=diversity, display_order='rule_quality_order', seed=data['seed'],
                        request_context=context_metadata,
                        recommendation_variation=variation,
                        spot_quality=spot_quality.metadata(data['randomize'], ai_guard=bool(data['recent_place_ids'])),
                        candidate_quality=quality,
                        identity_review=identity_review, candidate_service_area=service_area,
                        family_policy=family_policy,
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
    if data.get('intent_version') == 1:
        return _recommend_intent(data, 'course')
    try:
        df, service_area = filter_service_candidates(get_df(data['region']), data['region'])
        df, identity_review = filter_reviewed_candidates(df)
        df, quality = filter_coordinate_candidates(df)
        df, family_policy = filter_child_candidates(df, data)
        df = filter_excluded_categories(df, excluded_categories(data['user_text']))
        df = filter_radius(df, data['user_lat'], data['user_lng'], data['transport'])
        cats = ([SLOT_CATEGORY_MAP[s] for s in data['slot_types']] if data['slot_types']
                else fixed_categories(data['spot_count']))
        candidates = filter_keywords(df, list(dict.fromkeys(c for slot in cats for c in slot)), [])
        tags = _preference_keywords(candidates, data)
        df, context_metadata = apply_context(df, build_context(data,
            explicit_categories=_positive_category_mentions(data['user_text'])))
        start = (data['user_lat'], data['user_lng'])
        courses, metadata = search_courses(df, cats, tags, filter_keywords, data['count'],
                                           start, data['transport'], data['seed'], randomize=data['randomize'],
                                           recent_place_ids=data['recent_place_ids'])
        metadata.update(**_preference_metadata(candidates, data['persona_tags']),
                        request_context=context_metadata,
                        requested_count=data['count'], returned_count=len(courses),
                        slot_types=data['slot_types'], radius_km=RADIUS_KM[data['transport']],
                        distance_method='coordinate_great_circle',
                        candidate_quality=quality,
                        identity_review=identity_review, candidate_service_area=service_area,
                        family_policy=family_policy,
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
