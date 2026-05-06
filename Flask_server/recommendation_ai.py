import json, math
import pandas as pd
from geopy.distance import geodesic


# ── 스코어링 ──────────────────────────────────────────────────
def add_scores(df: pd.DataFrame, blog_tag_keywords: list) -> pd.DataFrame:
    """
    최종점수 = 0.4 × 인기도_norm + 0.6 × 태그_매칭_점수
    인기도: log(방문자수 + 블로그수×0.3 + 1) Min-Max 정규화
    태그매칭: blog_tag_keywords 중 블로그 태그에 포함된 비율
    """
    df = df.copy()

    raw = (df['방문자수'].fillna(0) + df['블로그수'].fillna(0) * 0.3 + 1).apply(math.log)
    mn, mx = raw.min(), raw.max()
    df['pop_score'] = ((raw - mn) / (mx - mn)).clip(0, 1) if mx > mn else 0.0

    if blog_tag_keywords:
        tokens = list({tok for kw in blog_tag_keywords for tok in kw.split()})
        def _match(tags_json):
            if pd.isna(tags_json):
                return 0.0
            try:
                keys = ' '.join(json.loads(tags_json).keys())
                return sum(1 for tok in tokens if tok in keys) / len(tokens)
            except Exception:
                return 0.0
        df['tag_score'] = df['blog_tags'].apply(_match)
    else:
        df['tag_score'] = 0.0

    df['score'] = 0.15 * df['pop_score'] + 0.85 * df['tag_score']
    return df


# ── Greedy TSP ────────────────────────────────────────────────
def greedy_tsp(records: list, start: tuple) -> list:
    """출발점(start)에서 nearest-neighbor로 방문 순서 결정."""
    route, current, remaining = [], start, list(records)
    while remaining:
        nearest = min(
            remaining,
            key=lambda p: geodesic(current, (p['latitude'], p['longitude'])).kilometers,
        )
        route.append(nearest)
        remaining.remove(nearest)
        current = (nearest['latitude'], nearest['longitude'])
    return route


# ── 코스 모드: 단일 계획에 대해 stop별 최적 장소 반환 ─────────
_FOOD_KEYWORDS = {'한식', '중식', '일식', '양식', '고기', '닭갈비', '해산물',
                  '국밥', '카페', '베이커리', '술집', '호프', '음식점', '식당'}

def _is_food(category_filters: list) -> bool:
    return any(kw in _FOOD_KEYWORDS for kw in category_filters)


def find_best_for_plan(df: pd.DataFrame, stops: list, filter_fn) -> list:
    """
    Claude가 설계한 단일 코스 계획(stops)에 대해
    각 stop의 최적 장소를 반환.
    - 중복 장소 제외
    - 음식점·카페는 코스 내 최대 1곳 강제
    """
    selected, used_names = [], set()
    food_count   = 0
    used_food_cats: set = set()  # 이미 사용된 음식 카테고리 (같은 대분류 반복 방지)
    MAX_FOOD = 3  # 5-stop 코스 기준: 점심+저녁+카페 허용

    for stop in stops:
        cat_f = stop['category_filters']

        if _is_food(cat_f):
            # 음식 할당량 초과 → 비음식 탐색
            if food_count >= MAX_FOOD:
                cat_f = []
            # 같은 음식 카테고리 반복 → 비음식 탐색
            elif any(c in used_food_cats for c in cat_f):
                cat_f = []

        cands = filter_fn(df, cat_f, stop['blog_tag_keywords'])
        cands = add_scores(cands, stop['blog_tag_keywords'])
        cands = cands[~cands['가게명'].isin(used_names)]
        if cands.empty:
            cands = filter_fn(df, cat_f, [])
            cands = add_scores(cands, [])
            cands = cands[~cands['가게명'].isin(used_names)]
        if cands.empty:
            cands = add_scores(df, [])
            cands = cands[~cands['가게명'].isin(used_names)]
        if cands.empty:
            return []

        best = cands.nlargest(1, 'score').iloc[0].to_dict()
        selected.append(best)
        used_names.add(best['가게명'])
        if _is_food(stop['category_filters']):
            food_count += 1
            used_food_cats.update(stop['category_filters'])

    return selected


# ── 고정 코스 템플릿: 음식→활동→카페→활동→음식 ──────────────
FOOD_CATS = ['한식', '중식', '일식', '양식', '고기', '닭갈비', '해산물', '국밥', '술집', '호프']
CAFE_CATS = ['카페', '베이커리']

_ACTIVITY_GROUPS = [
    ['공원', '산책로', '하천'],
    ['자연공원', '관광지', '온천', '캠핑'],
    ['박물관', '전시', '미술관', '문화재', '유적'],
    ['시장', '쇼핑', '체험'],
    ['키즈카페', '노래방', '볼링'],
]

