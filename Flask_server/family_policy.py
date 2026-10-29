"""Candidate gate for child-purpose venues, independent of cafe slot matching."""
import re

from category_policy import NEGATION, specialized_cafe_kind, directly_excluded

CHILD_COMPANIONS = {'아이와 함께', '유아/영아 동반'}
COMPANIONS = CHILD_COMPANIONS | {'혼자', '친구와', '연인과', '부부끼리', '가족 나들이',
    '부모님 모시고', '단체/모임', '동아리/클럽', '회식', '소개팅/첫만남'}
CHILD_KINDS = {'키즈카페', '실내놀이터'}
EXPLICIT_CHILD_ACTIVITY = r'키즈\s*카페|실내\s*놀이터'
CHILD_MUSEUM = (r'어린이\s*(?:미술|교통안전)?\s*(?:박물관|미술관|과학관|체험관|전시관)'
                r'|유아\s*(?:교육)?\s*(?:체험관|전시관)|유아\s*숲\s*체험(?:원|장)?')
CHILD_NEGATION = NEGATION + r'|안\s*(?:할|하|동반|데려)|동반\s*하지'


def children_allowed(data, plan=None):
    text = data.get('user_text', '')
    explicit = bool(re.search(EXPLICIT_CHILD_ACTIVITY, text))
    explicit_museum = any(not directly_excluded(text[m.end():]) for m in re.finditer(CHILD_MUSEUM, text))
    if plan is not None:
        # The structured interpretation resolves double negatives. Still require
        # literal child-activity evidence; indoor/general activity slots cannot
        # manufacture a child request. Manual companion overrides raw companion.
        explicit = explicit and any(CHILD_KINDS.intersection(s['category_filters']) for s in plan['stages'])
        explicit_museum = explicit_museum and any(any(
            kind in category for category in s['category_filters']
            for kind in ('박물관', '미술관', '과학관', '체험', '전시', '자연', '공원', '숲')) for s in plan['stages'])
    elif re.search(CHILD_NEGATION, text):
        # Legacy manual requests have no semantic plan. Ambiguous child scopes
        # stay closed; no word match is allowed to override a negation.
        explicit = False
        explicit_museum = False
    explicit = explicit or explicit_museum
    manual_companions = {t for t in data.get('persona_tags', []) if t in COMPANIONS}
    if manual_companions:
        return explicit or manual_companions.issubset(CHILD_COMPANIONS)
    if plan is not None:
        companion = plan.get('companion') or {}
        return explicit or (companion.get('value') in CHILD_COMPANIONS and not re.search(CHILD_NEGATION, text))
    positive_child = bool(re.search(r'(?:아이|유아|영아)(?:와|랑)\s*(?:함께|같이)?|(?:아이|유아|영아)\s*동반', text))
    return explicit or (positive_child and not re.search(CHILD_NEGATION, text))


def child_venue(record):
    category = str(record.get('카테고리', '') or '')
    name = str(record.get('가게명', '') or '')
    return (specialized_cafe_kind(category, name) == '키즈카페'
            or '실내놀이터' in re.sub(r'\s+', '', category)
            or bool(re.search(CHILD_MUSEUM, name + ' ' + category)))


def filter_child_candidates(frame, data, plan=None):
    allowed = children_allowed(data, plan)
    mask = frame.apply(child_venue, axis=1).astype(bool)
    removed = int(mask.sum()) if not allowed else 0
    return frame.loc[~mask].copy() if not allowed else frame, {
        'child_venues_allowed': allowed, 'excluded_count': removed,
        'policy': 'explicit_child_activity_or_companion_v2',
        'limitation': '아이 동반은 일반 카페 슬롯을 키즈카페로 변경하지 않습니다.',
    }
