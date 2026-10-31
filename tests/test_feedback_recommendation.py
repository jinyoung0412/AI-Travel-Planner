"""28 October feedback: real set variation, explicit order and grounded context."""
import copy
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import app
import travel_intent as ti
from api_request import parse_recommendation
from family_policy import filter_child_candidates
from intent_context import context_only
from place_identity import ensure_ids
from recommender import spot_quality
from recommender.constants import CORE_ACTIVITY_LABELS, SLOT_CATEGORY_MAP

ORIGIN = dict(user_lat=36.8013, user_lng=127.13587, region='천안', transport='대중교통', count=3,
              persona_tags=['연인과', '로맨틱한', '기념일'], intent_version=1, plan_mode='natural', seed=3)
TEXT = '여자친구랑 100일기념 데이트'


def unresolved(text=TEXT):
    return dict(schema_version=1, companion=dict(value='연인과', quote='여자친구'), stages=[],
        exclusions=[], ambiguities=[dict(quote=text, reason='원하는 활동 선택')],
        unsupported=[dict(quote='100일기념', reason='기념일 분위기 추가 요구사항 확인 필요')],
        requested_visit_count=None)


def frame(kinds=('한식', '공원', '카페', '공방', '박물관', '볼링')):
    return ensure_ids(pd.DataFrame([dict(가게명=f'추천시설{i}', 주소=f'충남 천안시 중앙로 {i+1}', 지역='천안',
        카테고리=kind, latitude=36.8013+i*.00001, longitude=127.13587, 방문자수=100,
        블로그수=0, blog_tags='{}', blog_tag_status='legacy_unverified') for i, kind in enumerate(kinds)]))


def install(monkeypatch, plan, data=None):
    calls = []
    monkeypatch.setattr(app, 'get_df', lambda _: frame() if data is None else data)
    def model(system, message, **kwargs):
        calls.append(system)
        if system == ti.SELECTION_SYSTEM:
            raise TimeoutError()
        return copy.deepcopy(plan)
    monkeypatch.setattr(app, '_call_claude', model)
    return app.app.test_client(), calls


@pytest.mark.parametrize('activity', CORE_ACTIVITY_LABELS)
def test_100day_activity_choice_is_exact_or_without_second_interpretation(monkeypatch, activity):
    client, calls = install(monkeypatch, unresolved())
    body = dict(ORIGIN, mode='spot', user_text=TEXT)
    preview = client.post('/travel/interpret', json=body)
    assert preview.status_code == 200 and preview.json['clarification_required']
    selected = {**body, 'activity_choice': activity, 'clarification_token': preview.json['clarification']['token']}
    resolved = client.post('/travel/interpret', json=selected)
    assert resolved.status_code == 200, resolved.json
    plan = resolved.json['travel_request']
    assert len(plan['stages']) == 1
    assert plan['stages'][0]['category_filters'] == SLOT_CATEGORY_MAP[activity]
    assert not plan['unsupported'] and not plan['ambiguities']
    assert plan['context_requests'][0]['quote'] == '100일기념'
    assert len(calls) == 1
    result = client.post('/recommend/spot', json={**selected, 'intent_token': resolved.json['intent_token']})
    assert result.status_code == 200, result.json
    assert result.json['metadata']['constraints_relaxed'] == []
    assert len(calls) == 2  # one interpretation, one bounded selection, no choice reinterpretation


def test_100day_craft_shortage_is_candidates_not_interpretation(monkeypatch):
    client, calls = install(monkeypatch, unresolved(), frame(('카페',)))
    body = dict(ORIGIN, mode='spot', user_text=TEXT)
    original = client.post('/travel/interpret', json=body).json
    chosen = {**body, 'activity_choice': '체험', 'clarification_token': original['clarification']['token']}
    preview = client.post('/travel/interpret', json=chosen).json
    result = client.post('/recommend/spot', json={**chosen, 'intent_token': preview['intent_token']})
    assert result.status_code == 422
    assert result.json['reason'] == 'insufficient_candidates'
    assert result.json['metadata']['candidate_counts'] == [0]
    assert len(calls) == 1


def test_manual_course_order_satisfies_missing_activity_without_question(monkeypatch):
    client, calls = install(monkeypatch, unresolved())
    body = dict(ORIGIN, mode='course', user_text=TEXT, plan_mode='manual', spot_count=3,
                slot_types=['음식', '자연·산책', '카페'])
    preview = client.post('/travel/interpret', json=body)
    assert preview.status_code == 200, preview.json
    assert preview.json['clarification_required'] is False
    plan = preview.json['travel_request']
    assert [s['activity'] for s in plan['stages']] == body['slot_types']
    assert not plan['ambiguities'] and not plan['unsupported']
    result = client.post('/recommend/course', json={**body, 'intent_token': preview.json['intent_token']})
    assert result.status_code == 200, result.json
    assert [p['category'] for p in result.json['courses'][0]] == ['한식', '공원', '카페']
    assert len(calls) == 2


