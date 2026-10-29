"""Validated category intent and shared spot/course domain boundaries."""
import re
import unicodedata

from recommender.constants import (FOOD_CATS, CAFE_CATS, SPECIALIZED_CAFE_CATS,
                                  CORE_ACTIVITY_LABELS, SLOT_CATEGORY_MAP, CRAFT_CATS)

FOOD_BEVERAGE_CATS = [
    '한식', '중식', '일식', '양식', '고기', '닭갈비', '해산물',
    '국밥', '음식점', '식당', '술집', '맥주', '호프', '카페', '베이커리',
    '분식', '피자', '파스타', '뷔페', '치킨', '햄버거', '패스트푸드',
    '커피', '디저트', '아이스크림', '주스', '차(음료)', '바(Bar)',
    '포차', '막걸리', '해물', '족발', '삼겹살', '샐러드', '도시락',
]
GENERIC_FOOD_TERMS = frozenset(('맛집', '음식', '밥집', '식당', '음식점'))
HOUSING_TERMS = ('주택전시', '모델하우스', '분양홍보', '견본주택', '주택홍보')
ALIASES = {
    '맛집': FOOD_CATS, '음식': FOOD_CATS, '밥집': FOOD_CATS,
    '식당': FOOD_CATS, '음식점': FOOD_CATS,
    '전시회': ['전시'], '문화전시': ['전시'],
    '주택전시': ['주택전시관'], '견본주택': ['주택전시관'],
    '분양홍보관': ['주택전시관'], '모델하우스': ['주택전시관'],
    # Beverage intent maps to the DB's beer/pub categories, not every restaurant
    # or wine/cocktail bar. Keep model aliases subject to the same allowlist.
    **{term: ['맥주', '호프'] for term in
       ('맥주', '맥주집', '맥줏집', '맥주전문점', '맥주 전문점', '호프집', '펍')},
    '보드게임카페': ['보드카페'], '보드게임 카페': ['보드카페'],
    '보드 게임 카페': ['보드카페'],
    **{term: [term] for term in SPECIALIZED_CAFE_CATS},
    **{term[:-2] + ' 카페': [term] for term in SPECIALIZED_CAFE_CATS},
    **{label: SLOT_CATEGORY_MAP[slot] for slot, label in CORE_ACTIVITY_LABELS.items()
       if label != slot},
    '체험': SLOT_CATEGORY_MAP['체험'], '만들기': SLOT_CATEGORY_MAP['체험'],
    '등산': SLOT_CATEGORY_MAP['등산'],
    **{term: ['PC방'] for term in ('pc방', '피시방', '피씨방', 'PC 방', '피시 방', '피씨 방')},
}
NEGATION = r'말고|제외|빼고|아닌|아니|않|싫|없이|없는|말아|대신|원치|안\s*(?:가|갈|좋|먹|원)|싶지'
SPATIAL_RELATION = r'근처|주변|인근|부근|옆|가까운'

# Provider category leaves describe purpose. Match approved forms, not brand
# names or incidental character sequences (e.g. 국가유산청 / 스포츠의류).
PLAY_LEAVES = {
    '노래방': {'노래방', '노래연습장', '코인노래방', '코인노래연습장'},
    '볼링': {'볼링', '볼링장'},
    '오락': {'오락', '오락실', '전자오락실', '게임장', '아케이드'},
    'pc방': {'pc방', '피시방', '피씨방', '인터넷게임방'},
    '실내놀이터': {'실내놀이터'},
}
HIKING_TERMS = {'산', '등산', '등산로', '트레킹', '트레킹코스'}
SPORT_TERMS = {'스포츠', '레저', '수영', '볼링', '클라이밍', '체육', '경기장', '골프', '테니스'}


def _normalized(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value or ''))).casefold()


def _category_leaves(category):
    return {_normalized(v) for v in re.split(r'[,>/]+', str(category or '')) if v.strip()}


def _sports_retail(category):
    if any(_normalized(path) == '등산,아웃도어' for path in re.split(r'[>/]+', str(category or ''))):
        return True
    return any(re.fullmatch(r'(?:등산|아웃도어|스포츠|골프|테니스|수영)(?:용품|의류)(?:점|판매점|전문점)?', leaf)
               for leaf in _category_leaves(category))


def _play_matches(category, term):
    leaves = _category_leaves(category)
    # This provider's broad compound label includes outdoor sports, too. It is
    # not evidence of an indoor game facility without a concrete purpose leaf.
    if term == '오락':
        labels = {_normalized(path) for path in re.split(r'[>/]+', str(category or ''))}
        specific = PLAY_LEAVES[term] - {'오락'}
        return bool(labels.intersection(PLAY_LEAVES[term]) or leaves.intersection(specific))
    return bool(leaves.intersection(PLAY_LEAVES[term]))


def concrete_food_terms(filters):
    return [term for term in filters if term in FOOD_BEVERAGE_CATS and term not in GENERIC_FOOD_TERMS]


