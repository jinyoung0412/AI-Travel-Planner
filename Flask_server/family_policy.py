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
_ACTION = r'(?:하|가|데려\s*가|데리고\s*가)'
_DIRECT_ACTION_NEGATION = re.compile(
    r'^(?:는|은)?\s*(?:' + _ACTION + r'지\s*(?:말|않)|'
    + _ACTION + r'고\s*싶지|' + _ACTION + r'기(?:는|가)?\s*(?:싫|원치)|'
    + _ACTION + r'는\s*(?:건|게|것은)?\s*(?:싫|대신)|'
    r'안\s*(?:가|하|할|데려|데리))')
_QUALIFIED_ACTION = re.compile(
    r'^(?:는|은)?\s*(?:' + _ACTION + r'지\s*않(?:는|을)\s*'
    r'(?:건|것은|게|수는|수)\s*(?:아니|없)|'
    r'안\s*가는\s*(?:건|것은|게)\s*아니|'
    + _ACTION + r'(?:기(?:는|가)?|는\s*(?:건|게|것은)?)\s*싫지\s*않)')
_INFANT_TERMS = {'유아', '영아', '아기'}
_AGE_CONTRAST = re.compile(
    r'^\s*(?:(?:은|는|이|가)\s*)?(?:아니(?:고|라(?:서)?)|아닌|없이)(?=\s|$)')
_WITH_CHILD = r'(?:(?:와|과|랑)\s*(?:함께|같이)|\s*동반)'
_POSITIVE_CHILD = re.compile(
    r'(?<![가-힣])(?P<subject>아이|유아|영아|아기|자녀|어린이)' + _WITH_CHILD)
_OTHER_CHILD = re.compile(
    r'(?<![가-힣])(?:(?:초등학생|중학생|고등학생)(?:인)?(?:\s*(?:아이|자녀))?'
    r'|다른\s*(?:아이|자녀))' + _WITH_CHILD)
_RETRACTED_PROHIBITION = re.compile(
    r'^(?:는|은)?\s*' + _ACTION + r'지\s*말라는\s*'
    r'(?:건|것(?:은|이)|뜻(?:은|이)|의미(?:는|가))\s*'
    r'아니(?:고|라(?:서)?|에요|야|다)(?=\s|[,]|$)')
_FOLLOWUP_COMPANION = re.compile(r'[\s,]*(?:(?:이번에는|이번엔|오늘은|지금은)\s*)?')


def _companion_tail(tail):
    tail = re.sub(r'^(?:와|랑|를|는|는요|은)?\s*(?:(?:함께|같이)\s*)?', '', tail)
    return re.sub(r'^동반(?:은|는|을|이|도)?\s*', '', tail)


def _positive_companion_spans(text, companion, *, other_child=False):
    """Literal accompaniment plus a compatible plan, never age suitability proof."""
    value = (companion or {}).get('value')
    if value not in CHILD_COMPANIONS or (other_child and value != '아이와 함께'):
        return []
    patterns = (_OTHER_CHILD,) if other_child else (_POSITIVE_CHILD, _OTHER_CHILD)
    spans = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            if value == '유아/영아 동반' and match.groupdict().get('subject') not in _INFANT_TERMS:
                continue
            quote = companion.get('quote')
            if quote and quote not in match.group() and match.group() not in quote:
                continue
            tail = _companion_tail(text[match.end():])
            # An action ban/retracted quote is not itself independent positive
            # accompaniment evidence. No recursive exception can prove itself.
            if directly_excluded(tail) or _DIRECT_ACTION_NEGATION.match(tail):
                continue
            spans.append((match.start(), match.end()))
    return spans


def _child_companion_negated(text, companion=None):
    """Only a direct child-companion clause may veto a structured companion.

    Arbitrary/double-negative scopes belong to the interpretation. Legacy
    requests keep their original conservative whole-sentence gate below.
    """
    other_child = _positive_companion_spans(text, companion, other_child=True)
    positive = _positive_companion_spans(text, companion)
    for match in re.finditer(r'아이|유아|영아|아기|자녀|어린이', text):
        raw_tail = text[match.end():]
        # A subtype attribute/absence cannot negate a separately grounded
        # older/different child's accompaniment. Generic/action bans still run.
        if match.group() in _INFANT_TERMS and other_child and _AGE_CONTRAST.match(raw_tail):
            continue
        tail = raw_tail
        if re.match(r'\s*없이(?:는)?\s*(?:안\s*가|가지\s*않|가고\s*싶지|싫)', tail):
            continue
        tail = _companion_tail(tail)
        retracted = _RETRACTED_PROHIBITION.match(tail)
        if retracted:
            end = match.end() + len(raw_tail) - len(tail) + retracted.end()
            if any(start >= end and _FOLLOWUP_COMPANION.fullmatch(text[end:start])
                   for start, _ in positive):
                continue
        if _QUALIFIED_ACTION.match(tail):
            continue
        if directly_excluded(tail):
            return True
        if _DIRECT_ACTION_NEGATION.match(tail):
            return True
    return False


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
        return explicit or (companion.get('value') in CHILD_COMPANIONS
                            and not _child_companion_negated(text, companion))
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