def test_selected_activity_tag_already_supplies_spot_activity(monkeypatch):
    client, _ = install(monkeypatch, unresolved())
    body = dict(ORIGIN, mode='spot', user_text=TEXT, persona_tags=['연인과', '기념일', '체험 공방'])
    preview = client.post('/travel/interpret', json=body)
    assert preview.status_code == 200
    assert preview.json['clarification_required'] is False
    assert preview.json['travel_request']['stages'][0]['category_filters'] == SLOT_CATEGORY_MAP['체험']


def test_manual_reorder_moves_conditions_with_matching_kind(monkeypatch):
    text = '실내 카페 다음 산책'
    plan = dict(schema_version=1, companion=None, stages=[
        dict(id='s1', activity='카페', quote='실내 카페', category_filters=['카페'], preferences=[],
             conditions=[dict(field='indoor', quote='실내', value=True, required=True)]),
        dict(id='s2', activity='산책', quote='산책', category_filters=['공원'], conditions=[], preferences=[])],
        exclusions=[], ambiguities=[], unsupported=[], requested_visit_count=None)
    client, _ = install(monkeypatch, plan)
    body = dict(ORIGIN, mode='course', user_text=text, plan_mode='manual', spot_count=3,
        persona_tags=[], slot_types=['음식', '자연·산책', '카페'])
    preview = client.post('/travel/interpret', json=body)
    assert preview.status_code == 200, preview.json
    stages = preview.json['travel_request']['stages']
    assert not stages[0]['conditions'] and not stages[1]['conditions']
    assert stages[2]['conditions'][0]['id'] == 's3.c1'
    result = client.post('/recommend/course', json={**body, 'intent_token': preview.json['intent_token']})
    assert result.status_code == 422 and result.json['reason'] == 'unverified_conditions'


@pytest.mark.parametrize('quote', ['100명 예약 필수', '기념일 휠체어 경사도 10도 이하', '생일 반드시 영업 중'])
def test_occasion_normalization_keeps_actual_unresolved_conditions(monkeypatch, quote):
    plan = unresolved(quote)
    plan['unsupported'] = [dict(quote=quote, reason='자료 없는 필수 조건')]
    client, _ = install(monkeypatch, plan)
    body = dict(ORIGIN, mode='course', user_text='여자친구 ' + quote, plan_mode='manual', spot_count=3,
                slot_types=['음식', '자연·산책', '카페'])
    result = client.post('/travel/interpret', json=body)
    assert result.status_code == 422
    assert result.json['reason'] == 'intent_conflict'
    assert not context_only(quote)


@pytest.mark.parametrize('bad', [None, 'id', [None], [''], ['x'*201], ['x']*101])
def test_history_schema_rejects_invalid_before_model(bad):
    with pytest.raises(ValueError):
        parse_recommendation({**ORIGIN, 'recent_place_ids': bad})


def test_history_is_validated_deduplicated_but_not_intent_change():
    first = parse_recommendation(ORIGIN)
    second = parse_recommendation({**ORIGIN, 'recent_place_ids': ['p1', 'p1', 'p2']})
    assert second['recent_place_ids'] == ['p1', 'p2']
    assert ti.fingerprint(first, 'spot') == ti.fingerprint(second, 'spot')
    token = ti.sign_plan({'test': True}, first, 'spot')
    assert ti.read_plan(token, second, 'spot') == {'test': True}


def test_history_changes_membership_with_bounded_cost_and_distinct_visits(monkeypatch):
    data = frame(('공방',)*30)
    client, _ = install(monkeypatch, unresolved(), data)
    body = {k:v for k,v in ORIGIN.items() if k not in ('intent_version', 'plan_mode')}
    body.update(count=10, persona_tags=['체험 공방'], seed=1, randomize=True)
    first = client.post('/recommend/spot', json=body)
    ids = {p['place_id'] for p in first.json['places']}
    second = client.post('/recommend/spot', json={**body, 'seed':2, 'recent_place_ids': sorted(ids)})
    assert second.status_code == 200
    new_ids = {p['place_id'] for p in second.json['places']}
    assert len(new_ids) == 10 and not ids.intersection(new_ids)
    info = second.json['metadata']['recommendation_variation']
    assert info['repeated_count'] == 0 and info['new_count'] == 10
    scored = app.add_scores(app.filter_radius(data, body['user_lat'],body['user_lng'],body['transport']), [])
    costs = sorted(spot_quality.cost(r,body['transport']) for r in scored[scored.place_id.isin(new_ids)].to_dict('records'))
    assert all(actual <= limit+1e-9 for actual,limit in zip(costs, info['quality_limits']))


