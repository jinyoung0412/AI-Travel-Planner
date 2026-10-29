"""Ordered course choices improve coordinate detours without road API calls."""
import math
from collections import Counter

import numpy as np
import pandas as pd
import pytest

import app
import travel_intent as intent
from recommendation_ai import add_scores, search_courses
from Flask_server.recommender import route_coherence as geometry
from Flask_server.recommender.route_refinement import improve
from test_travel_intent import plan, stage, choice

ORIGIN = (36.8, 127.1)


def row(pid, kind, x, y=0, score=0):
    return dict(place_id=pid, 가게명=pid, 주소=f'충남 천안시 테스트로 {pid}', 지역='천안',
                카테고리=kind, latitude=ORIGIN[0] + y / 111.195080234,
                longitude=ORIGIN[1] + x / (111.195080234 * math.cos(math.radians(ORIGIN[0]))),
                방문자수=100, 블로그수=0, score=score, origin_distance_km=abs(x))


def point(x, y=0):
    value = row('point', '공원', x, y)
    return value['latitude'], value['longitude']


def ids(routes):
    return [tuple(r['place_id'] for r in route) for route in routes]


def test_forward_route_has_no_penalty_and_returning_towards_later_stop_does():
    forward = [row('food', '한식', .2), row('park', '공원', .6), row('cafe', '카페', 1.)]
    backtrack = [forward[0], row('far-park', '공원', 1.2), row('near-cafe', '카페', .7)]
    assert geometry.penalty(forward, ORIGIN, '대중교통') == pytest.approx(0, abs=1e-8)
    assert geometry.penalty(backtrack, ORIGIN, '대중교통') > .02
    assert geometry.metadata([backtrack], ORIGIN, '대중교통')['coordinate_geometry_available']


def test_nonadjacent_future_pass_is_detected_without_a_reverse_angle_at_last_turn():
    # Earlier eastbound segment already approached the last cafe. The last
    # westbound->southbound turn itself is 90 degrees, not a reversal.
    prefix = [point(0), point(2), point(2, 1), point(1, 1)]
    incoming = np.asarray(prefix[-1]) - prefix[-2]
    outgoing = np.asarray(point(1, .04)) - prefix[-1]
    assert float(incoming @ outgoing) == pytest.approx(0, abs=1e-10)
    assert geometry.extension(prefix, [point(1, .04)], '대중교통')[0] > .05
    assert geometry.extension(prefix, [point(1, -1)], '대중교통')[0] == pytest.approx(0, abs=1e-8)


@pytest.mark.parametrize('bad', [{}, {'latitude': None, 'longitude': 127},
                                 {'latitude': np.inf, 'longitude': 127},
                                 {'latitude': 190, 'longitude': 127}])
def test_unknown_coordinates_do_not_create_geometry_facts_or_crash(bad):
    assert geometry.penalty([bad], ORIGIN, '대중교통') == 0
    assert not geometry.metadata([[bad]], ORIGIN, '대중교통')['coordinate_geometry_available']


def test_unusable_coordinate_pool_is_rejected_safely_by_search():
    data = pd.DataFrame([row('food', '한식', .2), row('park', '공원', .6), row('cafe', '카페', 1)])
    data.loc[data.place_id.eq('park'), 'latitude'] = np.nan
    routes, metadata = search_courses(data, [['한식'], ['공원'], ['카페']], [], app.filter_keywords,
                                      n=1, start=ORIGIN)
    assert not routes and metadata['reason'] == 'missing_slot_candidates'


def test_search_keeps_activity_order_and_chooses_coherent_alternative():
    data = pd.DataFrame([row('food', '한식', .2), row('overshoot', '공원', 1.2),
                         row('forward-park', '공원', .6), row('cafe', '카페', .9)])
    routes, meta = search_courses(data, [['한식'], ['공원'], ['카페']], [], app.filter_keywords,
                                 n=1, start=ORIGIN)
    assert ids(routes) == [('food', 'forward-park', 'cafe')]
    assert [r['카테고리'] for r in routes[0]] == ['한식', '공원', '카페']
    assert meta['route_coherence']['policy'] == geometry.POLICY
    assert meta['route_coherence']['route_penalties'] == [0]


def test_geometry_does_not_promote_much_less_relevant_venue():
    data = pd.DataFrame([row('food', '한식', .2), row('popular', '공원', 1.2),
                         row('poor', '공원', .6), row('cafe', '카페', .9)])
    data['방문자수'] = [100000, 100000, 0, 100000]
    routes, _ = search_courses(data, [['한식'], ['공원'], ['카페']], [], app.filter_keywords,
                              n=1, start=ORIGIN)
    assert routes[0][1]['place_id'] == 'popular'


