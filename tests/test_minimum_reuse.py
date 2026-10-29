"""Offline oracle checks for exact global visit reuse allocation."""
import itertools
import random
from collections import Counter

import pytest

from Flask_server.recommender import minimum_reuse as flow

ORIGIN = (36.8, 127.1)


def problem(slot_ids, scores=None):
    ids = set(itertools.chain.from_iterable(slot_ids))
    rows = {pid: dict(place_id=pid, latitude=ORIGIN[0], longitude=ORIGIN[1],
                     score=(scores or {}).get(pid, 0.)) for pid in ids}
    return [[rows[pid] for pid in slot] for slot in slot_ids], {pid: pid for pid in ids}


def solve(slot_ids, count, **kwargs):
    pools, groups = problem(slot_ids)
    return flow.allocate_minimum_reuse(pools, count, groups, ORIGIN, '대중교통', **kwargs)


def signatures(routes):
    return [tuple(row['place_id'] for row in route) for route in routes]


def objective(paths):
    uses = Counter(itertools.chain.from_iterable(paths))
    return sum(uses.values()) - len(uses), sum(n*(n-1)//2 for n in uses.values())


def test_scarce_later_slot_is_reserved_even_when_zero_overlap_is_impossible():
    pools, groups = problem([['1'], ['4', '2', '1', '0', '3', '5'], ['4', '0']],
                            {'0': 1., '4': 1., '2': .9, '3': .8, '5': .7})
    routes, meta = flow.allocate_minimum_reuse(pools, 3, groups, ORIGIN, '대중교통')
    paths = signatures(routes)
    assert len(set(itertools.chain.from_iterable(paths))) == 6
    assert len(set(paths)) == 3
    assert all(len(set(path)) == 3 for path in paths)
    assert meta['minimum_reuse_certified'] is True
    assert meta['minimum_reuse_repeated_visits'] == 3


def test_small_random_pools_match_exhaustive_global_repeat_and_balance_oracle():
    rng = random.Random(47)
    certified = 0
    for _ in range(60):
        slot_count, count = rng.randint(2, 3), rng.randint(2, 3)
        ids = list('abcde')[:rng.randint(3, 5)]
        slots = [rng.sample(ids, rng.randint(1, len(ids))) for _ in range(slot_count)]
        paths = [path for path in itertools.product(*slots) if len(set(path)) == slot_count]
        if not count <= len(paths) <= 20:
            continue
        routes, meta = solve(slots, count)
        if routes is None:
            assert meta['minimum_reuse_reason'] == 'duplicate_ordered_courses'
            assert meta['minimum_reuse_certified'] is False
            continue
        certified += 1
        actual = signatures(routes)
        optimum = min(map(objective, itertools.combinations(paths, count)))
        assert objective(actual) == optimum
        assert all(len(set(path)) == slot_count for path in actual)
        assert all(pid in slots[i] for path in actual for i, pid in enumerate(path))
    assert certified >= 10


def test_exact_visit_variants_cannot_repeat_within_a_course():
    pools, groups = problem([['a', 'b'], ['alias-a', 'c']])
    groups['alias-a'] = 'a'
    routes, meta = flow.allocate_minimum_reuse(pools, 2, groups, ORIGIN, '대중교통')
    assert meta['minimum_reuse_certified'] is True
    assert meta['minimum_reuse_repeated_visits'] == 1
    assert all(len({groups[row['place_id']] for row in path}) == 2 for path in routes)


def test_duplicate_course_solution_declines_global_certificate():
    routes, meta = solve([['a'], ['b']], 2)
    assert routes is None
    assert meta['minimum_reuse_reason'] == 'duplicate_ordered_courses'
    assert meta['minimum_reuse_certified'] is False


def test_two_by_two_pool_repairs_duplicates_without_changing_global_optimum():
    routes, meta = solve([['a', 'b'], ['c', 'd']], 3)
    paths = signatures(routes)
    assert len(set(paths)) == 3
    assert objective(paths) == (2, 2)
    assert meta['minimum_reuse_certified'] is True


def test_duplicate_repair_budget_cannot_produce_false_certificate(monkeypatch):
    monkeypatch.setattr(flow, 'MAX_REPAIR_MOVES', 0)
    routes, meta = solve([['a'], ['b']], 2)
    assert routes is None
    assert meta['minimum_reuse_reason'] == 'duplicate_ordered_courses'
    assert meta['minimum_reuse_certified'] is False


@pytest.mark.parametrize('constant,reason', [
    ('MAX_NODES', 'allocation_size_budget'),
    ('MAX_FORWARD_EDGES', 'allocation_size_budget'),
    ('MAX_SCANNED_EDGES', 'allocation_work_budget'),
])
def test_resource_limits_decline_without_truncating_candidates(monkeypatch, constant, reason):
    monkeypatch.setattr(flow, constant, 1)
    routes, meta = solve([['a', 'b'], ['c', 'd']], 2)
    assert routes is None
    assert meta['minimum_reuse_certified'] is False
    assert meta['minimum_reuse_reason'] == reason


def test_seed_replays_and_input_order_does_not_change_solution():
    slots = [['a', 'b', 'c'], ['d', 'e', 'f']]
    first, meta = solve(slots, 2, seed=39, randomize=True)
    second, _ = solve([list(reversed(s)) for s in slots], 2, seed=39, randomize=True)
    assert meta['minimum_reuse_certified'] is True
    assert signatures(first) == signatures(second)