# 코스별 활동 그룹 페어 (stop2, stop4 인덱스) — 최대 5코스
_COURSE_ACT_PAIRS = [(0, 2), (1, 3), (4, 0), (3, 4), (2, 1)]


def _pick_best(df, category_filters, blog_tag_keywords, filter_fn, used_names):
    cands = filter_fn(df, category_filters, blog_tag_keywords)
    cands = add_scores(cands, blog_tag_keywords)
    cands = cands[~cands['가게명'].isin(used_names)]
    if cands.empty:
        cands = filter_fn(df, category_filters, [])
        cands = add_scores(cands, [])
        cands = cands[~cands['가게명'].isin(used_names)]
    if cands.empty:
        return None
    return cands.nlargest(1, 'score').iloc[0].to_dict()


def _matched_food_cats(place: dict) -> set:
    cat = place.get('카테고리', '') or ''
    return {c for c in FOOD_CATS if c in cat}


SLOT_CATEGORY_MAP = {
    '음식':     ['한식', '중식', '일식', '양식', '고기', '닭갈비', '해산물', '국밥', '음식점', '식당'],
    '카페':     ['카페', '베이커리'],
    '자연·산책': ['공원', '산책로', '하천', '자연공원', '수목원', '생태'],
    '등산':     ['산', '등산', '트레킹', '계곡'],
    '문화·역사': ['박물관', '전시', '미술관', '문화재', '유적', '기념관', '역사'],
    '쇼핑':    ['시장', '쇼핑', '백화점', '아울렛'],
    '관광지':   ['관광지', '온천', '캠핑', '테마공원'],
    '실내 오락': ['키즈카페', '노래방', '볼링', '오락'],
}


def generate_from_slots(df, slot_types, blog_tag_keywords, filter_fn, n: int = 3):
    """
    사용자 정의 슬롯 순서로 코스 생성.
    각 슬롯 타입 → SLOT_CATEGORY_MAP 카테고리로 장소 탐색.
    블로그 키워드는 각 슬롯에서 스코어링 보조에만 사용.
    """
    if not slot_types:
        return []

    cluster_col = 'Cluster' if 'Cluster' in df.columns else None
    cluster_ids = df[cluster_col].value_counts().index.tolist() if cluster_col else [None] * n

    courses = []
    globally_used = set()

    for i, cid in enumerate(cluster_ids):
        if len(courses) >= n:
            break

        c_df = df[df[cluster_col] == cid] if cid is not None else df
        used_names = set(globally_used)
        course = []
        ok = True

        for slot in slot_types:
            cats = SLOT_CATEGORY_MAP.get(slot, [])
            place = _pick_best(c_df, cats, blog_tag_keywords, filter_fn, used_names)
            if place is None:
                place = _pick_best(df, cats, blog_tag_keywords, filter_fn, used_names)
            if place is None:
                ok = False
                break
            course.append(place)
            used_names.add(place['가게명'])

        if ok:
            courses.append(course)
            globally_used.update(p['가게명'] for p in course)

    return courses


def generate_fixed_courses(df, blog_tag_keywords, filter_fn, n: int = 3, spots: int = 5):
    """
    Cluster-aware 템플릿 코스 생성. spots 파라미터로 코스당 스팟 수 조절.
    - 3 stops: 음식 → 활동 → 카페
    - 4 stops: 음식 → 활동 → 카페 → 활동
    - 5 stops: 음식 → 활동 → 카페 → 활동 → 음식
    """
    cluster_col = 'Cluster' if 'Cluster' in df.columns else None

    if cluster_col:
        cluster_ids = df[cluster_col].value_counts().index.tolist()
    else:
        cluster_ids = [None] * n

    courses = []
    globally_used = set()

    for i, cid in enumerate(cluster_ids):
        if len(courses) >= n or i >= len(_COURSE_ACT_PAIRS):
            break

        act_idx1, act_idx2 = _COURSE_ACT_PAIRS[i]
        c_df = df[df[cluster_col] == cid] if cid is not None else df
        used_names = set(globally_used)
        used_food_cats: set = set()
        course = []

        def pick(cats, tags, _c=c_df, _full=df, _used=used_names):
            r = _pick_best(_c, cats, tags, filter_fn, _used)
            if r is None:
                r = _pick_best(_full, cats, tags, filter_fn, _used)
            return r

        # Stop 1: 음식점
        food1 = pick(FOOD_CATS, blog_tag_keywords)
        if food1 is None:
            continue
        course.append(food1)
        used_names.add(food1['가게명'])
        used_food_cats.update(_matched_food_cats(food1))

        # Stop 2: 활동 (그룹 act_idx1)
        act1 = pick(_ACTIVITY_GROUPS[act_idx1], blog_tag_keywords)
        if act1 is None:
            for g in _ACTIVITY_GROUPS:
                if g is not _ACTIVITY_GROUPS[act_idx1]:
                    act1 = pick(g, blog_tag_keywords)
                    if act1:
                        break
        if act1 is None:
            continue
        course.append(act1)
        used_names.add(act1['가게명'])

        # Stop 3: 카페
        cafe = pick(CAFE_CATS, blog_tag_keywords)
        if cafe is None:
            continue
        course.append(cafe)
        used_names.add(cafe['가게명'])

        if spots == 3:
            courses.append(course)
            globally_used.update(p['가게명'] for p in course)
            continue

        # Stop 4: 활동 (그룹 act_idx2, stop2와 다른 그룹)
        act2 = pick(_ACTIVITY_GROUPS[act_idx2], blog_tag_keywords)
        if act2 is None:
            for g in _ACTIVITY_GROUPS:
                if g is not _ACTIVITY_GROUPS[act_idx1] and g is not _ACTIVITY_GROUPS[act_idx2]:
                    act2 = pick(g, blog_tag_keywords)
                    if act2:
                        break
        if act2 is None:
            continue
        course.append(act2)
        used_names.add(act2['가게명'])

        if spots == 4:
            courses.append(course)
            globally_used.update(p['가게명'] for p in course)
            continue

        # Stop 5: 음식점 (stop1과 다른 카테고리)
        remaining_food = [c for c in FOOD_CATS if c not in used_food_cats]
        food2 = pick(remaining_food or FOOD_CATS, blog_tag_keywords)
        if food2 is None:
            continue
        course.append(food2)
        used_names.add(food2['가게명'])

        courses.append(course)
        globally_used.update(p['가게명'] for p in course)

    return courses


