"""Bounded ordered-slot refinement after full-pool reuse allocation.

Only replace a venue in its existing slot or exchange the same slot across two
courses. Exact reuse/balance, area reuse, history and per-course quality budgets
cannot get worse. Flow's minimum-reuse certificate therefore remains valid.
"""
from collections import Counter

import numpy as np

from .geometry import distances_from
from . import course_variety, route_coherence
from . import reviewed_area_policy as areas
from .constants import RADIUS_KM
from recommendation_context import context_cost

MAX_EVALUATIONS = 1200
MAX_SHORTLIST_SCANS = 100_000
MAX_PASSES = 2
SHORTLIST = 12
RELEVANCE_WINDOW = .10


def improve(routes, pools, groups, start, transport, recent_place_ids=(), randomize=False):
    selected = [list(route) for route in routes]
    info = dict(refinement_policy='fixed_slots_reuse_preserving_v1',
                refinement_evaluations=0, refinement_moves=0,
                refinement_shortlist_scans=0, refinement_work_limited=False)
    if not selected or any(route_coherence.coordinates(path) is None for path in selected):
        return selected, info
    recent = {groups.get(pid, pid) for pid in recent_place_ids}
    signature = lambda path: tuple(groups[row['place_id']] for row in path)

    def overlap(paths):
        exact = Counter(pid for path in paths for pid in signature(path))
        compared = Counter(areas.comparison_key(row, groups[row['place_id']])
                           for path in paths for row in path)
        return (sum(exact.values()) - len(exact), sum(n*(n-1)//2 for n in exact.values()),
                sum(compared.values()) - len(compared), sum(n*(n-1)//2 for n in compared.values()))

    def history(paths):
        return sum(pid in recent for path in paths for pid in signature(path))

    def relevance(path):
        return sum(1 - float(row.get('score', 0)) + context_cost(row) for row in path) / len(path)

    originals = [route_coherence.route_cost(path, start, transport, geometry=False) for path in selected]
    relevance_limits = [relevance(path) + RELEVANCE_WINDOW for path in selected]
    costs = [route_coherence.route_cost(path, start, transport) for path in selected]
    before_cost = sum(costs)
    allowed_overlap, allowed_history = overlap(selected), history(selected)

    def consider(changes):
        if info['refinement_evaluations'] >= MAX_EVALUATIONS:
            info['refinement_work_limited'] = True
            return False
        info['refinement_evaluations'] += 1
        replacement_costs = {}
        for index, path in changes.items():
            if len(set(signature(path))) != len(path):
                return False
            if relevance(path) > relevance_limits[index] + 1e-9:
                return False
            if route_coherence.route_cost(path, start, transport, geometry=False) > originals[index] + course_variety.QUALITY_WINDOW + 1e-9:
                return False
            replacement_costs[index] = route_coherence.route_cost(path, start, transport)
        gain = sum(costs[i] - value for i, value in replacement_costs.items())
        # Strict improvements only: identical geometry retains seeded choices.
        if gain <= 1e-8:
            return False
        if randomize:
            # Do not turn every seed's near-equal itinerary into the same local
            # optimum. Refine seeded choices only for a material objective
            # gain AND a clear coordinate detour reduction.
            geometry_gain = sum(route_coherence.penalty(selected[i], start, transport) -
                                route_coherence.penalty(path, start, transport)
                                for i, path in changes.items())
            if (gain <= course_variety.RANDOM_WINDOW / 2 * len(changes) or
                    geometry_gain <= .005 * len(changes)):
                return False
        proposed = [changes.get(i, path) for i, path in enumerate(selected)]
        if len({signature(path) for path in proposed}) != len(proposed):
            return False
        if any(after > limit for after, limit in zip(overlap(proposed), allowed_overlap)):
            return False
        if recent and history(proposed) > allowed_history:
            return False
        for index, path in changes.items():
            selected[index], costs[index] = path, replacement_costs[index]
        info['refinement_moves'] += 1
        return True

    for _ in range(MAX_PASSES):
        moves = info['refinement_moves']
        for index in range(len(selected)):
            for slot, pool in enumerate(pools):
                if info['refinement_evaluations'] >= MAX_EVALUATIONS:
                    break
                if info['refinement_shortlist_scans'] + len(pool) > MAX_SHORTLIST_SCANS:
                    info['refinement_work_limited'] = True
                    continue
                info['refinement_shortlist_scans'] += len(pool)
                path = selected[index]
                previous = start if slot == 0 else (path[slot-1]['latitude'], path[slot-1]['longitude'])
                coordinates = [(row['latitude'], row['longitude']) for row in pool]
                quality = np.array([1-float(row.get('score', 0)) + context_cost(row) for row in pool])
                local = distances_from(previous, coordinates) / RADIUS_KM[transport] + quality
                if slot + 1 < len(path):
                    following = (path[slot+1]['latitude'], path[slot+1]['longitude'])
                    local += distances_from(following, coordinates) / RADIUS_KM[transport]
                indices = sorted(range(len(pool)), key=lambda i: (float(local[i]), pool[i]['place_id']))[:SHORTLIST]
                # Include the most relevant venues even if neighbouring stops
                # are far away. This shortlist limits refinement work only;
                # full-pool feasibility/allocation has already completed.
                indices += sorted(range(len(pool)), key=lambda i: (float(quality[i]), pool[i]['place_id']))[:SHORTLIST//2]
                for candidate in dict.fromkeys(indices):
                    replacement = list(selected[index])
                    replacement[slot] = pool[candidate]
                    consider({index: replacement})
        # Flow allocates venue-use totals without route geometry. Same-slot
        # exchanges improve its grouping while preserving those totals exactly.
        for a in range(len(selected)):
            for b in range(a + 1, len(selected)):
                for slot in range(len(pools)):
                    if info['refinement_evaluations'] >= MAX_EVALUATIONS:
                        info['refinement_work_limited'] = True
                        break
                    first, second = list(selected[a]), list(selected[b])
                    first[slot], second[slot] = second[slot], first[slot]
                    consider({a: first, b: second})
        if info['refinement_moves'] == moves or info['refinement_evaluations'] >= MAX_EVALUATIONS:
            break
    info.update(refinement_objective_before=round(before_cost, 8),
                refinement_objective_after=round(sum(costs), 8))
    return selected, info
