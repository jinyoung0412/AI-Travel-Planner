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
        def _match(tags_json):
            if pd.isna(tags_json):
                return 0.0
            try:
                keys = ' '.join(json.loads(tags_json).keys())
                return sum(1 for kw in blog_tag_keywords if kw in keys) / len(blog_tag_keywords)
            except Exception:
                return 0.0
        df['tag_score'] = df['blog_tags'].apply(_match)
    else:
        df['tag_score'] = 0.0

    df['score'] = 0.4 * df['pop_score'] + 0.6 * df['tag_score']
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


# ── 코스 모드: 군집별 3-stop 선택 ────────────────────────────
def select_course(clustered: pd.DataFrame, stops: list, filter_fn) -> list:
    """
    각 군집에서 stops 조건에 맞는 장소를 하나씩 뽑아
    합산 점수가 가장 높은 군집의 3곳을 반환.

    filter_fn(df, category_filters, blog_tag_keywords) → filtered_df
    """
    cluster_col = 'Cluster' if 'Cluster' in clustered.columns else None
    cluster_ids = clustered[cluster_col].unique() if cluster_col else [0]

    best_score, best_selected = -1.0, None

    for cid in cluster_ids:
        c_df = clustered[clustered[cluster_col] == cid] if cluster_col else clustered

        selected, total = [], 0.0
        for stop in stops:
            cands = filter_fn(c_df, stop['category_filters'], stop['blog_tag_keywords'])
            cands = add_scores(cands, stop['blog_tag_keywords'])
            if cands.empty:
                break
            best_row = cands.nlargest(1, 'score').iloc[0].to_dict()
            selected.append(best_row)
            total += best_row['score']

        if len(selected) == 3 and total > best_score:
            best_score    = total
            best_selected = selected

    return best_selected or []
