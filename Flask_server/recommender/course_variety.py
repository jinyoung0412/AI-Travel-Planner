"""Disjoint-first course alternatives; persisted identities stay intact."""
import hashlib
import itertools
from collections import Counter

from . import reviewed_area_policy as areas

# Costs combine normalized popularity and straight-line distance per visit.
# Quality/history tie window applies only after the overlap objective.
QUALITY_WINDOW = 0.15
RANDOM_WINDOW = 0.04
POLICY = 'disjoint_first_full_pool_v3'


def signature(path, groups):
    return tuple(groups[p['place_id']] for p in path)


def shared_count(a, b):
    return sum((Counter(a) & Counter(b)).values())


def shared_visits(paths):
    return [shared_count(a, b) for a, b in itertools.combinations(paths, 2)]


def comparison_signature(path, groups):
    return tuple(areas.comparison_key(p, groups[p['place_id']]) for p in path)


def summary(paths, randomize=False, comparison_paths=None, reviewed_areas=()):
    length = len(paths[0]) if paths else 0
    target = length
    similar_threshold = length - min(2, length)
    exact_shared = shared_visits(paths)
    shared = shared_visits(comparison_paths if comparison_paths is not None else paths)
    return dict(policy=POLICY, minimum_changed_visits_target=target,
                comparison_basis='reviewed_tourism_areas_and_exact_visits' if reviewed_areas else 'exact_visits',
                reviewed_area_policy=areas.POLICY_VERSION, reviewed_area_groups=list(reviewed_areas),
                exact_max_shared_visits=max(exact_shared, default=0),
                exact_similar_pair_count=sum(value > similar_threshold for value in exact_shared),
                max_shared_visits=max(shared, default=0),
                similar_pair_count=sum(value > similar_threshold for value in shared),
                overlapping_pair_count=sum(value > 0 for value in exact_shared),
                repeated_visit_count=sum(map(len, paths)) - len(set(itertools.chain.from_iterable(paths))),
                quality_window=None, random_window=RANDOM_WINDOW if randomize else 0,
                randomized=bool(randomize),
                limitation='조건을 통과한 전체 후보에서 코스 간 장소 중복 방지를 우선합니다. '
                           '같은 관광 권역의 장소는 코스 구성이 겹치는 것으로 비교합니다. '
                           '중복 없는 구성이 불가능하면 반복 방문을 최소화해 선택합니다. 현장 동일성은 미확인입니다.')


def course_summary(courses, groups, randomize=False):
    return summary([signature(path, groups) for path in courses], randomize,
                   [comparison_signature(path, groups) for path in courses], areas.applied_areas(courses))


def select(complete, count, seed, groups, randomize=False, recent_place_ids=()):
    """Prefer least reuse across the entire set, then quality; vary near equals.

    The first course remains the cost optimum unless randomization is explicit.
    This ranks a bounded route set. Full-pool feasibility and joint minimum
    reuse allocation are handled by the search engine before final delivery.
    """
    options = [(float(cost), signature(path, groups), path, comparison_signature(path, groups))
               for cost, path in complete.values()]
    selected, previous = [], []
    recent = {groups.get(pid, pid) for pid in recent_place_ids}
    while options and len(selected) < count:
        def overlap(item):
            return (sum(shared_count(item[1], signature(path, groups)) for path in selected),
                    sum(shared_count(item[3], old) for old in previous),
                    max((shared_count(item[3], old) for old in previous), default=0))

        best_overlap = min(map(overlap, options))
        eligible = [item for item in options if overlap(item) == best_overlap]
        best_cost = min(item[0] for item in eligible)
        eligible = [item for item in eligible if item[0] <= best_cost + QUALITY_WINDOW]
        if recent:
            shared = min(sum(pid in recent for pid in item[1]) for item in eligible)
            eligible = [item for item in eligible if sum(pid in recent for pid in item[1]) == shared]
        minimum = min(item[0] for item in eligible)
        if randomize:
            eligible = [item for item in eligible if item[0] <= minimum + RANDOM_WINDOW]

        def key(item):
            tie = hashlib.sha256(f'{seed}:{"|".join(item[1])}'.encode()).hexdigest()
            return (tie, item[0]) if randomize else (item[0], tie)

        chosen = min(eligible, key=key)
        options.remove(chosen)
        selected.append(chosen[2])
        previous.append(chosen[3])
    return selected