def test_refinement_swaps_same_slots_without_harming_disjointness_or_quality():
    a = [row('f0', '한식', .2), row('p1', '공원', 1.6), row('c0', '카페', .6)]
    b = [row('f1', '한식', 1.2), row('p0', '공원', .4), row('c1', '카페', 1.8)]
    pools = [[a[i], b[i]] for i in range(3)]
    groups = {r['place_id']: r['place_id'] for path in [a, b] for r in path}
    refined, meta = improve([a, b], pools, groups, ORIGIN, '대중교통')
    assert meta['refinement_moves'] > 0
    assert meta['refinement_objective_after'] < meta['refinement_objective_before']
    assert Counter(r['place_id'] for p in refined for r in p) == Counter(groups.keys())
    assert len(set(ids(refined))) == 2
    assert all([r['카테고리'] for r in p] == ['한식', '공원', '카페'] for p in refined)


def test_reuse_certificate_and_seed_variation_survive_geometry_policy():
    rows = [row(f'{kind}{i}', cat, position) for kind, cat, position in
            [('f', '한식', .2), ('p', '공원', .6), ('c', '카페', 1.)] for i in range(3)]
    data = pd.DataFrame(rows)
    seen = set()
    for seed in range(5):
        routes, info = search_courses(data, [['한식'], ['공원'], ['카페']], [], app.filter_keywords,
                                     n=2, start=ORIGIN, seed=seed, randomize=True)
        replay, _ = search_courses(data.iloc[::-1], [['한식'], ['공원'], ['카페']], [], app.filter_keywords,
                                   n=2, start=ORIGIN, seed=seed, randomize=True)
        assert ids(routes) == ids(replay)
        assert info['course_diversity']['repeated_visit_count'] == 0
        assert info['course_diversity']['minimum_reuse_certified']
        seen.add(tuple(ids(routes)))
    assert len(seen) > 1


def test_ai_cannot_spend_general_quality_window_on_reintroduced_detour():
    data = add_scores(pd.DataFrame([row('food', '한식', .2), row('good', '공원', .6),
                                   row('bad', '공원', 1.4), row('cafe', '카페', .9)]), [])
    p = plan([stage('식사', ['한식']), stage('산책', ['공원']), stage('카페', ['카페'])])
    pools = [[dict(row=r, public=intent.candidate_record(r, s, intent.DATA_VERSION))
              for r in data.to_dict('records') if app.category_matches(r['카테고리'], s['category_filters'])]
             for s in p['stages']]
    fallback, search = intent.course_rule_selection(pools, p, 1, ORIGIN, '대중교통')
    bad = [[choice(pools[0][0]['public'], 's1'), choice(pools[1][1]['public'], 's2'),
            choice(pools[2][0]['public'], 's3')]]
    with pytest.raises(ValueError, match='selection_course_coherence'):
        intent.validate_selection({'courses': bad}, pools, p, 1, 'course', expected=1,
            diversity_reference=fallback, start=ORIGIN, transport='대중교통',
            quality_limit=search['quality_limit'])
    assert intent.selection_costs(fallback, pools, ORIGIN, '대중교통')[0] <= search['quality_limit'] + 1e-9
    assert intent.selection_fallback_reason(ValueError('selection_course_coherence')) == 'quality_guard'


def test_geometry_guard_accepts_reference_permutations_and_preserves_forced_overlap():
    first = [row('f0', '한식', .2), row('park', '공원', .6), row('c0', '카페', .9)]
    second = [row('f1', '한식', .25), first[1], row('c1', '카페', 1)]
    assert geometry.selection_within_reference([second, first], [first, second], ORIGIN, '대중교통')
    pools = [[first[i], second[i]] for i in range(3)]
    groups = {r['place_id']: r['place_id'] for p in [first, second] for r in p}
    refined, _ = improve([first, second], pools, groups, ORIGIN, '대중교통')
    assert sum(r['place_id'] == 'park' for p in refined for r in p) == 2


def test_random_refinement_keeps_near_equal_choices_but_fixes_large_detours():
    first = [row('food', '한식', .2), row('park', '공원', .6), row('cafe', '카페', .91)]
    near = row('near-cafe', '카페', .9)
    groups = {r['place_id']: r['place_id'] for r in first + [near]}
    refined, meta = improve([first], [[first[0]], [first[1]], [first[2], near]],
                           groups, ORIGIN, '대중교통', randomize=True)
    assert ids(refined) == ids([first]) and meta['refinement_moves'] == 0
    bad = [first[0], row('overshoot', '공원', 1.8), first[2]]
    groups['overshoot'] = 'overshoot'
    refined, meta = improve([bad], [[first[0]], [bad[1], first[1]], [first[2]]],
                           groups, ORIGIN, '대중교통', randomize=True)
    assert refined[0][1]['place_id'] == 'park' and meta['refinement_moves'] == 1


def test_refinement_budget_declines_extra_work_without_dropping_courses(monkeypatch):
    from Flask_server.recommender import route_refinement
    route = [row('food', '한식', .2), row('park', '공원', .6), row('cafe', '카페', .9)]
    groups = {r['place_id']: r['place_id'] for r in route}
    monkeypatch.setattr(route_refinement, 'MAX_EVALUATIONS', 0)
    refined, meta = route_refinement.improve([route], [[r] for r in route], groups, ORIGIN, '대중교통')
    assert ids(refined) == ids([route])
    assert meta['refinement_evaluations'] == 0
