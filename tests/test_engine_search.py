"""Offline search contracts, exhaustive comparisons and deterministic work bounds."""
import hashlib
import itertools

import numpy as np
import pandas as pd
import pytest

from recommendation_ai import (add_scores, distances_from, route_metrics, search_courses,
                               find_best_for_plan, select_courses, generate_fixed_courses)
from Flask_server.recommender import search as engine
from clustering_ai import find_optimal_clusters, perform_clustering

ORIGIN = (36.8, 127.1)


def frame(count):
    return pd.DataFrame([{'place_id': f'p{i:05}', '가게명': f'장소{i}', '주소': f'충남 테스트로 {i+1}',
                          'latitude': ORIGIN[0], 'longitude': ORIGIN[1], '카테고리': '공원',
                          '방문자수': 0, '블로그수': 0} for i in range(count)])


def category_filter(df, categories, tags):
    assert tags == []
    values = df.get('카테고리', pd.Series('', index=df.index))
    return df[values.map(lambda value: any(cat in value for cat in categories)).astype(bool)]


def course_ids(courses):
    return [tuple(p['place_id'] for p in course) for course in courses]


def tie(seed, ids):
    return hashlib.sha256(f'{seed}:{"|".join(ids)}'.encode()).hexdigest()


def test_finite_scores_with_corrupt_and_overflowing_counts():
    data = frame(8)
    data['방문자수'] = [np.inf, -np.inf, np.nan, -5, 'bad', 0, 1e308, np.iinfo(np.int64).max]
    data['블로그수'] = [0, 0, 0, 0, 0, 5, 1e308, np.iinfo(np.int64).max]
    before = data.copy(deep=True)
    result = add_scores(data, [])
    assert np.isfinite(result[['pop_score', 'tag_score', 'score']]).all().all()
    assert result['score'].between(0, 1).all()
    assert result['score'].iloc[:5].eq(0).all()
    assert result['score'].iloc[6] == 1
    assert 0 < result['score'].iloc[5] < result['score'].iloc[7] < 1
    pd.testing.assert_frame_equal(data, before)


def test_only_verified_well_formed_tag_keys_are_scored():
    data = frame(8)
    data['blog_tag_status'] = ['verified'] * 4 + ['legacy_unverified', 'fetch_error', None, 'verified']
    data['blog_tags'] = ['{"조용한":1}', 'bad', '["조용한"]', {1: 2},
                        '{"조용한":1}', '{"조용한":1}', '{"조용한":1}', '{"활기찬":1}']
    assert add_scores(data, ['조용한', None, 42])['tag_score'].tolist() == [1, 0, 0, 0, 0, 0, 0, 0]
    assert add_scores(data, None)['score'].eq(0).all()


def test_equal_total_counts_have_equal_popularity():
    data = frame(4)
    data['방문자수'], data['블로그수'] = [0, 10, 5, 7], [0, 0, 5, 3]
    assert add_scores(data, [])['pop_score'].tolist() == [0, 1, 1, 1]


def test_distance_units_and_route_legs_include_origin_without_return():
    assert distances_from((0, 0), [(0, 1), (0, 0), (0, 180)]).tolist() == pytest.approx(
        [111.195080234, 0, 20015.114442], abs=1e-6)
    assert distances_from(ORIGIN, []).size == 0
    metrics = route_metrics([{'latitude': 0, 'longitude': 1}, {'latitude': 0, 'longitude': 3}], (0, 0))
    assert metrics['estimated_distance_km'] == pytest.approx(333.585, abs=.001)
    assert metrics['leg_distances_km'] == [111.195, 222.39]
    assert metrics['travel_time_minutes'] is None
    assert route_metrics([], ORIGIN)['estimated_distance_km'] == 0


