"""Alternative composition, bounded randomization and constrained-pool regressions."""
import pandas as pd
import pytest

import app
from recommendation_ai import search_courses
from Flask_server.recommender import course_variety as policy
from Flask_server.recommender.visits import visit_groups

ORIGIN = (36.8151, 127.1139)


def data(foods=3, parks=3, cafes=4):
    return pd.DataFrame([dict(place_id=f'{kind}{i}', 가게명=f'{kind}{i}',
        주소=f'충남 천안시 테스트로 {len(kind)*100+i+1}', 지역='천안',
        카테고리=category, latitude=ORIGIN[0], longitude=ORIGIN[1],
        방문자수=100, 블로그수=0)
        for kind, category, amount in [('food','한식',foods),('park','공원',parks),('cafe','카페',cafes)]
        for i in range(amount)])


def signatures(courses):
    return [tuple(p['place_id'] for p in course) for course in courses]


def test_popular_prefix_cannot_fill_all_three_courses_with_cafe_swaps():
    rows = data()
    by_id = {p['place_id']:p for p in rows.to_dict('records')}
    routes = [(0.30, ('food0','park0','cafe0')),
              (0.31, ('food0','park0','cafe1')),
              (0.32, ('food0','park0','cafe2')),
              (0.37, ('food1','park0','cafe1')),
              (0.39, ('food2','park1','cafe2')),
              (0.90, ('food1','park2','cafe3'))]
    complete = {ids:(cost,[by_id[pid] for pid in ids]) for cost,ids in routes}
    selected = policy.select(complete, 3, 0, visit_groups(rows))
    assert signatures(selected) == [routes[i][1] for i in (0,4,5)]
    assert policy.summary(signatures(selected))['similar_pair_count'] == 0


def test_single_park_still_allows_different_food_and_cafe():
    courses, info = search_courses(data(parks=1), [['한식'],['공원'],['카페']], [],
        app.filter_keywords, start=ORIGIN, n=3)
    assert len({c[0]['place_id'] for c in courses}) == 3
    assert len({c[2]['place_id'] for c in courses}) == 3
    assert info['course_diversity']['max_shared_visits'] == 1
    assert info['constraints_relaxed'] == []


def test_limited_pool_keeps_valid_count_and_discloses_similar_alternatives():
    courses, info = search_courses(data(foods=1,parks=1), [['한식'],['공원'],['카페']], [],
        app.filter_keywords, start=ORIGIN, n=3, seed=52, randomize=True)
    assert len(set(signatures(courses))) == 3
    assert info['course_diversity']['similar_pair_count'] == 3
    assert info['course_diversity']['max_shared_visits'] == 2
    assert info['constraints_relaxed'] == []
    assert info['slot_candidate_counts'] == [1,1,4]


def test_zero_overlap_precedes_quality_window_within_eligible_candidates():
    rows=data(); by_id={p['place_id']:p for p in rows.to_dict('records')}
    choices=[(0.1,('food0','park0','cafe0')),(0.11,('food0','park0','cafe1')),
             (0.9,('food1','park1','cafe2'))]
    options={ids:(cost,[by_id[x] for x in ids]) for cost,ids in choices}
    selected=policy.select(options,2,1,visit_groups(rows),True)
    assert len(selected) == 2
    assert not set(signatures(selected)[0]) & set(signatures(selected)[1])
    assert choices[2][1] in signatures(selected)


def test_randomized_near_equals_change_by_seed_and_replay_without_poor_option():
    rows=data(); by_id={p['place_id']:p for p in rows.to_dict('records')}
    options={('food0',):(0.1,[by_id['food0']]),('food1',):(0.12,[by_id['food1']]),
             ('food2',):(0.4,[by_id['food2']])}
    seen=set()
    for seed in range(20):
        selected=policy.select(options,1,seed,visit_groups(rows),True)
        repeated=policy.select(dict(reversed(list(options.items()))),1,seed,visit_groups(rows),True)
        assert signatures(selected)==signatures(repeated)
        seen.add(signatures(selected)[0])
    assert seen=={('food0',),('food1',)}


def test_search_retains_earlier_visit_options_in_large_final_beam():
    rows=data(foods=4,parks=2,cafes=600)
    rows.loc[rows['place_id'].eq('food0'),'방문자수']=110
    rows.loc[rows['place_id'].eq('cafe599'),'방문자수']=0
    courses,info=search_courses(rows,[['한식'],['공원'],['카페']],[],app.filter_keywords,
        n=3,start=ORIGIN,beam_width=64,randomize=True,seed=77)
    assert len(set(signatures(courses)))==3
    assert info['course_diversity']['similar_pair_count']==0
    assert info['search_stats']['beam_distance_evaluations'] <= 4_000_000


