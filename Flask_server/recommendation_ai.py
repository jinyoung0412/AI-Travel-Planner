import json, math
import pandas as pd
from geopy.distance import geodesic


# ── 스코어링 ──────────────────────────────────────────────────
def add_scores(df: pd.DataFrame, blog_tag_keywords: list) -> pd.DataFrame:
    """
    인기도와 태그 매칭도를 정규화·가중합하여 각 장소의 최종 추천 점수를 산출한다.

        score = 0.15 × pop_score + 0.85 × tag_score

    - pop_score : 인기도. log(방문자수 + 블로그수×0.3 + 1) 변환 후 Min-Max 정규화.
                  로그 변환은 인기 장소에 점수가 극단적으로 쏠리는 멱법칙 분포를 완화하여,
                  중간 인기도 장소도 의미있는 점수 차이를 갖도록 보정한다.
    - tag_score : 사용자 키워드 중 해당 장소의 블로그 태그에 매칭된 토큰의 비율 (0~1).
    - 가중치 비율(0.15 : 0.85)은 "많이 가는 곳"보다 "내 취향에 맞는 곳"을 우선 추천한다는
      본 시스템의 추천 철학을 반영한 것이다.
    """
    df = df.copy()

    # ── 인기도 점수 (pop_score) ───────────────────────────────
    # +1은 log(0) 방지용. 0.3은 블로그수의 비중을 방문자수보다 낮게 둔 경험적 가중치.
    raw = (df['방문자수'].fillna(0) + df['블로그수'].fillna(0) * 0.3 + 1).apply(math.log)
    mn, mx = raw.min(), raw.max()
    df['pop_score'] = ((raw - mn) / (mx - mn)).clip(0, 1) if mx > mn else 0.0

    # ── 태그 매칭 점수 (tag_score) ────────────────────────────
    # 사용자 키워드를 공백 기준으로 토큰 단위 분해 후, 각 토큰이 블로그 태그에 등장하는지 확인.
    # 매칭된 토큰 수 / 전체 토큰 수 비율을 점수로 사용 → 키워드가 많을수록 부분 매칭 허용.
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

    # ── 최종 점수 (가중합) ────────────────────────────────────
    df['score'] = 0.15 * df['pop_score'] + 0.85 * df['tag_score']
    return df