@pytest.mark.parametrize('transport', ['차', '대중교통'])
def test_small_search_matches_exhaustive_objective_and_diversity(transport):
    data = frame(5)
    data['카테고리'] = ['공원 카페', '공원', '공원 카페', '한식', '한식 카페']
    data['latitude'] += np.array([0, .002, -.001, .004, -.003])
    data['방문자수'] = [0, 20, 5, 10, 1]
    data['blog_tag_status'] = 'verified'
    data['blog_tags'] = ['{}', '{}', '{"조용한":1}', '{}', '{}']
    categories = [['공원'], ['카페'], ['한식']]
    seed = 41
    scored = add_scores(data, ['조용한'])
    pools = [category_filter(scored, cats, []).to_dict('records') for cats in categories]
    options = []
    for path in itertools.product(*pools):
        ids = tuple(p['place_id'] for p in path)
        if len(set(ids)) != len(path):
            continue
        current, cost = ORIGIN, 0
        for place in path:
            point = (place['latitude'], place['longitude'])
            cost += distances_from(current, [point])[0] / engine.RADIUS_KM[transport] + 1 - place['score']
            current = point
        options.append((cost / len(path), ids))
    expected = []
    while options:
        best = min(options, key=lambda item: (
            item[0] + .08 * max((len(set(item[1]) & set(prev)) / 3 for prev in expected), default=0),
            tie(seed, item[1])))
        expected.append(best[1])
        options.remove(best)
    courses, info = search_courses(data, categories, ['조용한'], category_filter,
                                   n=100, start=ORIGIN, transport=transport, seed=seed, beam_width=1)
    assert course_ids(courses) == expected
    assert info['search_method'] == 'exhaustive'
    assert info['candidate_space_exhausted']
    assert info['reason'] == 'insufficient_unique_courses'


def test_matching_agrees_with_exhaustive_feasibility():
    rng = np.random.default_rng(2026)
    for _ in range(100):
        pools = [tuple(str(i) for i in range(5) if rng.random() < .45) for _ in range(4)]
        expected = any(len(set(path)) == len(path) for path in itertools.product(*pools))
        witness = engine._matching(pools)
        assert (witness is not None) == expected
        if witness is not None:
            assert len(set(witness)) == 4
            assert all(pid in pool for pid, pool in zip(witness, pools))


def test_beam_best_course_matches_small_complete_enumeration():
    data = frame(51)
    data['카테고리'] = ['공원'] * 17 + ['카페'] * 17 + ['한식'] * 17
    rng = np.random.default_rng(31)
    data['latitude'] += rng.normal(0, .01, len(data))
    data['longitude'] += rng.normal(0, .01, len(data))
    data['방문자수'] = rng.integers(0, 100, len(data))
    categories = [['공원'], ['카페'], ['한식']]
    courses, info = search_courses(data, categories, [], category_filter, n=1,
                                   start=ORIGIN, seed=11, beam_width=1024)
    scored = add_scores(data, [])
    pools = [category_filter(scored, cats, []).to_dict('records') for cats in categories]

    def objective(path):
        current, cost = ORIGIN, 0.0
        for place in path:
            point = (place['latitude'], place['longitude'])
            cost += float(distances_from(current, [point])[0] / 4.5 + 1 - place['score'])
            current = point
        return cost / 3

    optimum = min(objective(path) for path in itertools.product(*pools))
    assert info['search_method'] == 'beam_with_feasibility_completion'
    assert objective(courses[0]) == pytest.approx(optimum, abs=1e-12)


def test_collective_slot_shortage_is_proven_without_search():
    data = frame(3)
    data.loc[2, '카테고리'] = '카페'
    courses, info = search_courses(data, [['공원']] * 3, [], category_filter, start=ORIGIN)
    assert courses == []
    assert info['slot_candidate_counts'] == [2, 2, 2]
    assert info['reason'] == 'insufficient_distinct_places'


def test_seed_applies_before_candidate_truncation_and_is_row_order_independent():
    data = frame(engine.EXACT_COMBINATIONS + 1)
    selections = []
    for seed in (0, 1):
        courses, info = search_courses(data, [['공원']], [], category_filter, n=1,
                                       start=ORIGIN, seed=seed, beam_width=1)
        expected = min(data['place_id'], key=lambda pid: tie(seed, [pid]))
        assert course_ids(courses) == [(expected,)]
        repeated, _ = search_courses(data.sample(frac=1, random_state=7), [['공원']], [],
                                      category_filter, n=1, start=ORIGIN, seed=seed, beam_width=1)
        assert course_ids(repeated) == course_ids(courses)
        assert info['search_method'] == 'beam_with_feasibility_completion'
        selections.append(expected)
    assert selections[0] != selections[1]


def test_beam_work_is_bounded_by_candidate_volume(monkeypatch):
    data = frame(90)
    monkeypatch.setattr(engine, 'BEAM_DISTANCE_BUDGET', 10_000)
    courses, info = search_courses(data, [['공원']] * 5, [], category_filter, n=5,
                                   start=ORIGIN, seed=2, beam_width=1024)
    width = info['effective_beam_width']
    stats = info['search_stats']
    assert width == 22
    assert stats['beam_distance_evaluations'] <= 10_000
    assert stats['beam_expansions'] <= width + 4 * width * min(width, 32)
    assert len(set(course_ids(courses))) == 5
    assert all(len(set(ids)) == 5 for ids in course_ids(courses))