def test_order_swaps_of_same_visits_do_not_count_as_different_compositions():
    paths=[('a','b','c'),('b','a','c')]
    assert policy.summary(paths)['max_shared_visits']==3
    assert policy.summary(paths)['similar_pair_count']==1


@pytest.mark.parametrize('value',[1,'true',None,[]])
def test_randomization_flag_requires_boolean(value):
    with pytest.raises(ValueError):
        search_courses(data(),[['공원']],[],app.filter_keywords,randomize=value)
    response=app.app.test_client().post('/recommend/course',json=dict(
        user_lat=ORIGIN[0],user_lng=ORIGIN[1],randomize=value))
    assert response.status_code==400


def test_full_pool_allocation_finds_disjoint_routes_outside_popular_beam():
    rows = data(foods=5, parks=5, cafes=200)
    for kind in ('food', 'park', 'cafe'):
        rows.loc[rows.place_id.eq(kind+'0'), '방문자수'] = 1000000
    courses, info = search_courses(rows, [['한식'], ['공원'], ['카페']], [],
        app.filter_keywords, start=ORIGIN, n=3, beam_width=1)
    ids = [pid for course in signatures(courses) for pid in course]
    assert len(ids) == len(set(ids)) == 9
    assert info['course_diversity']['zero_overlap_feasible'] is True
    assert info['course_diversity']['repeated_visit_count'] == 0
    assert info['constraints_relaxed'] == []


def test_global_matching_reserves_scarce_candidates_for_later_courses():
    rows = data(foods=4, parks=0, cafes=0)
    rows['카테고리'] = ['한식 카페', '한식', '한식', '카페']
    rows.loc[0, '방문자수'] = 1000000
    courses, info = search_courses(rows, [['한식'], ['카페']], [],
        app.filter_keywords, start=ORIGIN, n=2)
    ids = [pid for course in signatures(courses) for pid in course]
    assert len(ids) == len(set(ids)) == 4
    assert {c[0]['place_id'] for c in courses} == {'food1', 'food2'}
    assert info['course_diversity']['zero_overlap_feasible'] is True


def test_shortage_reuses_only_park_and_reports_full_pool_infeasibility():
    courses, info = search_courses(data(foods=3, parks=1, cafes=20),
        [['한식'], ['공원'], ['카페']], [], app.filter_keywords,
        start=ORIGIN, n=3, randomize=True, seed=99)
    assert len({c[0]['place_id'] for c in courses}) == 3
    assert len({c[2]['place_id'] for c in courses}) == 3
    assert info['course_diversity']['repeated_visit_count'] == 2
    assert info['course_diversity']['zero_overlap_feasible'] is False
    assert info['slot_candidate_counts'] == [3, 1, 20]


def test_course_search_does_not_lose_candidates_at_model_pool_cap(monkeypatch):
    import travel_intent as ti
    import json
    from place_identity import ensure_ids
    rows = ensure_ids(data(foods=12, parks=12, cafes=30))
    rows['방문자수'] = list(range(len(rows)))
    monkeypatch.setattr(app, 'get_df', lambda _: rows)
    original = ti.pool_for_stage
    monkeypatch.setattr(ti, 'pool_for_stage',
        lambda frame, cats, limit, filter_fn, audit: original(frame, cats, 1, filter_fn, audit))
    def rank(system, message, **kwargs):
        if system != ti.SELECTION_SYSTEM:
            return dict(schema_version=1, companion=None, exclusions=[], ambiguities=[],
                unsupported=[], requested_visit_count=None, stages=[
                    dict(id=f's{i+1}', activity=label, quote=label, category_filters=[cat],
                         conditions=[], preferences=[])
                    for i, (label, cat) in enumerate([('식사', '한식'), ('산책', '공원'), ('카페', '카페')])])
        payload = json.loads(message)
        return {'courses': [[dict(stage_id=payload['stages'][i]['id'],
            place_id=payload['candidates'][i][idx]['place_id'],
            evidence_refs=[e['id'] for e in payload['candidates'][i][idx]['evidence']],
            reason_codes=['category_match'], satisfied_condition_ids=[], unverified_condition_ids=[])
            for i, idx in enumerate(course)] for course in payload['reference_indices']]}
    monkeypatch.setattr(app, '_call_claude', rank)
    response = app.app.test_client().post('/recommend/course', json=dict(
        region='천안', transport='대중교통', user_lat=ORIGIN[0], user_lng=ORIGIN[1],
        count=3, spot_count=3, slot_types=['음식', '자연·산책', '카페'],
        persona_tags=['친구와'], user_text='식사하고 산책 후 카페', intent_version=1, plan_mode='manual', seed=8))
    assert response.status_code == 200, response.json
    ids = [p['place_id'] for course in response.json['courses'] for p in course]
    assert len(ids) == len(set(ids)) == 9
    assert response.json['metadata']['course_search_candidate_counts'] == [12, 12, 30]
    assert response.json['metadata']['selection_method'] == 'ai_candidates'
