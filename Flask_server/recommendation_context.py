"""Request purpose is a ranking preference, never evidence of venue ambience.

Only category facts affect the deterministic cost. No brand classification,
price, opening hours or romantic/quiet claims are inferred from venue names.
"""
import re

from category_policy import category_matches, directly_excluded, GENERIC_FOOD_TERMS
from intent_context import grounded_tags, positive_context_matches

POLICY_VERSION = 'source_context_category_cost_v1'
PURPOSE_TAGS = ('기념일', '생일', '프로포즈', '첫 데이트', '소개팅/첫만남')
CONTEXT_TAGS = PURPOSE_TAGS + ('연인과', '친구와', '혼자', '부부끼리', '가족 나들이',
    '부모님 모시고', '아이와 함께', '유아/영아 동반', '단체/모임', '회식',
    '로맨틱한', '조용한', '활동적인', '힐링/여유', '고급스러운', '소소한 일상')
# A default for broad celebration-meal requests, not a learned quality score.
# Explicit requests for any of these kinds always override this preference.
CASUAL_MEALS = ('분식', '김밥', '떡볶이', '라면', '패스트푸드', '햄버거',
                '도시락', '토스트', '핫도그', '국밥', '해장국')
CASUAL_MEAL_COST = 1.0
COMPANION_TAGS = ('혼자', '친구와', '연인과', '부부끼리', '가족 나들이',
    '부모님 모시고', '아이와 함께', '유아/영아 동반', '단체/모임', '회식', '소개팅/첫만남')
MANUAL_MOODS = ('로맨틱한', '조용한', '활동적인', '힐링/여유')
# Entire reason must contain only cuisine-selection vocabulary. An arbitrary
# noun such as vegan/pets/takeout is a real unresolved request, not a filler.
_CUISINE_ONLY_REASON = re.compile(r'(?:(?:구체적인|구체적으로|구체적|구체|음식|요리|메뉴|종류|'
    r'한식|중식|일식|양식|고기|분식|해산물|등|또는|가|이|를|을|은|는|'
    r'명시되지|지정하지|선택되지|않았습니다|않았음|않아|않은|'
    r'선택|지정|명시|범위|확인|필요합니다|필요해요|필요)[\s,.()/:·]*)+')


def _explicit_kinds(text, categories):
    return list(dict.fromkeys(kind for kind in tuple(categories) + CASUAL_MEALS
        if kind not in GENERIC_FOOD_TERMS and
        positive_context_matches(text, re.escape(kind))))


def build_context(data, plan=None, explicit_categories=()):
    text = data.get('user_text', '')
    sentence_tags = grounded_tags(CONTEXT_TAGS, text, directly_excluded)
    manual = [tag for tag in data.get('persona_tags', []) if tag in CONTEXT_TAGS]
    # Apply the same manual companion/mood precedence as the canonical plan.
    if any(tag in MANUAL_MOODS for tag in manual):
        sentence_tags = [tag for tag in sentence_tags if tag not in MANUAL_MOODS]
    companion = (plan or {}).get('companion')
    companion_value = companion['value'] if companion else next(
        (tag for tag in manual if tag in COMPANION_TAGS), None)
    if companion_value:
        sentence_tags = [tag for tag in sentence_tags if tag not in COMPANION_TAGS]
        sentence_tags.append(companion_value)
    tags = list(dict.fromkeys(sentence_tags + manual))
    purposes = [tag for tag in tags if tag in PURPOSE_TAGS]
    easy_meal = bool(positive_context_matches(text,
        r'간단한|간단하게|가볍게|빨리|빠른|빠르게|저렴한|저렴하게|저렴하고|가성비|싸게'))
    kinds = _explicit_kinds(text, explicit_categories)
    stage_kinds = {}
    for stage in (plan or {}).get('stages', []):
        filters = stage['category_filters']
        # A source quote scopes food requests to their own visit. For manual
        # slots with no quote, only explicitly narrowed filters are exempt.
        quote = stage.get('quote')
        stage_kinds[stage['id']] = (_explicit_kinds(quote, kinds) if quote else
            [kind for kind in kinds if not set(filters).intersection(GENERIC_FOOD_TERMS)
             and category_matches(kind, filters)])
    return dict(policy=POLICY_VERSION, purposes=purposes, tags=tags,
        companion=companion_value,
        celebration_dining=bool(purposes or '로맨틱한' in tags),
        casual_meal_requested=easy_meal,
        explicit_categories=kinds, stage_explicit_categories=stage_kinds,
        venue_ambience_verified=False)


def apply_context(frame, context):
    result = frame.copy()
    explicit = context['explicit_categories']
    def penalty(row, requested):
        category = row.get('카테고리', '')
        if (not context['celebration_dining'] or context.get('casual_meal_requested') or
                not category_matches(category, CASUAL_MEALS)):
            return 0.0
        if requested and category_matches(category, requested):
            return 0.0
        return CASUAL_MEAL_COST
    rows = result.to_dict('records')
    result['_request_context_cost'] = [penalty(row, explicit) for row in rows]
    result['_request_context_cost_by_stage'] = [{sid: penalty(row, kinds)
        for sid, kinds in context.get('stage_explicit_categories', {}).items()} for row in rows]
    metadata = dict(context, casual_meal_cost=CASUAL_MEAL_COST,
        deprioritized_candidate_count=int(result['_request_context_cost'].gt(0).sum()),
        limitation='기념일 식사에서 간단한 식사 분류의 우선순위를 낮춥니다. 가격·분위기·독립 매장 여부를 입증하는 점수가 아닙니다.')
    return result, metadata


def context_cost(row, stage_id=None):
    """Internal server-only column survives score recalculation and pool search."""
    if stage_id and stage_id in row.get('_request_context_cost_by_stage', {}):
        return float(row['_request_context_cost_by_stage'][stage_id])
    return float(row.get('_request_context_cost', 0.0))


def order_spots(courses, pools):
    """A model permutation cannot put a downranked category ahead of its peers."""
    costs = {r['public']['place_id']: context_cost(r['row']) for r in pools[0]}
    return sorted(courses, key=lambda course: costs[course[0]['place_id']])


def resolve_generic_meal_ambiguities(plan):
    """A broad meal is a valid choice; do not demand an arbitrary cuisine.

    Remove only a redundant cuisine-selection question. Budget, availability,
    allergies and any other unresolved requirement still block as before.
    """
    kept = []
    for entry in plan['ambiguities']:
        quote, reason = entry['quote'], entry['reason']
        broad_quote = re.fullmatch(r'\s*(?:(?:평소에?|일상에서)\s*)?(?:(?:먹을|먹는|먹고\s*싶은)\s*)?'
            r'(?:식당|음식점|밥집|음식|맛집|식사)\s*', quote)
        cuisine_question = (re.search(r'음식\s*종류|종류.{0,12}(?:명시|지정|선택|확인)', reason) and
                            _CUISINE_ONLY_REASON.fullmatch(reason.strip()))
        supported = any(set(s['category_filters']).intersection(GENERIC_FOOD_TERMS) or
            {'한식', '중식', '양식', '분식'}.issubset(s['category_filters']) for s in plan['stages'])
        if not (broad_quote and cuisine_question and supported):
            kept.append(entry)
    plan['ambiguities'] = kept
    return plan
