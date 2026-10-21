"""Validated category intent and shared spot/course domain boundaries."""
import re

from recommender.constants import FOOD_CATS

FOOD_BEVERAGE_CATS = [
    '한식', '중식', '일식', '양식', '고기', '닭갈비', '해산물',
    '국밥', '음식점', '식당', '술집', '호프', '카페', '베이커리',
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
}
NEGATION = r'말고|제외|빼고|아닌|아니|않|싫|없이|없는|말아|대신|원치|안\s*(?:가|갈|좋|먹|원)|싶지'
SPATIAL_RELATION = r'근처|주변|인근|부근|옆|가까운'


def concrete_food_terms(filters):
    return [term for term in filters if term in FOOD_BEVERAGE_CATS and term not in GENERIC_FOOD_TERMS]


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


def normalize_filters(filters, known):
    allowed = set(known) | {'주택전시관'}
    unknown = [term for term in filters if term not in allowed and term not in ALIASES]
    if unknown:
        raise ValueError('unsupported_category')
    # A concrete food request must never expand to every restaurant.
    concrete = concrete_food_terms(filters)
    result = []
    for term in filters:
        if concrete and term in GENERIC_FOOD_TERMS:
            continue
        result.extend(ALIASES.get(term, [term]))
    return list(dict.fromkeys(result))


def category_matches(category, filters):
    value = str(category or '').lower()
    housing = any(term in value for term in HOUSING_TERMS)
    tokens = re.split(r'[,>/\s]+', value)
    for term in filters:
        term = term.lower()
        # Generic exhibitions, photo spots and course culture slots cannot match
        # property showrooms. Explicit housing intent can still select them.
        if housing and not any(hint in term for hint in HOUSING_TERMS):
            continue
        if housing and any(hint in term for hint in HOUSING_TERMS):
            return True
        if term == '산':
            if '산' in tokens:
                return True
        elif term == '카페' and '키즈카페' in value:
            continue
        elif term in value:
            return True
    return False
