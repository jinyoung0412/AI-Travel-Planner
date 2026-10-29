"""Independent spot quality: each place is measured from the request origin."""
import hashlib
from recommendation_context import context_cost

from .constants import RADIUS_KM
from .course_variety import QUALITY_WINDOW, RANDOM_WINDOW


def cost(row, transport):
    return float(row['origin_distance_km']) / RADIUS_KM[transport] + 1 - float(row['score']) + context_cost(row)


def rank(frame, transport, seed=0, randomize=False):
    result = frame.copy()
    result['_spot_cost'] = [cost(row, transport) for row in result.to_dict('records')]
    result['_spot_order'] = result['_spot_cost']
    if randomize:
        # Bounded jitter changes near-equal choices only. It cannot let a place
        # more than RANDOM_WINDOW worse overtake a better one by randomness.
        result['_spot_order'] += [int(hashlib.sha256(f'{seed}:{pid}'.encode()).hexdigest()[:16], 16)
                                  / 2**64 * RANDOM_WINDOW for pid in result['place_id']]
    return result.sort_values(['_spot_order', '_spot_cost', 'place_id']).drop(columns=['_spot_cost', '_spot_order'])


def metadata(randomize=False, ai_guard=True):
    return dict(policy=('origin_distance_popularity_quality_window_v1' if ai_guard or randomize else
                        'popularity_then_origin_distance_v1'),
                quality_window=QUALITY_WINDOW if ai_guard else None, random_window=RANDOM_WINDOW if randomize else 0,
                randomized=bool(randomize),
                limitation='등록된 인기도·출발점 직선거리와 별도 request_context의 종류별 우선순위를 비교합니다. 취향 정확도나 실제 이동시간 점수가 아닙니다.')


def prefer_new(frame, count, transport, recent_ids, seed=0, randomize=False, exemptions=()):
    """Swap actual visits within the same per-rank quality budget, never filter history.

    History is a soft preference. A constrained or expensive pool may repeat;
    the original required count and brand policy remain available as fallback.
    """
    from .diversity import select_diverse_spots, brand_family
    from .visits import distinct_visits, visit_groups
    baseline, base_policy = select_diverse_spots(rank(frame, transport), count, exemptions)
    ordered = rank(frame, transport, seed, randomize)
    ordinary, ordinary_policy = select_diverse_spots(ordered, count, exemptions)
    groups = visit_groups(frame)
    recent = {groups.get(pid, pid) for pid in recent_ids}
    limits = sorted(cost(row, transport) + QUALITY_WINDOW for row in baseline.to_dict('records'))
    available = distinct_visits(ordered).to_dict('records')
    chosen, seen_brands = [], set()
    if recent:
        for limit in limits:
            options = [r for r in available if cost(r, transport) <= limit + 1e-9]
            if not options:
                break
            def key(row):
                family = brand_family(row)
                return (bool(family and family not in exemptions and family in seen_brands),
                        groups[row['place_id']] in recent,
                        cost(row, transport) + (int(hashlib.sha256(
                            f'{seed}:{row["place_id"]}'.encode()).hexdigest()[:16], 16) / 2**64
                            * RANDOM_WINDOW if randomize else 0), row['place_id'])
            selected = min(options, key=key)
            chosen.append(selected)
            available.remove(selected)
            if brand_family(selected):
                seen_brands.add(brand_family(selected))
    if len(chosen) == len(baseline) and chosen:
        selected, policy = select_diverse_spots(frame.set_index('place_id', drop=False).loc[
            [r['place_id'] for r in chosen]].reset_index(drop=True), count, exemptions)
        if policy['repeated_brand_backfill_count'] > base_policy['repeated_brand_backfill_count']:
            selected, policy = ordinary, ordinary_policy
    else:
        selected, policy = ordinary, ordinary_policy
    selected_groups = {groups[pid] for pid in selected['place_id']}
    info = dict(policy='recent_visits_within_quality_window_v1', recent_count=len(recent),
                repeated_count=len(selected_groups & recent),
                new_count=len(selected_groups - recent),
                eligible_unseen_count=sum(groups[r['place_id']] not in recent for r in distinct_visits(frame).to_dict('records')),
                quality_window_candidate_count=sum(cost(r, transport) <= max(limits, default=-1) + 1e-9
                    for r in distinct_visits(frame).to_dict('records')),
                quality_window_unseen_count=sum(groups[r['place_id']] not in recent and
                    cost(r, transport) <= max(limits, default=-1) + 1e-9
                    for r in distinct_visits(frame).to_dict('records')),
                quality_window=QUALITY_WINDOW, quality_limits=limits)
    # Keep counts measured against the complete candidate pool.
    policy.update({key: value for key, value in base_policy.items() if key in (
        'distinct_candidate_count', 'known_brand_candidate_count', 'known_brand_family_count')})
    return selected, policy, info