# ── Greedy TSP ────────────────────────────────────────────────
def greedy_tsp(records: list, start: tuple) -> list:
    """
    탐욕 알고리즘 기반 nearest-neighbor 방식으로 방문 순서를 결정한다.

    출발점(start)에서 시작해, 매 단계마다 미방문 장소 중 현재 위치에서
    측지 거리가 가장 짧은 장소를 다음 목적지로 선택한다.

    엄밀한 외판원 문제(TSP)는 NP-hard이지만, 추천 결과의 장소 수가 5개 내외로 적기 때문에
    탐욕적 nearest-neighbor 방식으로도 실용적인 동선을 충분히 산출할 수 있다.
    """
    route, current, remaining = [], start, list(records)
    while remaining:
        # 현재 위치에서 가장 가까운 미방문 장소 선택
        nearest = min(
            remaining,
            key=lambda p: geodesic(current, (p['latitude'], p['longitude'])).kilometers,
        )
        route.append(nearest)
        remaining.remove(nearest)
        # 다음 반복은 방금 방문한 장소를 기준점으로
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
    사용자 정의 슬롯 순서대로 코스를 생성한다 (코스 추천 모드 ①).

    예) slot_types = ['음식', '카페', '자연·산책'] →
        음식 카테고리 1곳 → 카페 1곳 → 자연·산책 1곳 순으로 코스 구성.

    설계 핵심:
    - 군집 우선 탐색: 각 코스는 가급적 단일 군집(Cluster) 내에서만 구성하여 지리적 응집성 확보.
      군집 안에서 적합한 장소가 없으면 전체 후보에서 fallback 탐색.
    - 코스 내·코스 간 장소 중복 방지: used_names(코스 내) + globally_used(코스 간) 두 단계로 추적.
    - 슬롯별 SLOT_CATEGORY_MAP을 통해 사용자의 한국어 슬롯명을 DB 카테고리 키워드로 매핑.
    """
    if not slot_types:
        return []

    cluster_col = 'Cluster' if 'Cluster' in df.columns else None
    # 군집화가 적용된 경우, 장소가 많은 군집부터 순회하여 후보 풍부도 확보
    cluster_ids = df[cluster_col].value_counts().index.tolist() if cluster_col else [None] * n

    courses = []
    globally_used = set()  # 이미 다른 코스에서 선택된 장소 (코스 간 중복 방지)

    for i, cid in enumerate(cluster_ids):
        if len(courses) >= n:
            break

        c_df = df[df[cluster_col] == cid] if cid is not None else df
        used_names = set(globally_used)  # 이 코스 내에서 사용된 장소 (코스 내 중복 방지)
        course = []
        ok = True

        for slot in slot_types:
            cats = SLOT_CATEGORY_MAP.get(slot, [])
            # 1차: 현재 군집 내 탐색
            place = _pick_best(c_df, cats, blog_tag_keywords, filter_fn, used_names)
            # 2차 fallback: 군집 내 없으면 전체 후보에서 탐색
            if place is None:
                place = _pick_best(df, cats, blog_tag_keywords, filter_fn, used_names)
            if place is None:
                ok = False  # 한 슬롯이라도 후보를 못 찾으면 이 코스 폐기
                break
            course.append(place)
            used_names.add(place['가게명'])

        if ok:
            courses.append(course)
            globally_used.update(p['가게명'] for p in course)

    return courses


def generate_fixed_courses(df, blog_tag_keywords, filter_fn, n: int = 3, spots: int = 5):
    """
    표준 당일 여행 패턴 기반 고정 템플릿 코스 생성 (코스 추천 모드 ②).

    사용자가 슬롯 순서를 직접 지정하지 않은 경우 자동 적용되는 모드.
    spots 파라미터로 코스 길이를 조절:
        - 3 stops: 음식 → 활동 → 카페
        - 4 stops: 음식 → 활동 → 카페 → 활동
        - 5 stops: 음식 → 활동 → 카페 → 활동 → 음식 (점심·저녁 + 카페)

    설계 핵심:
    - 군집 우선 + 전체 fallback: generate_from_slots와 동일한 패턴.
    - 활동 그룹 다양성: 한 코스 내 두 활동 슬롯(stop2·stop4)이 서로 다른 활동 그룹에서 선택되도록
      _COURSE_ACT_PAIRS로 사전 정의된 페어를 사용. 또한 코스마다 다른 페어를 할당하여
      여러 코스가 모두 같은 패턴이 되는 단조로움을 방지.
    - 음식 카테고리 중복 방지: 두 음식 슬롯(stop1·stop5)이 같은 한식·중식 같은 동일 대분류로
      겹치지 않도록 used_food_cats로 추적하여 두 번째 음식 선택 시 제외.
    """
    cluster_col = 'Cluster' if 'Cluster' in df.columns else None

    if cluster_col:
        cluster_ids = df[cluster_col].value_counts().index.tolist()
    else:
        cluster_ids = [None] * n

    courses = []
    globally_used = set()  # 코스 간 장소 중복 방지

    for i, cid in enumerate(cluster_ids):
        if len(courses) >= n or i >= len(_COURSE_ACT_PAIRS):
            break

        # 코스마다 다른 활동 그룹 페어 할당 → 여러 코스의 활동 다양성 확보
        act_idx1, act_idx2 = _COURSE_ACT_PAIRS[i]
        c_df = df[df[cluster_col] == cid] if cid is not None else df
        used_names = set(globally_used)
        used_food_cats: set = set()  # 이 코스에서 이미 사용된 음식 대분류 (중복 방지용)
        course = []

        def pick(cats, tags, _c=c_df, _full=df, _used=used_names):
            """군집 내 우선 탐색 → 실패 시 전체 후보로 fallback."""
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
        used_food_cats.update(_matched_food_cats(food1))  # Stop 5에서 동일 카테고리 회피용

        # Stop 2: 활동 (할당된 첫 번째 활동 그룹)
        act1 = pick(_ACTIVITY_GROUPS[act_idx1], blog_tag_keywords)
        # 1차 그룹에 후보가 없으면 다른 그룹에서 fallback 탐색
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

        # Stop 4: 활동 (할당된 두 번째 활동 그룹, Stop 2와 다른 그룹)
        act2 = pick(_ACTIVITY_GROUPS[act_idx2], blog_tag_keywords)
        # fallback 시에도 Stop 2와 Stop 4가 동일 그룹이 되는 것을 회피
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

        # Stop 5: 음식점 (Stop 1과 다른 음식 카테고리에서 선택)
        # used_food_cats(이미 사용된 음식 대분류)를 제외한 후보군으로 탐색.
        # 모든 카테고리가 사용된 극단적 경우에만 전체 FOOD_CATS로 fallback.
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
