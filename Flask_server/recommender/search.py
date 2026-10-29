"""Ordered-slot search with bounded beam memory and feasible completion.

Callers scope candidates (for example by origin radius) before search. Radius is
only a kilometre cost scale here, not a per-leg limit. Slots are never reordered.
"""
import hashlib
import heapq
import itertools
import math
from numbers import Integral

import numpy as np
import pandas as pd

from place_identity import ensure_ids
from .constants import RADIUS_KM
from .geometry import distances_from
from .scoring import add_scores
from .visits import distinct_visits, visit_groups
from . import course_variety
from .disjoint_courses import allocate
from . import route_coherence
from recommendation_context import context_cost

MAX_SLOTS = 16
MAX_COURSES = 100
MAX_BEAM_WIDTH = 1024
EXACT_COMBINATIONS = 4096
BEAM_DISTANCE_BUDGET = 4_000_000


def _tie(seed, ids):
    return hashlib.sha256(f'{seed}:{"|".join(ids)}'.encode()).hexdigest()


def _matching(pools, used=frozenset()):
    """Return a distinct visit key per remaining slot, or prove Hall infeasibility."""
    from collections import deque
    owner, assigned = {}, [None] * len(pools)
    for root in range(len(pools)):
        queue, parent, visited = deque([root]), {}, {root}
        free = None
        while queue and free is None:
            slot = queue.popleft()
            for pid in pools[slot]:
                if pid in used or pid in parent:
                    continue
                parent[pid] = slot
                if pid not in owner:
                    free = pid
                    break
                other = owner[pid]
                if other not in visited:
                    visited.add(other)
                    queue.append(other)
        if free is None:
            return None
        while free is not None:
            slot = parent[free]
            previous = assigned[slot]
            owner[free], assigned[slot] = slot, free
            free = previous
    return tuple(assigned)


def _validate(categories, n, start, transport, seed, beam_width):
    if (isinstance(n, bool) or not isinstance(n, Integral) or n < 1 or
            not isinstance(categories, (list, tuple)) or not categories or
            any(not isinstance(cats, (list, tuple)) or not cats or
                any(not isinstance(cat, str) or not cat.strip() for cat in cats)
                for cats in categories)):
        return False
    if n > MAX_COURSES or len(categories) > MAX_SLOTS:
        raise ValueError(f'최대 {MAX_COURSES}개 코스, {MAX_SLOTS}개 슬롯을 지원합니다.')
    if (isinstance(beam_width, bool) or not isinstance(beam_width, Integral) or
            not 1 <= beam_width <= MAX_BEAM_WIDTH):
        raise ValueError(f'beam_width는 1~{MAX_BEAM_WIDTH} 정수여야 합니다.')
    if not isinstance(transport, str) or transport not in RADIUS_KM:
        raise ValueError('transport는 차 또는 대중교통이어야 합니다.')
    if isinstance(seed, bool) or not isinstance(seed, Integral):
        raise ValueError('seed는 정수여야 합니다.')
    if start is not None:
        try:
            point = np.asarray(start, dtype=float)
            valid = (point.shape == (2,) and np.isfinite(point).all() and
                     -90 <= point[0] <= 90 and -180 <= point[1] <= 180)
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise ValueError('start는 유효한 위도·경도여야 합니다.')
    return True


def _select(complete, n, seed, groups, randomize=False, recent_place_ids=()):
    return course_variety.select(complete, n, seed, groups, randomize, recent_place_ids)