def test_completion_preserves_count_and_slots_after_all_beam_routes_die(monkeypatch):
    data = frame(4200)
    data.loc[0, '카테고리'] = '공원 카페'
    data.loc[1:, 'latitude'] += .001
    monkeypatch.setattr(engine, 'BEAM_DISTANCE_BUDGET', 1)
    courses, info = search_courses(data, [['공원'], ['카페']], [], category_filter,
                                   n=5, start=ORIGIN, beam_width=1)
    assert info['effective_beam_width'] == 1
    assert len(set(course_ids(courses))) == 5
    assert all(ids[0] != 'p00000' and ids[1] == 'p00000' for ids in course_ids(courses))
    assert info['search_stats']['completion_prefixes'] <= 1 + 5 * 2
    assert info['search_stats']['completion_matching_checks'] > 0
    assert info['reason'] is None


def test_single_feasible_course_in_factorial_candidate_space_is_exhausted():
    data = frame(12)
    data['카테고리'] = [' '.join(f's{slot:02}' for slot in range(12 - i)) for i in range(12)]
    courses, info = search_courses(data, [[f's{slot:02}'] for slot in range(12)], [],
                                   category_filter, n=5, start=ORIGIN, beam_width=1)
    assert course_ids(courses) == [tuple(f'p{i:05}' for i in reversed(range(12)))]
    assert info['reason'] == 'insufficient_unique_courses'
    assert info['candidate_space_exhausted']
    assert info['search_stats']['completion_prefixes'] == 13
    assert info['search_stats']['completion_matching_checks'] <= 12 * 12


def test_invalid_old_duplicate_does_not_hide_valid_place():
    data = frame(1)
    bad = data.assign(latitude=np.inf)
    courses, info = search_courses(pd.concat([bad, data]), [['공원']], [], category_filter, n=1, start=ORIGIN)
    assert course_ids(courses) == [('p00000',)]
    assert info['slot_candidate_counts'] == [1]


@pytest.mark.parametrize('data', [pd.DataFrame(), pd.DataFrame([{'latitude': np.inf}]),
                                frame(1).drop(columns='longitude')])
def test_sparse_or_invalid_coordinates_fail_closed(data):
    courses, info = search_courses(data, [['공원']], [], category_filter, start=ORIGIN)
    assert courses == []
    assert info['reason'] == 'missing_slot_candidates'


@pytest.mark.parametrize('kwargs', [{'n': engine.MAX_COURSES + 1}, {'beam_width': 0},
    {'beam_width': engine.MAX_BEAM_WIDTH + 1}, {'transport': '비행기'}, {'start': (np.nan, 127)},
    {'start': (91, 127)}, {'start': [36]}, {'seed': True}, {'seed': '1'}])
def test_direct_call_limits_raise_clear_value_errors(kwargs):
    with pytest.raises(ValueError):
        search_courses(frame(1), [['공원']], [], category_filter, **kwargs)


def test_direct_slot_limit_prevents_recursion_explosion():
    with pytest.raises(ValueError):
        search_courses(frame(20), [['공원']] * (engine.MAX_SLOTS + 1), [], category_filter)


def test_legacy_wrappers_preserve_result_shapes_and_ignore_clusters():
    data = frame(6)
    data['카테고리'] = ['한식', '공원', '카페'] * 2
    data['Cluster'] = 0
    stops = [{'category_filters': [category], 'blog_tag_keywords': []}
             for category in ('한식', '공원', '카페')]
    best = find_best_for_plan(data, stops, category_filter, ORIGIN)
    selected = select_courses(data, stops, category_filter, top_n=5, start=ORIGIN)
    fixed = generate_fixed_courses(data, [], category_filter, n=5, spots=3, start=ORIGIN)
    assert len(best) == 3 and len(selected) == len(fixed) == 5
    assert selected[0]['course'] == best
    assert all(set(item) == {'course', 'total_score'} for item in selected)
    assert all(item['total_score'] == sum(p['score'] for p in item['course']) for item in selected)


def test_clustering_rejects_missing_and_out_of_range_coordinates():
    data = frame(5)
    data['latitude'] = [36, 91, np.inf, np.nan, -91]
    assert perform_clustering(data)['Cluster'].tolist() == [0, -1, -1, -1, -1]
    assert perform_clustering(data.drop(columns='longitude'))['Cluster'].eq(-1).all()
    assert find_optimal_clusters([], 10) == 1
    assert find_optimal_clusters([[91, 127], [np.inf, 127]], 10) == 1