def test_history_shortage_never_drops_count_or_expands_quality(monkeypatch):
    data = frame(('공방',)*3)
    client, _ = install(monkeypatch, unresolved(), data)
    body = {k:v for k,v in ORIGIN.items() if k not in ('intent_version', 'plan_mode')}
    body.update(count=10, persona_tags=['체험 공방'], recent_place_ids=data.place_id.tolist())
    result = client.post('/recommend/spot',json=body)
    assert result.status_code == 200 and len(result.json['places']) == 3
    assert result.json['metadata']['reason'] == 'insufficient_candidates'
    assert result.json['metadata']['recommendation_variation']['repeated_count'] == 3
    assert result.json['metadata']['constraints_relaxed'] == []


def test_inferred_indoor_and_mood_tags_cannot_pass_model_answer(monkeypatch):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'tags': ['부모님 모시고','문화·역사 탐방', '실내 위주','감성적인', '로맨틱한']})
    result = app.app.test_client().post('/suggest/tags',json={'user_text':'부모님과 전시 보러 가요'})
    assert result.json['tags'] == ['부모님 모시고','문화·역사 탐방']


def test_adult_exhibition_excludes_child_museum_but_explicit_child_place_is_valid():
    data = frame(('박물관',)*3)
    data.loc[0, '가게명'] = '천안 어린이박물관'
    data.loc[1, '가게명'] = '어린이 그림을 전시하는 일반 미술관'
    filtered, info = filter_child_candidates(data, {'user_text':'부모님과 전시', 'persona_tags':['부모님 모시고']})
    assert len(filtered) == 2 and info['excluded_count'] == 1
    filtered, info = filter_child_candidates(data, {'user_text':'어린이박물관', 'persona_tags':['부모님 모시고']})
    assert len(filtered) == 3
    filtered, _ = filter_child_candidates(data, {'user_text':'어린이박물관 말고 박물관', 'persona_tags':['부모님 모시고']})
    assert len(filtered) == 2


@pytest.mark.parametrize('region', ['천안', '아산', '내 주변', ''])
def test_source_address_filters_anseong_even_when_region_column_and_coordinates_lie(monkeypatch, region):
    data = frame(('공방',)*3)
    data.loc[0, '주소'] = '경기 안성시 공도읍 중앙로 1'
    data.loc[1, '주소'] = '충남 아산시 중앙로 2'
    data.loc[1, '지역'] = '아산'
    data = ensure_ids(data.drop(columns=['place_id', 'identity_key', 'identity_aliases', 'identity_alias_conflicts', 'coordinate_identity_key']))
    client, _ = install(monkeypatch, unresolved(), data)
    body = {k:v for k,v in ORIGIN.items() if k not in ('intent_version','plan_mode')}
    body.update(region=region,persona_tags=['체험 공방'])
    result = client.post('/recommend/spot',json=body)
    assert result.status_code == 200
    assert all('안성' not in p['address'] for p in result.json['places'])
    assert result.json['metadata']['candidate_service_area']['excluded_count'] >= 1
    if region in ('천안','아산'):
        assert all(region+'시' in p['address'] for p in result.json['places'])


def test_natural_spot_rejects_model_reusing_old_set_when_equal_quality_alternatives_exist(monkeypatch):
    data = frame(('공방',)*30)
    p = dict(schema_version=1, companion=None, stages=[dict(id='s1', activity='공방', quote='공방',
        category_filters=['공방'], conditions=[], preferences=[])], exclusions=[], ambiguities=[],
        unsupported=[], requested_visit_count=None)
    client, _ = install(monkeypatch, p, data)
    body = dict(ORIGIN, user_text='공방', count=5, persona_tags=[], randomize=True)
    first = client.post('/recommend/spot',json=body)
    assert first.status_code == 200
    prior = {place['place_id'] for place in first.json['places']}
    def repeat_model(system, message, **kwargs):
        if system != ti.SELECTION_SYSTEM:
            return copy.deepcopy(p)
        payload = json.loads(message)
        records = [r for r in payload['candidates'][0] if r['place_id'] in prior]
        return {'courses': [[dict(stage_id='s1', place_id=r['place_id'], evidence_refs=[e['id'] for e in r['evidence']],
            reason_codes=['category_match'], satisfied_condition_ids=[], unverified_condition_ids=[])] for r in records]}
    monkeypatch.setattr(app, '_call_claude', repeat_model)
    second = client.post('/recommend/spot',json={**body,'recent_place_ids':sorted(prior)})
    assert second.status_code == 200, second.json
    assert not prior.intersection(p['place_id'] for p in second.json['places'])
    assert second.json['metadata']['selection_validation_reason'] == 'selection_recent_overlap'
    assert second.json['metadata']['selection_fallback_reason'] == 'diversity_guard'