def search_courses(df, categories, tags, filter_fn, n=3, start=None,
                   transport='대중교통', seed=0, beam_width=256, randomize=False, recent_place_ids=()):
    if type(randomize) is not bool:
        raise ValueError('randomize는 참 또는 거짓이어야 합니다.')
    if not _validate(categories, n, start, transport, seed, beam_width):
        return [], {'reason': 'invalid_slots', 'constraints_relaxed': []}
    clean = df.copy()
    for column in ('latitude', 'longitude'):
        clean[column] = pd.to_numeric(clean.get(column, pd.Series(index=clean.index, dtype=float)),
                                      errors='coerce')
    clean = clean[clean['latitude'].between(-90, 90) & clean['longitude'].between(-180, 180)]
    # Reject unusable coordinates before deduplicating identities: a corrupt old
    # row must not hide another usable row for the same provider place.
    clean = ensure_ids(clean).drop_duplicates('place_id')
    scored = add_scores(clean, tags)
    groups = visit_groups(scored)
    # Collapse variants within each slot, rather than across all categories: a
    # duplicate row with a different category must not hide a feasible slot.
    pools = [distinct_visits(filter_fn(scored, cats, []).sort_values(
        ['score', 'place_id'], ascending=[False, True])).sort_values('place_id').to_dict('records')
        for cats in categories]
    sizes = [len(pool) for pool in pools]
    info = {'slot_candidate_counts': sizes, 'constraints_relaxed': [], 'seed': int(seed),
            'requested_count': int(n), 'returned_count': 0,
            'search_method': 'beam_with_feasibility_completion',
            'distance_scale_km': RADIUS_KM[transport]}
    if any(size == 0 for size in sizes):
        return [], {**info, 'reason': 'missing_slot_candidates'}
    pool_ids = [tuple(groups[p['place_id']] for p in pool) for pool in pools]
    witness = _matching(pool_ids)
    if witness is None:
        return [], {**info, 'reason': 'insufficient_distinct_places'}
    if start is None:
        start = tuple(clean[['latitude', 'longitude']].mean())
    coords = [np.array([(p['latitude'], p['longitude']) for p in pool]) for pool in pools]
    penalties = [1 - np.array([p['score'] for p in pool]) +
                 np.array([context_cost(p) for p in pool]) for pool in pools]
    ties = [np.array([_tie(seed, [pid]) for pid in ids]) for ids in pool_ids]
    radius = RADIUS_KM[transport]
    stats = {'distance_evaluations': 0, 'beam_expansions': 0, 'completion_prefixes': 0,
             'completion_matching_checks': 0, 'beam_distance_evaluations': 0}

    def local_cost(slot, last, path=()):
        stats['distance_evaluations'] += sizes[slot]
        prefix = [start] + [(row['latitude'], row['longitude']) for row in path]
        return (distances_from(last, coords[slot]) / radius + penalties[slot] +
                route_coherence.extension(prefix, coords[slot], transport))

    def save(path, cost):
        complete[tuple(groups[p['place_id']] for p in path)] = (cost / len(pools), path)

    complete = {}
    exhaustive = math.prod(sizes) <= EXACT_COMBINATIONS
    if exhaustive:
        # This small, bounded path is also an oracle for beam regressions.
        for indices in itertools.product(*(range(size) for size in sizes)):
            ids = [pool_ids[slot][idx] for slot, idx in enumerate(indices)]
            if len(set(ids)) != len(ids):
                continue
            last, cost, path = start, 0.0, []
            for slot, idx in enumerate(indices):
                stats['distance_evaluations'] += 1
                prefix = [start] + [(row['latitude'], row['longitude']) for row in path]
                cost += float(distances_from(last, [coords[slot][idx]])[0] / radius + penalties[slot][idx] +
                              route_coherence.extension(prefix, [coords[slot][idx]], transport)[0])
                path.append(pools[slot][idx])
                last = coords[slot][idx]
            save(path, cost)
        info['search_method'] = 'exhaustive'
    else:
        # At least one state scans each pool. Beyond that unavoidable input cost,
        # candidate volume reduces width so distance work stays within the budget.
        width = min(max(int(beam_width), int(n)), max(1, BEAM_DISTANCE_BUDGET // sum(sizes)))
        info['effective_beam_width'] = width
        states = [(0.0, [], frozenset(), start)]
        for slot, pool in enumerate(pools):
            def expansions():
                for cost, path, used, last in states:
                    local = local_cost(slot, last, path)
                    valid = np.array([pid not in used for pid in pool_ids[slot]])
                    ordered = np.lexsort((ties[slot], local))
                    take = width if slot == 0 else min(width, max(32, int(n) * 4))
                    for idx in ordered[valid[ordered]][:take]:
                        place = pool[int(idx)]
                        stats['beam_expansions'] += 1
                        yield (cost + float(local[idx]), path + [place],
                               used | {groups[place['place_id']]}, coords[slot][idx])
            # Keep only width states in memory, even with large n/beam settings.
            def state_key(state):
                return state[0], _tie(seed, [groups[p['place_id']] for p in state[1]])

            # Reserve room for different earlier visits: a popular prefix must
            # not consume the whole beam with only its last cafe changing.
            prefixes = {}
            def diverse_expansions():
                for state in expansions():
                    prefix = tuple(groups[p['place_id']] for p in state[1][:-1])
                    if prefix not in prefixes or state_key(state) < state_key(prefixes[prefix]):
                        prefixes[prefix] = state
                    yield state
            next_states = heapq.nsmallest(width, diverse_expansions(), key=state_key)
            if n > 1 and len(prefixes) > 1:
                reserved = heapq.nsmallest(width // 2, prefixes.values(), key=state_key)
                primary = next_states[:width - len(reserved)]
                seen = {tuple(groups[p['place_id']] for p in state[1]) for state in primary}
                for state in reserved + next_states:
                    ids = tuple(groups[p['place_id']] for p in state[1])
                    if ids not in seen and len(primary) < width:
                        primary.append(state); seen.add(ids)
                next_states = primary
            states = next_states
            if not states:
                break
        for cost, path, _, _ in states:
            if len(path) == len(pools):
                save(path, cost)
        stats['beam_distance_evaluations'] = stats['distance_evaluations']

        def visit(slot, path, used, last, cost, assignment):
            stats['completion_prefixes'] += 1
            if slot == len(pools):
                save(path, cost)
                return
            local = local_cost(slot, last, path)
            future = set(assignment[1:])
            for idx in np.lexsort((ties[slot], local)):
                place = pools[slot][int(idx)]
                pid = groups[place['place_id']]
                if pid in used:
                    continue
                remaining = assignment[1:]
                # Only choosing a future witness ID can break feasibility. All
                # other candidates already have a matching for the suffix, so
                # successful prefixes always reach a leaf (no factorial retry).
                if pid in future:
                    stats['completion_matching_checks'] += 1
                    remaining = _matching(pool_ids[slot + 1:], used | {pid})
                    if remaining is None:
                        continue
                visit(slot + 1, path + [place], used | {pid}, coords[slot][idx],
                      cost + float(local[idx]), remaining)
                if len(complete) >= n:
                    return

        if len(complete) < n:
            visit(0, [], frozenset(), start, 0.0, witness)
            exhaustive = len(complete) < n

    selected = _select(complete, n, seed, groups, randomize, recent_place_ids)
    allocation = {}
    if len(selected) > 1:
        selected, allocation = allocate(pools, len(selected), groups, _matching,
            local_cost, start, seed, randomize, recent_place_ids, complete, transport)
    from .route_refinement import improve
    selected, refinement = improve(selected, pools, groups, start, transport, recent_place_ids, randomize)
    for path in selected:
        complete[tuple(groups[p['place_id']] for p in path)] = (
            route_coherence.route_cost(path, start, transport), path)
    best_cost = min(cost for cost, _ in complete.values()) if complete else None
    selected_keys = {tuple(groups[p['place_id']] for p in path) for path in selected}
    selected_costs = [cost for key, (cost, _) in complete.items() if key in selected_keys]
    info.update(reason=None if len(selected) == n else 'insufficient_unique_courses',
                returned_count=len(selected), candidate_space_exhausted=exhaustive,
                search_stats=stats, best_route_cost=best_cost,
                route_coherence={**route_coherence.metadata(selected, start, transport), **refinement},
                quality_limit=(max(best_cost + course_variety.QUALITY_WINDOW, max(selected_costs))
                               if selected_costs else None),
                course_diversity={**course_variety.course_summary(selected, groups, randomize),
                                  **allocation})
    recent = {groups.get(pid, pid) for pid in recent_place_ids}
    selected_ids = {groups[p['place_id']] for path in selected for p in path}
    info['recommendation_variation'] = dict(policy='recent_visits_within_quality_window_v1',
        recent_count=len(recent), repeated_count=len(selected_ids & recent),
        new_count=len(selected_ids - recent), evaluated_route_count=len(complete),
        candidate_space_exhausted=exhaustive)
    return selected, info
