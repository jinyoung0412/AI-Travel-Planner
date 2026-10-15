"""Product defaults shared by the recommendation compatibility API."""

FOOD_CATS = ['한식', '중식', '일식', '양식', '고기', '닭갈비', '해산물', '국밥',
             '음식점', '식당', '분식', '피자', '치킨', '햄버거', '뷔페']
CAFE_CATS = ['카페', '베이커리', '커피', '디저트']
SLOT_CATEGORY_MAP = {
    '음식': FOOD_CATS,
    '카페': CAFE_CATS,
    '자연·산책': ['공원', '산책로', '하천', '수목원', '생태', '호수', '정원'],
    '등산': ['등산', '트레킹', '계곡', '산'],
    '문화·역사': ['박물관', '전시', '미술관', '문화재', '유적', '기념관', '역사', '국가유산'],
    '쇼핑': ['시장', '쇼핑', '백화점', '아울렛'],
    '관광지': ['관광지', '온천', '캠핑', '테마공원'],
    '실내 오락': ['키즈카페', '노래방', '볼링', '오락'],
}
ACTIVITY_CATS = list(dict.fromkeys(c for s, cats in SLOT_CATEGORY_MAP.items()
                                if s not in ('음식', '카페') for c in cats))
RADIUS_KM = {'차': 15.0, '대중교통': 4.5}