def test_history_cannot_replace_good_spot_with_a_costly_unseen_place():
    data = pd.DataFrame([dict(place_id='good',origin_distance_km=0,score=1),
                         dict(place_id='far',origin_distance_km=4.5,score=0)])
    selected, _, info = spot_quality.prefer_new(data,1,'대중교통',['good'],seed=3,randomize=True)
    assert selected.place_id.tolist() == ['good']
    assert info['repeated_count'] == 1 and info['eligible_unseen_count'] == 1


def test_manual_course_history_changes_real_visits_and_keeps_selected_order(monkeypatch):
    data = frame(('한식','공원','카페')*12)
    client, _ = install(monkeypatch, unresolved(), data)
    body = {k:v for k,v in ORIGIN.items() if k not in ('intent_version','plan_mode')}
    body.update(slot_types=['음식','자연·산책','카페'],spot_count=3,count=3,randomize=True)
    first = client.post('/recommend/course',json=body)
    prior = {p['place_id'] for course in first.json['courses'] for p in course}
    second = client.post('/recommend/course',json={**body,'recent_place_ids':sorted(prior),'seed':4})
    assert second.status_code == 200, second.json
    now = {p['place_id'] for course in second.json['courses'] for p in course}
    assert now != prior
    assert all([p['category'] for p in course] == ['한식','공원','카페'] for course in second.json['courses'])
    assert second.json['metadata']['constraints_relaxed'] == []
    assert second.json['metadata']['recommendation_variation']['new_count'] > 0


@pytest.mark.parametrize('name', ['어린이박물관','어린이미술관','단추어린이미술체험관',
    '천안어린이교통안전체험관','유아교육체험관','태학산 유아숲체험원'])
def test_named_child_education_venue_stays_out_of_adult_pool(name):
    data = frame(('박물관',))
    data.loc[0,'가게명'] = name
    filtered, meta = filter_child_candidates(data, {'persona_tags':['부모님 모시고']})
    assert filtered.empty and meta['excluded_count'] == 1
    assert len(filter_child_candidates(data, {'persona_tags':['아이와 함께']})[0]) == 1


def test_conflicting_or_unsupported_catalog_region_is_not_repaired_implicitly():
    data=frame(('공방',)*3)
    data.loc[0,'지역']='기타'
    data.loc[1,'지역']='아산'
    filtered,_=app.filter_service_candidates(data,'내 주변')
    assert filtered.place_id.tolist() == [data.iloc[2].place_id]


def test_interpretation_diagnostics_are_enumerated_without_provider_text(monkeypatch):
    client = app.app.test_client()
    monkeypatch.setattr(app, '_call_claude', lambda *a,**k: {'not':'a valid intent'})
    result=client.post('/travel/interpret',json={**ORIGIN,'mode':'spot','user_text':'공방'})
    assert result.status_code == 422
    assert result.json['metadata']['failure_code'] == 'intent_schema'
    assert ti.interpretation_failure_code(ValueError('private-provider-payload')) == 'invalid_interpretation'
    assert ti.interpretation_failure_code(ti.ModelBoundaryError('provider_timeout')) == 'provider_timeout'


@pytest.mark.parametrize('occasion', ['100일','200일','300일','1000일','1주년','2주년','10주년',
    '백일','천일','생일','기념일','프로포즈','졸업 기념','입학 기념','첫 만남','소개팅',
    '가족 나들이','일상 탈출','오랜만에 만남','로맨틱한 데이트'])
def test_twenty_soft_context_forms_do_not_block_selected_course(monkeypatch, occasion):
    text='여자친구랑 '+occasion
    p=unresolved(text)
    p['unsupported']=[dict(quote=occasion,reason='상황 분위기 추가 확인 필요')]
    client,calls=install(monkeypatch,p)
    body=dict(ORIGIN,mode='course',user_text=text,plan_mode='manual',spot_count=3,
        slot_types=['음식','자연·산책','카페'])
    response=client.post('/travel/interpret',json=body)
    assert response.status_code==200,response.json
    assert response.json['clarification_required'] is False
    assert not response.json['travel_request']['unsupported']
    assert [s['activity'] for s in response.json['travel_request']['stages']]==body['slot_types']
    assert len(calls)==1