# ── 코스 모드: 군집별 3-stop 선택 (상위 N개 코스 반환) ───────
def select_courses(clustered: pd.DataFrame, stops: list, filter_fn, top_n: int = 3) -> list:
    """
    각 군집에서 stops 조건에 맞는 장소를 하나씩 뽑아
    합산 점수 기준 상위 top_n개 코스를 반환.

    filter_fn(df, category_filters, blog_tag_keywords) → filtered_df
    반환값: [{"course": [place, place, place], "total_score": float}, ...]
    """
    cluster_col = 'Cluster' if 'Cluster' in clustered.columns else None
    cluster_ids = clustered[cluster_col].unique() if cluster_col else [0]

    candidates = []
    globally_used = set()  # 이미 다른 코스에서 선택된 장소 (코스 간 중복 방지)

    for cid in cluster_ids:
        c_df = clustered[clustered[cluster_col] == cid] if cluster_col else clustered

        selected, used_names, total = [], set(globally_used), 0.0
        for stop in stops:
            cands = filter_fn(c_df, stop['category_filters'], stop['blog_tag_keywords'])
            cands = add_scores(cands, stop['blog_tag_keywords'])
            cands = cands[~cands['가게명'].isin(used_names)]
            if cands.empty:
                # 클러스터 내에서 못 찾으면 전체 반경으로 확장
                cands = filter_fn(clustered, stop['category_filters'], stop['blog_tag_keywords'])
                cands = add_scores(cands, stop['blog_tag_keywords'])
                cands = cands[~cands['가게명'].isin(used_names)]
            if cands.empty:
                break
            best_row = cands.nlargest(1, 'score').iloc[0].to_dict()
            selected.append(best_row)
            used_names.add(best_row['가게명'])
            total += best_row['score']

        if len(selected) == 3:
            candidates.append({'course': selected, 'total_score': total})
            globally_used.update(r['가게명'] for r in selected)

    candidates.sort(key=lambda x: x['total_score'], reverse=True)
    if candidates:
        return candidates[:top_n]

    # 클러스터 탐색 실패 시 전체 반경에서 stop별 최고 장소 조합으로 fallback
    def _pick_for_stop(df, stop, used):
        # 1단계: 카테고리 + 태그 필터
        cands = filter_fn(df, stop['category_filters'], stop['blog_tag_keywords'])
        cands = add_scores(cands, stop['blog_tag_keywords'])
        cands = cands[~cands['가게명'].isin(used)]
        if not cands.empty:
            return cands.nlargest(1, 'score').iloc[0].to_dict()
        # 2단계: 카테고리만 (태그 완화)
        cands = filter_fn(df, stop['category_filters'], [])
        cands = add_scores(cands, [])
        cands = cands[~cands['가게명'].isin(used)]
        if not cands.empty:
            return cands.nlargest(1, 'score').iloc[0].to_dict()
        # 3단계: 인기도 순 (카테고리도 없음, 최후 수단)
        cands = add_scores(df, [])
        cands = cands[~cands['가게명'].isin(used)]
        return cands.nlargest(1, 'score').iloc[0].to_dict()

    selected, used_names, total = [], set(), 0.0
    for stop in stops:
        best_row = _pick_for_stop(clustered, stop, used_names)
        selected.append(best_row)
        used_names.add(best_row['가게명'])
        total += best_row['score']

    return [{'course': selected, 'total_score': total}]
