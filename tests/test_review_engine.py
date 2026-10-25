"""ENG-01–04: kind/scope interpretation and recommendation-only visit uniqueness."""
import pandas as pd
import pytest

import app
from place_identity import ensure_ids
from Flask_server.recommender import search as engine
from Flask_server.recommender.visits import visit_key

ORIGIN = (36.8082, 127.1506)
BASE = dict(region='천안', user_lat=ORIGIN[0], user_lng=ORIGIN[1], transport='대중교통')


def place(pid, name=None, address='충남 천안시 중앙로 10', category='카페', **kw):
    return dict(provider='naver', provider_place_id=str(pid), 가게명=name or f'장소{pid}',
                주소=address, 카테고리=category, latitude=ORIGIN[0], longitude=ORIGIN[1],
                방문자수=10, 블로그수=0, **kw)


@pytest.mark.parametrize('kind', ['파스타', '샐러드', '아이스크림', '디저트', '막걸리', '도시락', '닭갈비'])
@pytest.mark.parametrize('alias', ['맛집', '밥집', '음식점'])
def test_concrete_kind_survives_food_alias_offline(kind, alias):
    assert app.extract_spot_category(f'{kind} {alias}') == [kind]


@pytest.mark.parametrize('kind', ['파스타', '샐러드', '아이스크림', '막걸리', '도시락'])
@pytest.mark.parametrize('model_alias', ['맛집', '음식점'])
def test_correct_concrete_kind_survives_generic_model_result(monkeypatch, kind, model_alias):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': [model_alias]})
    assert app.extract_spot_category(f'카페 말고 {kind} 맛집') == [kind]


@pytest.mark.parametrize('text', ['카페가 아닌 곳은 싫어요', '카페 말고는 가지 않을래요',
    '카페는 싫지 않아요', '카페 말고도 좋아요', '카페는 아니지 않아요',
    '카페는 아니어도 좋아요', '카페는 제외하지 말아줘', '카페가 아닌 곳은 가지 않을래요'])
def test_qualified_or_double_negation_keeps_correct_model_target(monkeypatch, text):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': ['카페']})
    assert app.excluded_categories(text) == []
    assert app.extract_spot_category(text) == ['카페']


def test_choice_is_not_a_hard_exclusion(monkeypatch):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': ['카페','공원']})
    assert app.excluded_categories('카페 아니면 공원') == []
    assert set(app.extract_spot_category('카페 아니면 공원')) == {'카페','공원'}


@pytest.mark.parametrize('text,banned', [('카페 말고 공원', ['카페']),
    ('카페는 싫어 공원', ['카페']), ('카페 아닌 공원', ['카페']),
    ('카페 말고 키즈카페', ['카페']), ('키즈카페 말고 카페', ['키즈카페'])])
def test_direct_exclusions_still_override_wrong_model(monkeypatch, text, banned):
    assert app.excluded_categories(text) == banned
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': banned})
    with pytest.raises(ValueError):
        app.extract_spot_category(text)


@pytest.mark.parametrize('text,target', [('공원 근처 카페', '카페'), ('카페 옆 공원', '공원'),
    ('박물관 주변에 있는 샐러드 맛집', '샐러드'), ('공원에서 가까운 카페', '카페'),
    ('공원 근처 카페 근처 박물관', '박물관'), ('아산 카페', '카페')])
def test_landmark_mentions_are_not_alternative_kinds(text, target):
    assert app.extract_spot_category(text) == [target]


def test_explicit_multiple_kinds_remain_supported():
    assert set(app.extract_spot_category('카페와 공원을 추천해줘')) == {'카페', '공원'}


def test_spot_kind_and_spatial_limitation_are_exposed(monkeypatch):
    frame = ensure_ids(pd.DataFrame([place('1', category='공원'), place('2')]))
    monkeypatch.setattr(app, 'get_df', lambda region='': frame.copy())
    response = app.app.test_client().post('/recommend/spot', json={**BASE, 'user_text':'공원 근처 카페'})
    assert response.status_code == 200
    assert [p['place_id'] for p in response.json['places']] == ['naver:2']
    assert response.json['metadata']['category_filters'] == ['카페']
    assert response.json['metadata']['spatial_relation_limitation']


def duplicate_frame():
    return ensure_ids(pd.DataFrame([place(i, '같은카페') for i in (111, 222, 333)]))


def test_spot_counts_visits_without_rewriting_provider_ids(monkeypatch):
    frame = duplicate_frame()
    before = frame.copy(deep=True)
    monkeypatch.setattr(app, 'get_df', lambda region='': frame.copy())
    response = app.app.test_client().post('/recommend/spot', json={**BASE, 'user_text':'카페', 'count':3})
    assert response.status_code == 200
    assert len(response.json['places']) == response.json['metadata']['returned_count'] == 1
    assert response.json['metadata']['reason'] == 'insufficient_candidates'
    assert response.json['places'][0]['place_id'] == 'naver:111'
    pd.testing.assert_frame_equal(frame, before)


