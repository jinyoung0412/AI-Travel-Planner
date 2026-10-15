"""Slot-constrained, origin-aware route search using coordinate distances.

Clusters never restrict the number of courses. Beam search ranks combinations;
an injective-assignment DFS fills any count shortfall without relaxing slots.
Distances are great-circle estimates, never road/transit times.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from place_identity import ensure_ids

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


def add_scores(df, blog_tag_keywords):
    result = df.copy()
    def numeric(col):
        return pd.to_numeric(result.get(col, pd.Series(0, index=result.index)),
                             errors='coerce').fillna(0).clip(lower=0)
    raw = np.log1p(numeric('방문자수') + numeric('블로그수'))
    spread = raw.max() - raw.min()
    result['pop_score'] = (raw - raw.min()) / spread if spread > 0 else 0.0
    tokens = sorted({tok.lower() for kw in blog_tag_keywords for tok in kw.split() if tok})
    def match(tags):
        try:
            parsed = json.loads(tags) if isinstance(tags, str) else tags
            keys = ' '.join(parsed.keys()).lower() if isinstance(parsed, dict) else ''
            return sum(tok in keys for tok in tokens) / len(tokens) if tokens else 0.0
        except (TypeError, ValueError):
            return 0.0
    verified = result.get('blog_tag_status', pd.Series('', index=result.index)).eq('verified')
    result['tag_score'] = result.get('blog_tags', pd.Series('{}', index=result.index)).where(verified, '{}').map(match)
    # Equal bounded signals; no match evidence => popularity alone. Product
    # defaults, not learned weights. Both remain available in the scored DataFrame.
    result['score'] = ((result['pop_score'] + result['tag_score']) / 2
                       if result['tag_score'].gt(0).any() else result['pop_score'])
    return result


def distances_from(start, coordinates):
    coordinates = np.asarray(coordinates, dtype=float).reshape(-1, 2)
    a = np.radians(np.asarray(start, dtype=float))
    b = np.radians(coordinates)
    d = b - a
    h = np.sin(d[:, 0] / 2)**2 + np.cos(a[0]) * np.cos(b[:, 0]) * np.sin(d[:, 1] / 2)**2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def route_metrics(course, start):
    current, legs = start, []
    for p in course:
        point = (p['latitude'], p['longitude'])
        legs.append(float(distances_from(current, [point])[0]))
        current = point
    return {'distance_method': 'coordinate_great_circle',
            'estimated_distance_km': round(sum(legs), 3),
            'leg_distances_km': [round(x, 3) for x in legs],
            'travel_time_minutes': None}


def greedy_tsp(records, start):
    remaining, route = list(records), []
    while remaining:
        idx = int(np.argmin(distances_from(start, [(p['latitude'], p['longitude']) for p in remaining])))
        p = remaining.pop(idx)
        route.append(p)
        start = (p['latitude'], p['longitude'])
    return route


def _can_assign(pools, used=frozenset()):
    """Small bipartite matching: detects overlapping-slot impossibility."""
    owner = {}
    def assign(slot, seen):
        for p in pools[slot]:
            pid = p['place_id']
            if pid in used or pid in seen:
                continue
            seen.add(pid)
            if pid not in owner or assign(owner[pid], seen):
                owner[pid] = slot
                return True
        return False
    return all(assign(i, set()) for i in range(len(pools)))


def _tie(seed, ids):
    return hashlib.sha256(f'{seed}:{"|".join(ids)}'.encode()).hexdigest()


def search_courses(df, categories, tags, filter_fn, n=3, start=None,
                   transport='대중교통', seed=0, beam_width=256):
    if n < 1 or not categories or any(not c for c in categories):
        return [], {'reason': 'invalid_slots', 'constraints_relaxed': []}
    clean = ensure_ids(df).drop_duplicates('place_id').copy()
    for c in ('latitude', 'longitude'):
        clean[c] = pd.to_numeric(clean.get(c, pd.Series(dtype=float)), errors='coerce')
    clean = clean[np.isfinite(clean['latitude']) & np.isfinite(clean['longitude']) &
                  clean['latitude'].between(-90, 90) & clean['longitude'].between(-180, 180)]
    scored = add_scores(clean, tags)
    # Tags are ranking hints; calling the filter with [] enforces categories only.
    pools = [filter_fn(scored, cats, []).sort_values('place_id').to_dict('records') for cats in categories]
    sizes = [len(p) for p in pools]
    info = {'slot_candidate_counts': sizes, 'constraints_relaxed': [],
            'seed': seed, 'search_method': 'beam_with_feasibility_completion'}
    if any(s == 0 for s in sizes):
        return [], {**info, 'reason': 'missing_slot_candidates'}
    if not _can_assign(pools):
        return [], {**info, 'reason': 'insufficient_distinct_places'}
    if start is None:
        # Compatibility for standalone callers; API always supplies origin.
        start = tuple(clean[['latitude', 'longitude']].mean())
    radius = RADIUS_KM[transport]
    width = max(beam_width, n)
    coords = [np.array([(p['latitude'], p['longitude']) for p in pool]) for pool in pools]
    scores = [np.array([p['score'] for p in pool]) for pool in pools]
    # state = (objective sum, path, used IDs, last coordinates)
    states = [(0.0, [], frozenset(), start)]
    for slot, pool in enumerate(pools):
        expanded = []
        for cost, path, used, last in states:
            distance = distances_from(last, coords[slot])
            local_cost = distance / radius + (1 - scores[slot])
            valid = np.array([p['place_id'] not in used for p in pool])
            indices = np.flatnonzero(valid)
            take = width if slot == 0 else max(32, n * 4)
            # Stable sort makes a zero-score/zero-distance pool reproducible.
            best = indices[np.argsort(local_cost[indices], kind='stable')[:take]]
            for idx in best:
                p = pool[int(idx)]
                expanded.append((cost + float(local_cost[idx]), path + [p],
                                 used | {p['place_id']}, tuple(coords[slot][idx])))
        expanded.sort(key=lambda s: (s[0], _tie(seed, [p['place_id'] for p in s[1]])))
        states = expanded[:width]
        if not states:
            break
    complete = {tuple(p['place_id'] for p in path): (cost / len(categories), path)
                for cost, path, _, _ in states if len(path) == len(categories)}
    # If pruning lost a feasible route/count, explore full pools with a matching
    # oracle. Stop after n unique valid courses; never infer impossibility from beam.
    if len(complete) < n:
        def visit(slot, path, used, last, cost):
            if len(complete) >= n:
                return
            if slot == len(pools):
                complete[tuple(p['place_id'] for p in path)] = (cost / len(pools), path)
                return
            if not _can_assign(pools[slot:], used):
                return
            local = distances_from(last, coords[slot]) / radius + (1 - scores[slot])
            for idx in np.argsort(local, kind='stable'):
                p = pools[slot][int(idx)]
                if p['place_id'] not in used:
                    visit(slot + 1, path + [p], used | {p['place_id']},
                          tuple(coords[slot][idx]), cost + float(local[idx]))
                if len(complete) >= n:
                    return
        visit(0, [], frozenset(), start, 0.0)
    selected, options = [], list(complete.values())
    while options and len(selected) < n:
        def rank(item):
            cost, path = item
            ids = {p['place_id'] for p in path}
            overlap = max((len(ids & {p['place_id'] for p in prev}) / len(path)
                           for prev in selected), default=0)
            return cost + 0.08 * overlap, _tie(seed, [p['place_id'] for p in path])
        best = min(options, key=rank)
        options.remove(best)
        selected.append(best[1])
    info.update(reason=None if len(selected) == n else 'insufficient_unique_courses',
                requested_count=n, returned_count=len(selected))
    return selected, info


def generate_from_slots(df, slot_types, blog_tag_keywords, filter_fn, n=3,
                        start=None, transport='대중교통', seed=0):
    categories = [SLOT_CATEGORY_MAP.get(slot, []) for slot in slot_types]
    return search_courses(df, categories, blog_tag_keywords, filter_fn, n, start, transport, seed)[0]


def fixed_categories(spots):
    if spots not in (3, 4, 5):
        raise ValueError('spot_count는 3~5이어야 합니다.')
    return [FOOD_CATS, ACTIVITY_CATS, CAFE_CATS, ACTIVITY_CATS, FOOD_CATS][:spots]


def generate_fixed_courses(df, blog_tag_keywords, filter_fn, n=3, spots=5,
                           start=None, transport='대중교통', seed=0):
    return search_courses(df, fixed_categories(spots), blog_tag_keywords, filter_fn,
                          n, start, transport, seed)[0]


def find_best_for_plan(df, stops, filter_fn, start=None):
    tags = list(dict.fromkeys(t for stop in stops for t in stop.get('blog_tag_keywords', [])))
    courses, _ = search_courses(df, [s['category_filters'] for s in stops], tags, filter_fn, 1, start)
    return courses[0] if courses else []


def select_courses(clustered, stops, filter_fn, top_n=3, start=None):
    tags = list(dict.fromkeys(t for s in stops for t in s.get('blog_tag_keywords', [])))
    courses, _ = search_courses(clustered, [s['category_filters'] for s in stops], tags,
                               filter_fn, top_n, start)
    return [{'course': c, 'total_score': sum(p['score'] for p in c)} for c in courses]
