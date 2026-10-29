import itertools
import numpy as np
import pandas as pd
import pytest
import app
from recommendation_ai import generate_from_slots, generate_fixed_courses, search_courses, route_metrics, add_scores


def test_direct_scoring_ignores_unverified_tags(places):
    p = places.head(3).copy()
    p['blog_tags'] = '{"조용한카페": 1}'
    assert add_scores(p, ['조용한'])['tag_score'].eq(0).all()
    p['blog_tag_status'] = ['verified', 'legacy_unverified', 'fetch_error']
    assert add_scores(p, ['조용한'])['tag_score'].tolist() == [1, 0, 0]


def test_synthetic_verified_taste_changes_rank_with_same_candidates(places):
    p = places.head(2).copy()
    p['카테고리'], p['방문자수'], p['블로그수'] = '카페', 0, 0
    p['blog_tag_status'] = 'verified'
    p['blog_tags'] = ['{"조용한":1}', '{"활기찬":1}']
    quiet = add_scores(p, ['조용한'])
    lively = add_scores(p, ['활기찬'])
    assert quiet['tag_score'].tolist() == [1, 0]
    assert lively['tag_score'].tolist() == [0, 1]
    assert quiet['score'].idxmax() == 0 and lively['score'].idxmax() == 1
from clustering_ai import perform_clustering

ORIGIN = (36.8151, 127.1139)
SLOTS = ['음식', '자연·산책', '카페']


def ids(courses):
    return [tuple(p['place_id'] for p in course) for course in courses]


def test_more_courses_than_clusters_and_repeatability(places):
    a = generate_from_slots(places, SLOTS, [], app.filter_keywords, n=5, start=ORIGIN, seed=42)
    b = generate_from_slots(places, SLOTS, [], app.filter_keywords, n=5, start=ORIGIN, seed=42)
    assert len(a) == 5 and len(set(ids(a))) == 5 and ids(a) == ids(b)
    for course in a:
        assert [p['카테고리'] for p in course] == ['한식', '공원', '카페']
        assert len({p['place_id'] for p in course}) == 3


def test_fixed_count_not_limited_by_cluster(places):
    p = places.copy()
    p.loc[p.index[3::6], '카테고리'] = '박물관'
    courses = generate_fixed_courses(p, [], app.filter_keywords, n=5, spots=5, start=ORIGIN)
    assert len(courses) == 5
    assert all([p['카테고리'] for p in c] == ['한식', '공원', '카페', '박물관', '한식'] for c in courses)


def test_same_name_different_addresses_allowed(places):
    p = places.head(3).copy()
    p['가게명'] = '아지트'
    courses = generate_from_slots(p, SLOTS, [], app.filter_keywords, n=5, start=ORIGIN)
    assert len(courses) == 1 and len(set(ids(courses)[0])) == 3


def test_route_selection_accounts_for_origin_and_legs(places):
    p = places.head(6).copy()
    p['방문자수'] = 0
    p['longitude'] = [127.11, 127.11, 127.11, 127.14, 127.14, 127.14]
    west = generate_from_slots(p, SLOTS, [], app.filter_keywords, n=1, start=(36.8151, 127.11))[0]
    east = generate_from_slots(p, SLOTS, [], app.filter_keywords, n=1, start=(36.8151, 127.14))[0]
    assert [r['가게명'] for r in west] == ['장소0', '장소1', '장소2']
    assert [r['가게명'] for r in east] == ['장소3', '장소4', '장소5']
    # For equal relevance and small pools, compare all feasible Cartesian routes.
    pools = [app.filter_keywords(p, app.SLOT_CATEGORY_MAP[s], []).to_dict('records') for s in SLOTS]
    optimum = min(sum(route_metrics(c, (36.8151, 127.11))['leg_distances_km']) for c in itertools.product(*pools))
    assert route_metrics(west, (36.8151, 127.11))['estimated_distance_km'] <= optimum + .003
    assert route_metrics(west, ORIGIN)['travel_time_minutes'] is None


def test_missing_categories_and_matching_impossibility(places):
    courses, info = search_courses(places.head(1), [['카페']], [], app.filter_keywords, n=2, start=ORIGIN)
    assert courses == [] and info['reason'] == 'missing_slot_candidates'
    courses, info = search_courses(places.head(1), [['한식'], ['한식']], [], app.filter_keywords, start=ORIGIN)
    assert courses == [] and info['reason'] == 'insufficient_distinct_places'
    assert info['constraints_relaxed'] == []


def test_feasibility_completion_survives_beam_pruning(places):
    p = places.head(2).copy()
    p['카테고리'] = ['공원 카페', '공원']
    p['방문자수'] = 0
    # Greedy would use the sole cafe in slot 1, losing slot 2.
    c, info = search_courses(p, [['공원'], ['카페']], [], app.filter_keywords, n=1,
                            start=ORIGIN, beam_width=1)
    assert len(c) == 1 and [r['가게명'] for r in c[0]] == ['장소1', '장소0']


def test_empty_invalid_coordinates_zero_and_malformed_tags(places):
    assert generate_from_slots(places.head(0), SLOTS, [], app.filter_keywords, start=ORIGIN) == []
    p = places.head(6).copy()
    p['방문자수'] = [-5, None, 0, 'bad', 0, 0]
    p['blog_tags'] = ['bad', None, '{}', '[]', '{}', '{}']
    p.loc[3, 'latitude'] = np.nan
    scores = add_scores(p, ['일치하지않음'])
    assert scores['score'].notna().all() and scores['score'].eq(0).all()
    assert len(generate_from_slots(p, SLOTS, [], app.filter_keywords, n=1, start=ORIGIN)) == 1