def test_highest_ranked_provider_variant_is_kept_with_original_fields(monkeypatch):
    frame = duplicate_frame()
    frame.loc[1, '방문자수'] = 1000
    before = frame.copy(deep=True)
    monkeypatch.setattr(app, 'get_df', lambda region='': frame.copy())
    response = app.app.test_client().post('/recommend/spot', json={**BASE, 'user_text':'카페','count':3})
    assert response.status_code == 200
    assert [p['place_id'] for p in response.json['places']] == ['naver:222']
    courses, _ = engine.search_courses(frame, [['카페']], [], app.filter_keywords, n=3, start=ORIGIN)
    assert [p['place_id'] for p in courses[0]] == ['naver:222']
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize('beam', [False, True])
def test_identical_visits_cannot_fill_multiple_course_slots(monkeypatch, beam):
    if beam:
        monkeypatch.setattr(engine, 'EXACT_COMBINATIONS', 0)
    frame = duplicate_frame()
    response_client = app.app.test_client()
    monkeypatch.setattr(app, 'get_df', lambda region='': frame.copy())
    response = response_client.post('/recommend/course', json={**BASE, 'slot_types':['카페']*3, 'count':5})
    assert response.status_code == 422
    assert response.json['metadata']['slot_candidate_counts'] == [1, 1, 1]
    assert response.json['metadata']['reason'] == 'insufficient_distinct_places'
    assert frame['place_id'].nunique() == 3


@pytest.mark.parametrize('beam', [False, True])
def test_alternatives_are_unique_visit_sequences_not_provider_variants(monkeypatch, beam):
    if beam:
        monkeypatch.setattr(engine, 'EXACT_COMBINATIONS', 0)
        monkeypatch.setattr(engine, 'BEAM_DISTANCE_BUDGET', 1)
    frame = ensure_ids(pd.DataFrame([place(i, name) for i, name in
        [(11,'카페A'), (12,'카페A'), (21,'카페B'), (22,'카페B')]]))
    courses, info = engine.search_courses(frame, [['카페']]*2, [], app.filter_keywords,
        n=10, start=ORIGIN, beam_width=1)
    assert {tuple(p['가게명'] for p in c) for c in courses} == {('카페A','카페B'),('카페B','카페A')}
    assert len(courses) == 2
    assert info['reason'] == 'insufficient_unique_courses'
    assert info['candidate_space_exhausted']
    shuffled, _ = engine.search_courses(frame.sample(frac=1, random_state=7), [['카페']]*2,
        [], app.filter_keywords, n=10, start=ORIGIN, beam_width=1)
    assert courses == shuffled


def test_completion_uses_visit_groups_when_provider_variant_could_reuse_cafe(monkeypatch):
    frame = ensure_ids(pd.DataFrame([
        place(11,'복합카페',category='공원 카페'), place(12,'복합카페',category='공원 카페'),
        place(21,'다른공원',category='공원')]))
    frame.loc[2, 'latitude'] += .001
    monkeypatch.setattr(engine, 'EXACT_COMBINATIONS', 0)
    monkeypatch.setattr(engine, 'BEAM_DISTANCE_BUDGET', 1)
    courses, info = engine.search_courses(frame, [['공원'],['카페']], [], app.filter_keywords,
        n=5, start=ORIGIN, beam_width=1)
    assert len(courses) == 1
    assert [p['가게명'] for p in courses[0]] == ['다른공원', '복합카페']
    assert info['search_stats']['completion_prefixes'] > 0
    assert info['search_stats']['completion_matching_checks'] > 0
    assert info['candidate_space_exhausted']


def test_category_variants_do_not_hide_a_feasible_slot():
    frame = ensure_ids(pd.DataFrame([
        place(11,'복합시설',category='카페'), place(12,'복합시설',category='공원'),
        place(21,'다른카페',category='카페')]))
    courses, _ = engine.search_courses(frame, [['카페'],['공원']], [], app.filter_keywords,
        n=5, start=ORIGIN)
    assert len(courses) == 1
    assert [p['place_id'] for p in courses[0]] == ['naver:21', 'naver:12']


@pytest.mark.parametrize('change', [
    {'가게명':'같은카페 별관'}, {'가게명':'같은카페 부속매점'},
    {'주소':'충남 천안시 중앙로 12'}, {'주소':'충남 천안시 중앙로 10 1층'},
    {'주소':'충남 천안시 중앙로 10 2층'}, {'주소':'충남 천안시 중앙로 10 101호'},
    {'latitude':ORIGIN[0]+.0000001}, {'longitude':ORIGIN[1]+.0000001},
])
def test_same_name_building_branches_floors_and_nearby_coords_remain_distinct(change):
    one, two = place(11,'같은카페'), {**place(12,'같은카페'), **change}
    frame = ensure_ids(pd.DataFrame([one,two]))
    courses, _ = engine.search_courses(frame, [['카페']]*2, [], app.filter_keywords,
        n=2, start=ORIGIN)
    assert len(courses) == 2
    assert all(len({visit_key(p) for p in c}) == 2 for c in courses)


def test_incomplete_address_is_not_enough_to_group_same_named_provider_rows():
    frame = ensure_ids(pd.DataFrame([place(i,'동명장소',address='충남 천안시') for i in (11,12)]))
    courses, _ = engine.search_courses(frame, [['카페']]*2, [], app.filter_keywords, n=2, start=ORIGIN)
    assert len(courses) == 2  # Low-level engine; runtime quality filtering is a separate guard.