def filters_for_activity(filters, activity_filters):
    """Retain source kinds that belong to an activity, without broadening them.

    A meal activity is a parent purpose of specific meals such as pasta/salad,
    even when those exact leaves are absent from its default search list.
    Drinks and purpose cafes remain separate activities under the existing
    category policy. This relation never changes candidate category matching.
    """
    meal_kinds = set(FOOD_BEVERAGE_CATS) - set(CAFE_CATS) - {
        '술집', '맥주', '호프', '아이스크림', '주스', '차(음료)', '바(Bar)', '포차', '막걸리'}
    meal_activity = bool(set(activity_filters).intersection(GENERIC_FOOD_TERMS))
    return [term for term in filters if term in activity_filters or
            category_matches(term, activity_filters) or (meal_activity and term in meal_kinds)]


def directly_excluded(tail):
    """Hard exclusions cover simple scopes; qualified/double negatives need interpretation."""
    tail = re.sub(r'^(?:은|는|을|를|이|가|도)?\s*', '', tail)
    if re.match(r'말고(?:는|도)|싫지\s*않|아니지\s*않|아니(?:면|어도)|제외하지\s*(?:말|않)', tail):
        return False
    if re.match(r'아닌\s*(?:곳|데|장소|종류)(?:은|는|이|가)?\s*'
                r'(?:싫|원치|안\s*(?:가|갈|원)|가(?:고\s*싶지|지\s*않))', tail):
        return False
    return bool(re.match(NEGATION, tail))


def landmark_suffix(tail):
    """Identify a mentioned landmark, without asserting distance from that landmark."""
    return bool(re.match(r'\s*(?:(?:의\s*)?(?:근처|주변|옆|인근|부근)|에서\s*가까운)', tail))


def generic_food_modifier(term, concrete, text):
    """Narrow only an observed adjacent type modifier, never an absent OR word.

    Category arrays are unions. Adjectives between alternatives ("음식점 또는
    조용한 카페") cannot be evidence to delete one alternative.
    """
    if not text or term not in GENERIC_FOOD_TERMS or not concrete:
        return False
    occurrences = list(re.finditer(re.escape(term), text))
    return bool(occurrences) and all(any(
        re.search(re.escape(kind) + r'\s*$', text[:m.start()]) or
        re.match(r'\s*' + re.escape(kind), text[m.end():])
        for kind in concrete) for m in occurrences)


def normalize_filters(filters, known, *, text=None):
    allowed = set(known) | {'주택전시관'}
    unknown = [term for term in filters if term not in allowed and term not in ALIASES]
    if unknown:
        raise ValueError('unsupported_category')
    concrete = concrete_food_terms(filters)
    result = []
    for term in filters:
        if generic_food_modifier(term, concrete, text):
            continue
        result.extend(ALIASES.get(term, [term]))
    return list(dict.fromkeys(result))


def specialized_cafe_kind(category, name=''):
    """Use actual purpose categories, with a narrow fallback for cafe labels.

    Names are auxiliary evidence only for already cafe/coffee/dessert records.
    A full '보드게임카페'/'라이브카페' label is evidence; '보드', '게임',
    '라이브' or an ordinary cafe's unrelated brand word alone is not.
    """
    value = re.sub(r'\s+', '', str(category or '')).lower()
    for kind in SPECIALIZED_CAFE_CATS:
        if kind in value or (kind == '보드카페' and '보드게임카페' in value):
            return kind
    if any(term in value for term in CAFE_CATS):
        label = re.sub(r'\s+', '', str(name or '')).lower()
        for kind in SPECIALIZED_CAFE_CATS:
            if kind in label or (kind == '보드카페' and '보드게임카페' in label):
                return kind
    return None


def category_matches(category, filters, name=''):
    value = str(category or '').lower()
    housing = any(term in value for term in HOUSING_TERMS)
    cafe_kind = specialized_cafe_kind(category, name)
    tokens = re.split(r'[,>/\s]+', value)
    for term in filters:
        term = term.lower()
        # Generic exhibitions, photo spots and course culture slots cannot match
        # property showrooms. Explicit housing intent can still select them.
        if housing and not any(hint in term for hint in HOUSING_TERMS):
            continue
        if housing and any(hint in term for hint in HOUSING_TERMS):
            return True
        if cafe_kind:
            # Applies to all generic cafe-slot alternatives, including mixed
            # provider labels such as '보드카페,디저트'. Explicit purpose wins.
            if term in CAFE_CATS:
                continue
            if term == cafe_kind:
                return True
        if term in HIKING_TERMS | SPORT_TERMS and _sports_retail(category):
            continue
        if term in PLAY_LEAVES:
            if _play_matches(category, term):
                return True
            continue
        if term in CRAFT_CATS:
            labels = _category_leaves(category) | {_normalized(path) for path in re.split(r'[>/]+', value)}
            if _normalized(term) in labels:
                return True
            continue
        if term == '국가유산':
            if '국가유산' in _category_leaves(category):
                return True
            continue
        if term == '전통' and '전통,민속주점' == _normalized(category):
            continue
        if term == '산':
            if '산' in tokens:
                return True
        elif term in value:
            return True
    return False
