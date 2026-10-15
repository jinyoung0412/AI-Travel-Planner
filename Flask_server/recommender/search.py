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

MAX_SLOTS = 16
MAX_COURSES = 100
MAX_BEAM_WIDTH = 1024
EXACT_COMBINATIONS = 4096
BEAM_DISTANCE_BUDGET = 4_000_000
DIVERSITY_PENALTY = 0.08


def _tie(seed, ids):
    return hashlib.sha256(f'{seed}:{"|".join(ids)}'.encode()).hexdigest()


def _matching(pools, used=frozenset()):
    """Return a distinct ID per remaining slot, or prove Hall infeasibility."""
    owner, assigned = {}, [None] * len(pools)

    def assign(slot, seen):
        for pid in pools[slot]:
            if pid in used or pid in seen:
                continue
            seen.add(pid)
            if pid not in owner or assign(owner[pid], seen):
                owner[pid], assigned[slot] = slot, pid
                return True
        return False

    return tuple(assigned) if all(assign(i, set()) for i in range(len(pools))) else None


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


def _select(complete, n, seed):
    selected, selected_ids = [], []
    options = list(complete.values())
    while options and len(selected) < n:
        def rank(item):
            cost, path = item
            ids = {p['place_id'] for p in path}
            overlap = max((len(ids & previous) / len(path) for previous in selected_ids), default=0)
            return cost + DIVERSITY_PENALTY * overlap, _tie(seed, [p['place_id'] for p in path])
        best = min(options, key=rank)
        options.remove(best)
        selected.append(best[1])
        selected_ids.append({p['place_id'] for p in best[1]})
    return selected


def search_courses(df, categories, tags, filter_fn, n=3, start=None,
                   transport='대중교통', seed=0, beam_width=256):
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
    pools = [filter_fn(scored, cats, []).sort_values('place_id').to_dict('records') for cats in categories]
    sizes = [len(pool) for pool in pools]
    info = {'slot_candidate_counts': sizes, 'constraints_relaxed': [], 'seed': int(seed),
            'requested_count': int(n), 'returned_count': 0,
            'search_method': 'beam_with_feasibility_completion',
            'distance_scale_km': RADIUS_KM[transport]}
    if any(size == 0 for size in sizes):
        return [], {**info, 'reason': 'missing_slot_candidates'}
    pool_ids = [tuple(p['place_id'] for p in pool) for pool in pools]
    witness = _matching(pool_ids)
    if witness is None:
        return [], {**info, 'reason': 'insufficient_distinct_places'}
    if start is None:
        start = tuple(clean[['latitude', 'longitude']].mean())
    coords = [np.array([(p['latitude'], p['longitude']) for p in pool]) for pool in pools]
    penalties = [1 - np.array([p['score'] for p in pool]) for pool in pools]
    ties = [np.array([_tie(seed, [pid]) for pid in ids]) for ids in pool_ids]
    radius = RADIUS_KM[transport]
    stats = {'distance_evaluations': 0, 'beam_expansions': 0, 'completion_prefixes': 0,
             'completion_matching_checks': 0, 'beam_distance_evaluations': 0}

    def local_cost(slot, last):
        stats['distance_evaluations'] += sizes[slot]
        return distances_from(last, coords[slot]) / radius + penalties[slot]

    def save(path, cost):
        complete[tuple(p['place_id'] for p in path)] = (cost / len(pools), path)

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
                cost += float(distances_from(last, [coords[slot][idx]])[0] / radius + penalties[slot][idx])
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
                    local = local_cost(slot, last)
                    valid = np.array([pid not in used for pid in pool_ids[slot]])
                    ordered = np.lexsort((ties[slot], local))
                    take = width if slot == 0 else min(width, max(32, int(n) * 4))
                    for idx in ordered[valid[ordered]][:take]:
                        place = pool[int(idx)]
                        stats['beam_expansions'] += 1
                        yield (cost + float(local[idx]), path + [place],
                               used | {place['place_id']}, coords[slot][idx])
            # Keep only width states in memory, even with large n/beam settings.
            next_states = heapq.nsmallest(width, expansions(),
                                         key=lambda s: (s[0], _tie(seed, [p['place_id'] for p in s[1]])))
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
            local = local_cost(slot, last)
            future = set(assignment[1:])
            for idx in np.lexsort((ties[slot], local)):
                place = pools[slot][int(idx)]
                pid = place['place_id']
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

    selected = _select(complete, n, seed)
    info.update(reason=None if len(selected) == n else 'insufficient_unique_courses',
                returned_count=len(selected), candidate_space_exhausted=exhaustive,
                search_stats=stats)
    return selected, info
