"""Full-pool allocation before quality ranking can hide different venues.

Matching across all requested visits proves zero-reuse feasibility. A reserved
matching prevents a cheap early stop from consuming a later course's only venue.
When that proof fails, min-cost flow minimizes reuse across all courses. Only
when resource limits or unresolved duplicate itineraries prevent certification
do we fall back to a disclosed greedy reuse reduction.
"""
from collections import Counter
import hashlib

from . import course_variety as variety
from . import reviewed_area_policy as areas
from .minimum_reuse import allocate_minimum_reuse


def allocate(pools, count, groups, matching, local_cost, start, seed,
             randomize, recent_place_ids, complete, transport):
    exact = [tuple(groups[p['place_id']] for p in pool) for pool in pools]
    area = [tuple(areas.comparison_key(p, groups[p['place_id']]) for p in pool)
            for pool in pools]
    aliases = {}
    for ids, keys in zip(exact, area):
        for pid, key in zip(ids, keys):
            aliases.setdefault(pid, set()).add(key)
    # A provider/category alias of one exact venue must never become two
    # independent capacity units merely because only one row is area-reviewed.
    area = [tuple(next(iter(aliases[pid])) if len(aliases[pid]) == 1
                  else ('exact_visit', pid) for pid in ids) for ids in exact]
    recent = {groups.get(pid, pid) for pid in recent_place_ids}
    calls = 0

    def match(slots, used=frozenset()):
        nonlocal calls
        calls += 1
        return matching(slots, used)

    # Prefer different tourism areas when possible, but do not confuse an area
    # with venue identity or forbid two distinct venues in a single itinerary.
    all_keys = area * count
    assignment = match(all_keys)
    area_disjoint = assignment is not None
    if assignment is None:
        all_keys = exact * count
        assignment = match(all_keys)
    zero_possible = assignment is not None
    minimum_info = dict(minimum_reuse_certified=True, minimum_reuse_method='disjoint_matching',
                        minimum_reuse_repeated_visits=0)
    if not zero_possible:
        packed, minimum_info = allocate_minimum_reuse(
            pools, count, groups, start, transport, seed, randomize, recent_place_ids)
        if packed is not None:
            for path in packed:
                last, cost = start, 0.0
                for slot, row in enumerate(path):
                    idx = next(i for i, p in enumerate(pools[slot]) if p['place_id'] == row['place_id'])
                    cost += float(local_cost(slot, last, path[:slot])[idx])
                    last = (row['latitude'], row['longitude'])
                complete[variety.signature(path, groups)] = (cost / len(pools), path)
            return packed, dict(zero_overlap_feasible=False, zero_area_overlap_feasible=False,
                allocation_matching_checks=calls, overlap_fallback='minimum_reuse_assignment',
                overlap_reason='insufficient_distinct_eligible_visits', **minimum_info)
    usage, area_usage = Counter(), Counter()
    selected, used, previous = [], set(), []
    remaining = assignment

    def build(keys, remaining, reserved_used, course_index):
        path, cost, last, course_used = [], 0.0, start, set()
        for slot, pool in enumerate(pools):
            offset = course_index * len(pools) + slot if zero_possible else slot
            costs = local_cost(slot, last, path)
            indices = [i for i, pid in enumerate(exact[slot])
                       if pid not in course_used and keys[offset][i] not in reserved_used]
            def reuse(i):
                return usage[exact[slot][i]], area_usage[area[slot][i]]
            # A seed varies similarly priced choices only after reuse priorities.
            buckets = {}
            for i in indices:
                buckets.setdefault(reuse(i), []).append(i)
            ordered = []
            for reuse_key in sorted(buckets):
                choices = sorted(buckets[reuse_key], key=lambda i: (float(costs[i]), pool[i]['place_id']))
                if randomize and choices:
                    ceiling = float(costs[choices[0]]) + variety.RANDOM_WINDOW
                    near = [i for i in choices if float(costs[i]) <= ceiling]
                    rest = [i for i in choices if float(costs[i]) > ceiling]
                    near.sort(key=lambda i: (exact[slot][i] in recent,
                        hashlib.sha256(f'{seed}:{course_index}:{slot}:{exact[slot][i]}'.encode()).hexdigest()))
                    choices = near + rest
                ordered.extend(choices)
            future = set(remaining[1:])
            for idx in ordered:
                key = keys[offset][idx]
                tail = remaining[1:]
                if key in future:
                    tail = match(keys[offset + 1:], reserved_used | {key})
                    if tail is None:
                        continue
                row = pool[idx]
                path.append(row)
                cost += float(costs[idx])
                last = (row['latitude'], row['longitude'])
                course_used.add(exact[slot][idx])
                reserved_used.add(key)
                remaining = tail
                break
            else:
                raise AssertionError('reserved matching must admit a completion')
        return path, cost / len(pools), remaining

    for index in range(count):
        if zero_possible:
            path, cost, remaining = build(all_keys, remaining, used, index)
        else:
            # Full-pool candidate, even when the ordinary beam contains only
            # popular prefixes. The per-course matching still forbids repeats.
            path, cost, _ = build(exact, match(exact), set(), index)
            complete[tuple(groups[p['place_id']] for p in path)] = (cost, path)
            options = [(c, route) for ids, (c, route) in complete.items() if ids not in previous]
            def reuse_key(item):
                route = item[1]
                ids = variety.signature(route, groups)
                compared = variety.comparison_signature(route, groups)
                return (sum(usage[pid] for pid in ids),
                        sum(area_usage[key] for key in compared),
                        max((variety.shared_count(ids, old) for old in previous), default=0))
            best = min(map(reuse_key, options))
            eligible = {variety.signature(route, groups): (c, route)
                        for c, route in options if reuse_key((c, route)) == best}
            path = variety.select(eligible, 1, seed + index, groups, randomize, recent_place_ids)[0]
            cost = eligible[variety.signature(path, groups)][0]
        signature = variety.signature(path, groups)
        complete[signature] = (cost, path)
        selected.append(path)
        previous.append(signature)
        usage.update(signature)
        area_usage.update(variety.comparison_signature(path, groups))
    return selected, dict(zero_overlap_feasible=zero_possible,
                         zero_area_overlap_feasible=area_disjoint,
                         allocation_matching_checks=calls,
                         overlap_fallback=None if zero_possible else 'full_pool_greedy_reuse_reduction',
                         overlap_reason=None if zero_possible else 'insufficient_distinct_eligible_visits',
                         **minimum_info)
