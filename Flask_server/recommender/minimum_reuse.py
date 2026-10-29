"""Exact repeat minimization without expanding or truncating eligible pools.

Flow assigns every (course, slot) through a capacity-one (course, exact visit)
node. A global visit's first use is free and later uses cost one at the primary
objective. Increasing secondary costs balance unavoidable uses. Static candidate
quality only breaks those ties; it is not a route-distance optimization.
"""
import hashlib
import heapq
import math
from collections import deque

from .constants import RADIUS_KM
from recommendation_context import context_cost

MAX_NODES = 40_000
MAX_FORWARD_EDGES = 120_000
MAX_SCANNED_EDGES = 2_000_000
MAX_REPAIR_MOVES = 10_000
QUALITY_SCALE = 10_000


def _origin_distance(start, row):
    lat1, lon1, lat2, lon2 = map(math.radians, (*start, row['latitude'], row['longitude']))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1., max(0., h))))


def allocate_minimum_reuse(pools, count, groups, start, transport, seed=0,
                           randomize=False, recent_place_ids=()):
    """Return ``(routes, metadata)``; ``routes=None`` declines certification.

    Resource limits reject the entire problem, never discard candidates. A
    solution with duplicate ordered courses receives a bounded permutation
    repair preserving all visit-use totals. If repair fails, it is declined;
    uniqueness of complete courses is not represented by the flow network.
    The caller may use a separately disclosed heuristic in either case.
    """
    info = dict(minimum_reuse_method='min_cost_flow_v1',
                minimum_reuse_certified=False,
                minimum_reuse_quality_objective='origin_distance_popularity_context',
                minimum_reuse_resource_limits=dict(nodes=MAX_NODES,
                    forward_edges=MAX_FORWARD_EDGES, scanned_edges=MAX_SCANNED_EDGES,
                    duplicate_repair_moves=MAX_REPAIR_MOVES))

    def decline(reason):
        return None, {**info, 'minimum_reuse_reason': reason}

    if not pools or count < 1 or any(not pool for pool in pools):
        return decline('missing_slot_candidates')
    visits = count * len(pools)
    recent = {groups.get(pid, pid) for pid in recent_place_ids}
    choices, all_keys = [], set()
    try:
        for slot, pool in enumerate(pools):
            by_key = {}
            for row in pool:
                key = groups[row['place_id']]
                quality = (_origin_distance(start, row) / RADIUS_KM[transport]
                           + 1 - float(row.get('score', 0.)) + context_cost(row))
                if not math.isfinite(quality):
                    return decline('invalid_candidate_quality')
                if randomize:
                    fraction = int(hashlib.sha256(f'{seed}:{slot}:{key}'.encode()).hexdigest()[:12], 16) / 16**12
                    quality += .04 * fraction
                # Recent history is a soft tie preference at the quality level.
                if key in recent:
                    quality += .04
                value = (quality, str(row['place_id']), row)
                if key not in by_key or value[:2] < by_key[key][:2]:
                    by_key[key] = value
            choices.append(by_key)
            all_keys.update(by_key)
    except (KeyError, TypeError, ValueError, OverflowError):
        return decline('invalid_candidate_quality')
    keys = sorted(all_keys, key=repr)
    nodes = 2 + visits + (count + 1) * len(keys)
    forward_edges = visits + count * sum(map(len, choices)) + 2 * count * len(keys)
    info.update(minimum_reuse_node_count=nodes, minimum_reuse_forward_edge_count=forward_edges)
    if nodes > MAX_NODES or forward_edges > MAX_FORWARD_EDGES:
        return decline('allocation_size_budget')
    values = [value[0] for choices_for_slot in choices for value in choices_for_slot.values()]
    low, high = min(values), max(values)
    quality_cost = lambda value: round((value-low)/(high-low)*QUALITY_SCALE) if high > low else 0
    secondary_weight = visits * QUALITY_SCALE + 1
    primary_weight = secondary_weight * (visits * (count-1) // 2 + 1)
    graph = [[] for _ in range(nodes)]

    def edge(source, target, capacity, cost):
        forward = [target, len(graph[target]), capacity, cost]
        backward = [source, len(graph[source]), 0, -cost]
        graph[source].append(forward)
        graph[target].append(backward)
        return forward

    source, sink = 0, 1
    slot_base, course_visit_base = 2, 2 + visits
    global_base = course_visit_base + count * len(keys)
    index = {key: i for i, key in enumerate(keys)}
    selected_edges = []
    for course in range(count):
        for slot, by_key in enumerate(choices):
            slot_node = slot_base + course * len(pools) + slot
            edge(source, slot_node, 1, 0)
            records = []
            for key in sorted(by_key, key=repr):
                quality, _, row = by_key[key]
                visit_node = course_visit_base + course * len(keys) + index[key]
                records.append((edge(slot_node, visit_node, 1, quality_cost(quality)), row))
            selected_edges.append(records)
        for i in range(len(keys)):
            edge(course_visit_base + course * len(keys) + i, global_base + i, 1, 0)
    for i in range(len(keys)):
        edge(global_base+i, sink, 1, 0)
        for use in range(1, count):
            edge(global_base+i, sink, 1, primary_weight + use * secondary_weight)

    potentials, scanned = [0] * nodes, 0
    for flow in range(visits):
        distances, previous = [None] * nodes, [None] * nodes
        distances[source] = 0
        queue = [(0, source)]
        while queue:
            distance, node = heapq.heappop(queue)
            if distance != distances[node]:
                continue
            for ei, arc in enumerate(graph[node]):
                scanned += 1
                if scanned > MAX_SCANNED_EDGES:
                    info.update(minimum_reuse_scanned_edges=scanned, minimum_reuse_augmentations=flow)
                    return decline('allocation_work_budget')
                target, _, capacity, cost = arc
                if not capacity:
                    continue
                candidate = distance + cost + potentials[node] - potentials[target]
                if distances[target] is None or candidate < distances[target]:
                    distances[target], previous[target] = candidate, (node, ei)
                    heapq.heappush(queue, (candidate, target))
        if distances[sink] is None:
            return decline('insufficient_distinct_visits_within_course')
        for node, distance in enumerate(distances):
            if distance is not None:
                potentials[node] += distance
        node = sink
        while node != source:
            parent, ei = previous[node]
            arc = graph[parent][ei]
            arc[2] -= 1
            graph[node][arc[1]][2] += 1
            node = parent
    routes = []
    for course in range(count):
        route = []
        for slot in range(len(pools)):
            records = selected_edges[course*len(pools)+slot]
            route.append(next(row for arc, row in records if arc[2] == 0))
        routes.append(route)
    signatures = [tuple(groups[row['place_id']] for row in route) for route in routes]
    info.update(minimum_reuse_scanned_edges=scanned, minimum_reuse_augmentations=visits)
    if len(set(signatures)) != count:
        # Courses are interchangeable. Swapping a slot between two courses keeps
        # every global usage count and every per-slot quality contribution.
        # Reject swaps introducing a repeated visit inside either itinerary.
        canonical = lambda paths: tuple(sorted(paths, key=repr))
        initial = canonical(signatures)
        queue, seen, moves, repaired = deque([initial]), {initial}, 0, None
        while queue and moves < MAX_REPAIR_MOVES and repaired is None:
            state = queue.popleft()
            for a in range(count):
                for b in range(a+1, count):
                    for slot in range(len(pools)):
                        moves += 1
                        if moves > MAX_REPAIR_MOVES:
                            break
                        if state[a][slot] == state[b][slot]:
                            continue
                        first, second = list(state[a]), list(state[b])
                        first[slot], second[slot] = second[slot], first[slot]
                        if len(set(first)) != len(pools) or len(set(second)) != len(pools):
                            continue
                        candidate = list(state)
                        candidate[a], candidate[b] = tuple(first), tuple(second)
                        candidate = canonical(candidate)
                        if candidate in seen:
                            continue
                        if len(set(candidate)) == count:
                            repaired = candidate
                            break
                        seen.add(candidate)
                        queue.append(candidate)
                    if repaired is not None or moves >= MAX_REPAIR_MOVES:
                        break
                if repaired is not None or moves >= MAX_REPAIR_MOVES:
                    break
        info.update(minimum_reuse_duplicate_repair_moves=moves,
                    minimum_reuse_duplicate_repair_states=len(seen))
        if repaired is None:
            return decline('duplicate_ordered_courses')
        signatures = repaired
        routes = [[choices[slot][key][2] for slot, key in enumerate(path)]
                  for path in signatures]
    usage = {}
    for signature in signatures:
        for key in signature:
            usage[key] = usage.get(key, 0) + 1
    info.update(minimum_reuse_certified=True, minimum_reuse_reason=None,
                minimum_reuse_repeated_visits=visits-len(usage),
                minimum_reuse_pairwise_shared_visits=sum(n*(n-1)//2 for n in usage.values()))
    return routes, info