def test_duplicate_coordinate_clustering_and_seed(places):
    p = places.head(5).copy()
    p['latitude'] = ORIGIN[0]
    p['longitude'] = ORIGIN[1]
    assert perform_clustering(p)['Cluster'].nunique() == 1
    assert perform_clustering(places.head(0)).empty
    assert perform_clustering(places, seed=42)['Cluster'].equals(perform_clustering(places, seed=42)['Cluster'])


def test_literal_category_actual_wins_search_hint(places):
    p = places.head(2).copy()
    p['search_category'] = '닭갈비'
    assert app.filter_keywords(p, ['닭갈비'], []).empty
    assert app.filter_keywords(p, ['.*'], []).empty
    p['카테고리'] = ['해산물', '산,고개']
    assert app.filter_keywords(p, ['산'], [])['가게명'].tolist() == ['장소1']


@pytest.fixture
def client(monkeypatch, places):
    from place_identity import ensure_ids
    monkeypatch.setattr(app, 'get_df', lambda region: ensure_ids(places))
    return app.app.test_client()


def payload(**kwargs):
    return {'user_lat': ORIGIN[0], 'user_lng': ORIGIN[1], 'transport': '대중교통', **kwargs}


def test_api_explicit_chicken_not_broadened(client, monkeypatch, places):
    from place_identity import ensure_ids
    p = places.copy()
    p.loc[0, '카테고리'] = '닭갈비'
    monkeypatch.setattr(app, 'get_df', lambda region: ensure_ids(p))
    response = client.post('/recommend/spot', json=payload(user_text='닭갈비', persona_tags=['맛집 탐방']))
    assert response.status_code == 200
    data = response.get_json()
    assert data['metadata']['category_filters'] == ['닭갈비']
    assert len(data['places']) == 1 and data['places'][0]['category'] == '닭갈비'
    assert data['places'][0]['place_id']


def test_api_course_constraints_and_count(client):
    response = client.post('/recommend/course', json=payload(slot_types=SLOTS, spot_count=3, count=5,
                                                             persona_tags=['힐링/여유'], seed=42))
    assert response.status_code == 200
    data = response.get_json()
    assert len(data['courses']) == 5
    assert data['metadata']['returned_count'] == 5 and data['metadata']['constraints_relaxed'] == []
    assert data['course_metrics'][0]['travel_time_minutes'] is None
    assert data['metadata']['distance_method'] == 'coordinate_great_circle'


@pytest.mark.parametrize('changes', [{'slot_types': ['잘못된슬롯']}, {'slot_types': SLOTS, 'spot_count': 5},
    {'count': 0}, {'count': '5'}, {'user_lat': 'NaN'}, {'persona_tags': '힐링'}, {'transport': ['차']},
    {'transport': '비행기'}, {'region': '서울'}, {'seed': True}, {'slot_types': [None]}])
def test_invalid_requests_are_client_errors(client, changes):
    response = client.post('/recommend/course', json=payload(**changes))
    assert response.status_code == 400
    assert response.get_json()['reason'] == 'invalid_request'


def test_impossible_partial_and_llm_failure(client, monkeypatch, places):
    from place_identity import ensure_ids
    monkeypatch.setattr(app, 'get_df', lambda region: ensure_ids(places.head(3)))
    partial = client.post('/recommend/course', json=payload(slot_types=SLOTS, count=5)).get_json()
    assert len(partial['courses']) == 1
    assert partial['metadata']['reason'] == 'insufficient_unique_courses'
    missing = client.post('/recommend/course', json=payload(slot_types=['음식', '음식', '음식']))
    assert missing.status_code == 422 and missing.get_json()['courses'] == []
    assert missing.get_json()['metadata']['reason'] == 'insufficient_distinct_places'
    llm = client.post('/recommend/spot', json=payload(user_text='도자기 만드는 곳'))
    assert llm.status_code == 503
    malformed = client.post('/recommend/course', data='[]', content_type='application/json')
    assert malformed.status_code == 400


def test_all_distinct_courses_when_coordinates_overlap(places):
    p = places.head(5).copy()
    p['latitude'] = ORIGIN[0]
    p['longitude'] = ORIGIN[1]
    c, info = search_courses(p, [app.SLOT_CATEGORY_MAP[s] for s in SLOTS], [],
                            app.filter_keywords, n=5, start=ORIGIN)
    assert len(c) == 4 and len(set(ids(c))) == 4
    assert info['reason'] == 'insufficient_unique_courses'
    assert all(route_metrics(course, ORIGIN)['estimated_distance_km'] == 0 for course in c)


def test_malformed_llm_preference_remains_soft(client, monkeypatch):
    monkeypatch.setattr(app, '_call_claude', lambda *a, **k: {'blog_tag_keywords': 'bad'})
    response = client.post('/recommend/course', json=payload(slot_types=SLOTS, count=5,
                                                             persona_tags=['맛집 탐방']))
    assert response.status_code == 200
    assert len(response.get_json()['courses']) == 5


def test_generic_food_word_does_not_broaden_explicit_type(client, monkeypatch, places):
    from place_identity import ensure_ids
    p = places.copy()
    p.loc[0, '카테고리'] = '닭갈비'
    monkeypatch.setattr(app, 'get_df', lambda region: ensure_ids(p))
    response = client.post('/recommend/spot', json=payload(user_text='닭갈비 음식점', persona_tags=['맛집 탐방']))
    assert response.status_code == 200
    assert response.get_json()['metadata']['category_filters'] == ['닭갈비']
    assert len(response.get_json()['places']) == 1


def test_negated_category_is_not_inferred_as_wanted_when_llm_fails(client):
    response = client.post('/recommend/spot', json=payload(user_text='닭갈비 말고 카페'))
    assert response.status_code == 503
    assert response.get_json()['reason'] == 'category_unavailable'
