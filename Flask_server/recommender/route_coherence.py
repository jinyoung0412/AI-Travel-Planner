"""Bounded coordinate-only detour costs; never road or transit claims.

Activity order is immutable. A turn costs extra only when movement reverses;
a separate segment projection detects an earlier approach to a later stop.
Both are soft costs, capped per visit so relevance remains part of selection.
"""
import math

import numpy as np

from .constants import RADIUS_KM
from .geometry import distances_from
from recommendation_context import context_cost

POLICY = 'ordered_coordinate_detour_v1'
CORRIDOR_KM = .15
TOLERANCE_KM = .10
WEIGHT = .65
MAX_VISIT_COST = .12
SELECTION_WINDOW = .015
DISTANCE_GROWTH_KM = .20
DISTANCE_GROWTH_FRACTION = .10


def coordinates(path):
    try:
        values = np.asarray([(p['latitude'], p['longitude']) for p in path], dtype=float).reshape(-1, 2)
    except (KeyError, TypeError, ValueError):
        return None
    if (not np.isfinite(values).all() or
            not ((np.abs(values[:, 0]) <= 90) & (np.abs(values[:, 1]) <= 180)).all()):
        return None
    return values


def extension(prefix, candidates, transport):
    """Vector cost for appending candidates to an ordered coordinate prefix.

    Uses a local tangent plane only for turn/projection geometry. Ordinary
    route length is still great-circle distance. Invalid geometry adds no
    invented penalty; search independently rejects unusable coordinates.
    """
    candidates = np.asarray(candidates, dtype=float).reshape(-1, 2)
    zeros = np.zeros(len(candidates))
    if len(prefix) < 2 or not len(candidates):
        return zeros
    prefix = np.asarray(prefix, dtype=float).reshape(-1, 2)
    if not np.isfinite(prefix).all() or not np.isfinite(candidates).all():
        return zeros
    scale = np.array([111.195080234, 111.195080234 * math.cos(math.radians(prefix[0, 0]))])
    points = (prefix - prefix[0]) * scale
    ends = (candidates - prefix[0]) * scale
    incoming = points[-1] - points[-2]
    outgoing = ends - points[-1]
    length_in = float(np.linalg.norm(incoming))
    length_out = np.linalg.norm(outgoing, axis=1)
    chord = np.linalg.norm(ends - points[-2], axis=1)
    denominator = np.maximum(length_in * length_out, 1e-12)
    reverse_fraction = np.clip(-(outgoing @ incoming) / denominator, 0, 1)
    turnback = np.maximum(0, length_in + length_out - chord - TOLERANCE_KM) * reverse_fraction
    # When C lies near an earlier A->B segment, count the travel after the
    # closest approach until C is eventually reached. This is not an assertion
    # that the actual road passed C or that a visit took place on that leg.
    premature = zeros.copy()
    leg_lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    suffix = np.cumsum(leg_lengths[::-1])[::-1]
    for i, segment_length in enumerate(leg_lengths):
        if segment_length <= 1e-9:
            continue
        vector = points[i + 1] - points[i]
        projection = ((ends - points[i]) @ vector) / segment_length**2
        nearest = points[i] + np.clip(projection, 0, 1)[:, None] * vector
        lateral = np.linalg.norm(ends - nearest, axis=1)
        inside = (projection >= 0) & (projection <= 1)
        remaining = (1 - np.clip(projection, 0, 1)) * segment_length
        if i + 1 < len(leg_lengths):
            remaining += suffix[i + 1]
        excess = np.maximum(0, remaining + length_out - lateral - TOLERANCE_KM)
        closeness = np.clip(1 - lateral / CORRIDOR_KM, 0, 1)
        premature = np.maximum(premature, excess * closeness * inside)
    return np.minimum(MAX_VISIT_COST, WEIGHT * np.maximum(turnback, premature) / RADIUS_KM[transport])


def penalty(path, start, transport):
    values = coordinates(path)
    if values is None or not len(values):
        return 0.0
    try:
        prefix = [tuple(float(x) for x in start)]
    except (TypeError, ValueError):
        return 0.0
    if len(prefix[0]) != 2 or not np.isfinite(prefix).all():
        return 0.0
    total = 0.0
    for point in values:
        total += float(extension(prefix, [point], transport)[0])
        prefix.append(point)
    return total / len(values)


def route_cost(path, start, transport, geometry=True):
    """Shared server objective for allocation refinement and quality guards."""
    values = coordinates(path)
    if values is None or not len(values):
        return math.inf
    last, total = start, 0.0
    for row, point in zip(path, values):
        total += float(distances_from(last, [point])[0] / RADIUS_KM[transport])
        total += 1 - float(row.get('score', 0)) + context_cost(row)
        last = point
    return total / len(path) + (penalty(path, start, transport) if geometry else 0)


def metadata(paths, start, transport):
    valid = all(coordinates(path) is not None for path in paths)
    return dict(policy=POLICY, coordinate_geometry_available=valid,
        corridor_km=CORRIDOR_KM, tolerance_km=TOLERANCE_KM,
        maximum_extra_cost_per_visit=MAX_VISIT_COST,
        selection_penalty_window=SELECTION_WINDOW,
        route_penalties=[round(penalty(path, start, transport), 6) for path in paths],
        limitation='방문 순서를 유지하며 좌표의 방향 전환·뒤 방문 장소에 대한 앞 구간의 근접을 비교합니다. '
                   '도로·건널목·정류장·실제 경로의 왕복 여부와 이동시간은 확인하지 않았습니다.')


def selection_within_reference(paths, reference, start, transport):
    """Permutation-invariant guard; compact model orders pass unchanged.

    The general quality window is wider than the geometry cost itself. This
    prevents an unrestricted model response from spending it on new detours.
    Unknown coordinates cannot support a positive geometry assertion.
    """
    if start is None or len(paths) != len(reference):
        return True
    if any(coordinates(path) is None for path in list(paths) + list(reference)):
        return True
    actual = sorted(penalty(path, start, transport) for path in paths)
    baseline = sorted(penalty(path, start, transport) for path in reference)
    if any(value > limit + SELECTION_WINDOW + 1e-9 for value, limit in zip(actual, baseline)):
        return False
    def total_distance(routes):
        total = 0.0
        for path in routes:
            last = start
            for point in coordinates(path):
                total += float(distances_from(last, [point])[0])
                last = point
        return total
    original = total_distance(reference)
    return total_distance(paths) <= original + max(DISTANCE_GROWTH_KM,
                                                   original * DISTANCE_GROWTH_FRACTION) + 1e-9
