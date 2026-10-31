"""Product defaults shared by the recommendation compatibility API."""

FOOD_CATS = ['한식', '중식', '일식', '양식', '고기', '닭갈비', '해산물', '국밥',
             '음식점', '식당', '분식', '피자', '치킨', '햄버거', '뷔페']
CAFE_CATS = ['카페', '베이커리', '커피', '디저트']
# Their primary purpose differs from an ordinary coffee/bakery stop. Keep
# explicit categories selectable without treating every '*카페' as generic cafe.
SPECIALIZED_CAFE_CATS = ['키즈카페', '보드카페', '방탈출카페', '라이브카페', '슬라임카페']
INDOOR_ACTIVITY_CATS = ['노래방', '볼링', '오락', 'PC방', '보드카페', '방탈출카페',
                        '키즈카페', '실내놀이터']
CRAFT_CATS = ['공방', '관람,체험', '체험마을', '체험여행']
SLOT_CATEGORY_MAP = {
    '음식': FOOD_CATS,
    '카페': CAFE_CATS,
    '자연·산책': ['공원', '산책로', '도보코스', '하천', '수목원', '생태', '호수', '정원'],
    '등산': ['등산', '트레킹', '등산로', '트레킹코스', '산'],
    '문화·역사': ['박물관', '전시', '미술관', '문화재', '유적', '기념관', '역사', '국가유산'],
    '쇼핑': ['시장', '쇼핑', '백화점', '아울렛'],
    '관광지': ['관광지', '온천', '캠핑', '테마공원'],
    '실내 오락': INDOOR_ACTIVITY_CATS,
    '체험': CRAFT_CATS,
    '맥주·호프': ['맥주', '호프'],
}
# Public choices use six concrete activities. Old wire values remain valid for
# saved/older clients; removing a button must not rewrite an existing request.
CORE_ACTIVITY_LABELS = {
    '음식': '식사', '카페': '카페·디저트', '자연·산책': '산책·자연',
    '문화·역사': '전시·문화관람', '체험': '체험·만들기', '실내 오락': '실내 놀거리',
}
# Explicit course visits are selectable without changing generic activity tags
# or making ordinary meals/general outings include drinking venues.
COURSE_ACTIVITY_LABELS = {**CORE_ACTIVITY_LABELS, '맥주·호프': '맥주·호프'}
DEFAULT_COURSE_SLOTS = ['음식', '자연·산책', '카페', '문화·역사', '음식']
CORE_ACTIVITY_TAG_SLOTS = {
    '맛집 탐방': '음식', '카페 투어': '카페', '자연/산책': '자연·산책',
    '문화·역사 탐방': '문화·역사', '체험 공방': '체험', '노래방/실내 오락': '실내 오락',
}
def activity_tag_label(tag):
    """User-facing core activity names; request/storage wire tags stay stable."""
    return CORE_ACTIVITY_LABELS.get(CORE_ACTIVITY_TAG_SLOTS.get(tag), tag)


ACTIVITY_TAG_CATEGORIES = {tag: SLOT_CATEGORY_MAP[slot] for tag, slot in CORE_ACTIVITY_TAG_SLOTS.items()}
# Legacy/detail intents remain usable without returning to the main picker.
ACTIVITY_TAG_CATEGORIES.update({
    '박물관/전시': ['박물관', '미술관', '전시'],
    '등산/트레킹': SLOT_CATEGORY_MAP['등산'],
    '쇼핑': SLOT_CATEGORY_MAP['쇼핑'],
    '스포츠/레저': ['스포츠', '레저', '수영', '볼링', '클라이밍', '체육', '경기장', '골프', '테니스'],
    '전통/한옥': ['한옥', '전통', '문화재'],
})
ACTIVITY_CATS = list(dict.fromkeys(c for s, cats in SLOT_CATEGORY_MAP.items()
                                if s in CORE_ACTIVITY_LABELS and s not in ('음식', '카페') for c in cats))
RADIUS_KM = {'차': 15.0, '대중교통': 4.5}
