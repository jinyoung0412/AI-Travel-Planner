"""S04/S07: subtype contrast, bounded one-of enumeration, and HTTP controls."""
import copy

import pandas as pd
import pytest

import app
import travel_intent as ti
from family_policy import filter_child_candidates
from place_identity import ensure_ids
from test_backend_intent_guards import BASE, condition, interpret, plan, consent_fields
from test_backend_intent_guards_v2 import catalogue


@pytest.mark.parametrize('text,quote', [
    ('유아는 아니고 초등학생 아이와 함께 박물관', '아이와 함께'),
    ('유아 없이 초등학생 아이와 함께 박물관', '아이와 함께'),
    ('영아는 아니고 중학생 자녀와 함께 박물관', '자녀와 함께'),
    ('유아가 아닌 초등학생인 아이와 함께 박물관', '아이와 함께'),
    ('유아 없이 초등학생과 함께 박물관', '초등학생과 함께'),
    ('아기 없이 다른 아이와 함께 박물관', '아이와 함께'),
    ('초등학생 아이와 함께 유아 없이 박물관', '아이와 함께'),
])
def test_s04_subtype_contrast_keeps_a_separate_explicit_child_companion(monkeypatch, text, quote):
    raw = plan(('박물관', ['박물관'], []))
    raw['companion'] = dict(value='아이와 함께', quote=quote)
    preview = interpret(monkeypatch, text, raw)
    assert preview.status_code == 200
    catalogue(monkeypatch, '박물관', '합성 어린이박물관')
    result = app.app.test_client().post('/recommend/spot', json={**BASE,
        'user_text': text, 'intent_token': preview.json['intent_token']})
    assert result.status_code == 200, result.json
    assert result.json['metadata']['family_policy']['child_venues_allowed'] is True
    assert result.json['metadata']['family_policy']['excluded_count'] == 0
    assert result.json['places'][0]['source_name'] == '합성 어린이박물관'
    # This allows a candidate kind, not a verified age-suitability facility fact.
    assert {e['field'] for e in result.json['places'][0]['travel_explanation']['evidence']} == {
        'category', 'origin_distance_km'}


@pytest.mark.parametrize('text,who,allowed', [
    ('유아 없이 박물관', '아이와 함께', False),
    ('유아는 아니고 초등학생 박물관', '아이와 함께', False),
    ('유아는 아니고 어른과 박물관', '아이와 함께', False),
    ('유아 없이 아이와 함께 박물관', '아이와 함께', False),
    ('유아 없이 초등학생 아이와 함께 박물관', '유아/영아 동반', False),
    ('유아 없이 초등학생 아이와 함께 박물관', '친구와', False),
    ('유아 없이 초등학생 아이와 함께 박물관', None, False),
    ('아이 없이 유아는 아니고 초등학생 아이와 함께 박물관', '아이와 함께', False),
    ('유아 없이 초등학생 아이와 함께 가지 말고 박물관', '아이와 함께', False),
    ('유아 없이 초등학생 아이와 함께 가는 대신 친구와 박물관', '아이와 함께', False),
    ('유아 동반하지 말고 초등학생 아이와 함께 박물관', '아이와 함께', False),
    ('유아는 아니고 초등학생 아이와 함께는 싫지 않아요', '아이와 함께', True),
    ('카페 말고 아이와 박물관', '아이와 함께', True),
    ('아이 없이 박물관', '아이와 함께', False),
    ('아이 동반하지 말고 박물관', '아이와 함께', False),
    ('아이를 데려가지 말고 박물관', '아이와 함께', False),
    ('아이와 가는 대신 친구와 박물관', '아이와 함께', False),
])
def test_s04_requires_both_grounding_and_a_compatible_plan_without_overriding_direct_bans(text, who, allowed):
    frame = pd.DataFrame([dict(가게명='합성 어린이박물관', 카테고리='박물관')])
    raw = dict(companion=dict(value=who) if who else None, stages=[dict(category_filters=['박물관'])])
    selected, metadata = filter_child_candidates(frame, dict(user_text=text, persona_tags=[]), raw)
    assert metadata['child_venues_allowed'] is allowed
    assert len(selected) == int(allowed)


@pytest.mark.parametrize('tags,allowed', [(['아이와 함께'], True), (['친구와'], False)])
def test_s04_manual_companion_keeps_precedence_over_the_age_contrast(tags, allowed):
    frame = pd.DataFrame([dict(가게명='합성 어린이박물관', 카테고리='박물관')])
    raw = dict(companion=dict(value='아이와 함께'), stages=[dict(category_filters=['박물관'])])
    selected, _ = filter_child_candidates(frame, dict(
        user_text='유아 없이 초등학생 아이와 함께 박물관', persona_tags=tags), raw)
    assert len(selected) == int(allowed)


def test_s04_legacy_keeps_the_conservative_negative_scope():
    frame = pd.DataFrame([dict(가게명='합성 어린이박물관', 카테고리='박물관')])
    selected, _ = filter_child_candidates(frame, dict(
        user_text='유아 없이 초등학생 아이와 함께 박물관', persona_tags=[]))
    assert selected.empty


@pytest.mark.parametrize('text,kinds', [
    ('실내 카페와 공원 중 하나', ['카페', '공원']),
    ('실내 박물관과 공원 중 하나만', ['박물관', '공원']),
    ('실내 카페와 공원 중에서 한 곳만 추천해줘', ['카페', '공원']),
    ('실내 카페와 공원 가운데 한 곳', ['카페', '공원']),
    ('실내 카페와 공원 둘 중 하나', ['카페', '공원']),
    ('실내 카페와 박물관과 공원 중 하나', ['카페', '박물관', '공원']),
    ('실내 카페와 실내 박물관과 공원 셋 중 하나만', ['카페', '박물관', '공원']),
    ('실내 전시관과 공원 중 하나', ['전시', '공원']),
    ('실내 카페와 야외 공원 중 하나', ['카페', '공원']),
])
def test_s07_branch_conditions_are_preserved_without_a_common_fact(monkeypatch, text, kinds):
    # v4 refused this scope; v13 represents each branch without a common fact.
    result = interpret(monkeypatch, text, plan((text, kinds, [])), model_calls=0)
    assert result.status_code == 200, result.json
    stage = result.json['travel_request']['stages'][0]
    assert not stage['conditions']
    assert stage['alternatives'][0]['conditions'][0]['field'] == 'indoor'
    assert all(c['field'] != 'indoor' for c in stage['alternatives'][-1]['conditions'])


@pytest.mark.parametrize('text,kinds', [
    ('반드시 실내 카페와 반드시 실내 박물관 중 하나', ['카페', '박물관']),
    ('반드시 실내 박물관과 반드시 실내 카페 가운데 하나만', ['박물관', '카페']),
    ('실내 카페와 실내 박물관과 실내 공원 셋 중 하나', ['카페', '박물관', '공원']),
])
@pytest.mark.parametrize('conditions,expected', [([], 422),
    ([condition(required=False)], 422), ([condition(value=False)], 422), ([condition()], 200)])
def test_s07_common_required_condition_still_needs_explicit_unverified_consent(monkeypatch, text, kinds, conditions, expected):
    preview = interpret(monkeypatch, text, plan((text, kinds, conditions)))
    assert preview.status_code == 200, preview.json
    for alt in preview.json['travel_request']['stages'][0]['alternatives']:
        assert alt['conditions'][0]['value'] is True and alt['conditions'][0]['required'] is True
    catalogue(monkeypatch)
    request = {**BASE, 'user_text': text, 'intent_token': preview.json['intent_token']}
    denied = app.app.test_client().post('/recommend/spot', json=request)
    assert denied.status_code == 422 and denied.json['reason'] == 'unverified_conditions'
    accepted = app.app.test_client().post('/recommend/spot', json={**request, **consent_fields(preview)})
    assert accepted.status_code == 200, accepted.json
    assert accepted.json['metadata']['user_accepted_unverified'] is True
    assert accepted.json['places'][0]['travel_explanation']['satisfied_conditions'] == ['장소 종류']


def course_catalogue(monkeypatch):
    frame = ensure_ids(pd.DataFrame([dict(가게명=f'합성 {kind}', 카테고리=kind,
        주소=f'충남 천안시 검증로 {i+1}', 지역='천안', latitude=BASE['user_lat']+i*.0001,
        longitude=BASE['user_lng'], 방문자수=1, 블로그수=0, blog_tags='{}')
        for i, kind in enumerate(['카페', '공원', '박물관'])]))
    monkeypatch.setattr(app, 'get_df', lambda _: frame.copy())
    def unavailable(*args, **kwargs):
        raise TimeoutError()
    monkeypatch.setattr(app, '_call_claude', unavailable)


def test_s07_choice_then_visit_preserves_counts_quotes_and_the_second_visit(monkeypatch):
    text = '카페와 공원 중 하나를 고른 다음 박물관까지 두 곳을 방문하는 한 코스'
    raw = plan(('카페와 공원 중 하나', ['카페', '공원'], []), ('박물관', ['박물관'], []))
    raw['requested_visit_count'] = dict(value=2, quote='두 곳')
    raw['requested_result_count'] = dict(value=1, quote='한 코스')
    preview = interpret(monkeypatch, text, raw, mode='course')
    assert preview.status_code == 200, preview.json
    kept = preview.json['travel_request']
    assert kept['requested_visit_count'] == raw['requested_visit_count']
    assert kept['requested_result_count'] == raw['requested_result_count']
    assert [s['quote'] for s in kept['stages']] == [s['quote'] for s in raw['stages']]
    course_catalogue(monkeypatch)
    result = app.app.test_client().post('/recommend/course', json={**BASE,
        'user_text': text, 'intent_token': preview.json['intent_token']})
    assert result.status_code == 200, result.json
    assert len(result.json['courses']) == 1 and len(result.json['courses'][0]) == 2
    assert result.json['courses'][0][1]['category'] == '박물관'


@pytest.mark.parametrize('text', ['실내 카페와 야외 공원 둘 다', '실내 카페에 갔다가 야외 공원'])
def test_s07_and_and_sequential_visits_do_not_become_one_of(monkeypatch, text):
    raw = plan(('실내 카페', ['카페'], [condition()]),
               ('야외 공원', ['공원'], [condition('outdoor', quote='야외')]))
    assert interpret(monkeypatch, text, raw, mode='course').status_code == 200
    bad = copy.deepcopy(raw)
    bad['stages'][0]['conditions'] = []
    assert interpret(monkeypatch, text, bad, mode='course').status_code == 422


@pytest.mark.parametrize('text', ['실내 카페와 공원 중 하나씩', '실내 카페와 공원 셋 중 하나'])
def test_s07_distributive_or_unresolved_list_size_does_not_erase_a_required_condition(monkeypatch, text):
    raw = plan(('카페', ['카페'], []), ('공원', ['공원'], []))
    result = interpret(monkeypatch, text, raw, mode='course')
    assert result.status_code == 422
    assert result.json['metadata']['failure_code'] == 'intent_dropped_condition'


def test_s07_other_visit_choice_cannot_hide_the_first_visit_required_condition(monkeypatch):
    text = '반드시 실내 카페에 갔다가 공원과 박물관 중 하나'
    raw = plan(('카페', ['카페'], []), ('공원과 박물관 중 하나', ['공원', '박물관'], []))
    result = interpret(monkeypatch, text, raw, mode='course')
    assert result.status_code == 200, result.json
    first, second = result.json['travel_request']['stages']
    assert first['conditions'][0]['field'] == 'indoor' and first['conditions'][0]['required']
    assert all(not a['conditions'] for a in second['alternatives'])


def test_s07_manual_reordering_keeps_the_whole_or_and_its_common_condition(monkeypatch):
    text = '반드시 실내 공원과 반드시 실내 수목원 중 하나'
    raw = plan((text, ['공원', '수목원'], [condition()]))
    preview = interpret(monkeypatch, text, raw, mode='course', plan_mode='manual',
        slot_types=['음식', '자연·산책', '카페'], spot_count=3)
    assert preview.status_code == 200, preview.json
    stages = preview.json['travel_request']['stages']
    assert set(stages[1]['category_filters']) == {'공원', '수목원'}
    assert all(a['conditions'][0]['field'] == 'indoor' for a in stages[1]['alternatives'])
    assert not stages[0]['conditions'] and not stages[2]['conditions']


def test_v11_tokens_require_a_new_interpretation_even_for_safe_common_conditions(monkeypatch):
    text = '반드시 실내 카페와 반드시 실내 박물관 중 하나'
    data = app.parse_recommendation({**BASE, 'user_text': text})
    raw = plan((text, ['카페', '박물관'], [condition()]))
    validated = ti.apply_controls(ti.validate_interpretation(raw, text, app._known_categories()), data, 'spot')
    with monkeypatch.context() as previous:
        previous.setattr(ti, 'DATA_VERSION', 'places-6e51a45748c2-policy-20261102-v11')
        token = ti.sign_plan(validated, data, 'spot')
    catalogue(monkeypatch)
    request = {**BASE, 'user_text': text, 'intent_token': token}
    result = app.app.test_client().post('/recommend/spot', json=request)
    assert result.status_code == 400 and result.json['reason'] == 'intent_expired'
    accepted = app.app.test_client().post('/recommend/spot', json={**request, 'accept_unverified': True})
    assert accepted.status_code == 400 and accepted.json['reason'] == 'intent_expired'


@pytest.mark.parametrize('text', [
    '아이 동반하지 말라는 건 아니고 아이와 함께 박물관',
    '아이를 데려가지 말라는 뜻은 아니고 아이와 함께 박물관',
    '아이 동반하지 말라는 의미는 아니라서 오늘은 아이와 함께 박물관',
])
def test_i06_retracted_quoted_prohibition_with_explicit_followup_companion(monkeypatch, text):
    raw = plan(('박물관', ['박물관'], []))
    raw['companion'] = dict(value='아이와 함께', quote='아이와 함께')
    preview = interpret(monkeypatch, text, raw)
    assert preview.status_code == 200
    catalogue(monkeypatch, '박물관', '합성 어린이박물관')
    result = app.app.test_client().post('/recommend/spot', json={**BASE,
        'user_text': text, 'intent_token': preview.json['intent_token']})
    assert result.status_code == 200, result.json
    assert result.json['metadata']['family_policy']['excluded_count'] == 0
    assert len(result.json['places']) == 1


@pytest.mark.parametrize('text,allowed', [
    ('아이 동반하지 말라는 건 아니고 박물관', False),
    ('아이 동반하지 말라는 건 아니고 친구와 박물관', False),
    ('아이 동반하지 말라는 건 아니고 아이가 좋아서 박물관', False),
    ('아이 동반하지 말라는 뜻이고 아이와 함께 박물관', False),
    ('아이를 데려가지 말라는 뜻이고 아이와 함께 박물관', False),
    ('아이 동반하지 말고 아이와 함께 박물관', False),
    ('아이 동반하지 말라는 건 아니고 아이와 함께 가지 말고 박물관', False),
    ('아이 동반하지 말라는 건 아니고 아이와 함께 박물관, 아이는 동반하지 말고', False),
    ('아이를 데려가지 않는 건 아니고 아이와 함께 박물관', True),
    ('아이와 함께는 싫지 않아요', True),
])
def test_i06_retraction_is_local_and_needs_actual_positive_accompaniment(text, allowed):
    raw = dict(companion=dict(value='아이와 함께', quote='아이와 함께'),
               stages=[dict(category_filters=['박물관'])])
    frame = pd.DataFrame([dict(가게명='합성 어린이박물관', 카테고리='박물관')])
    selected, _ = filter_child_candidates(frame, dict(user_text=text, persona_tags=[]), raw)
    assert len(selected) == int(allowed)


@pytest.mark.parametrize('tags,allowed', [(['아이와 함께'], True), (['친구와'], False)])
def test_i06_manual_companion_keeps_precedence(tags, allowed):
    raw = dict(companion=dict(value='아이와 함께', quote='아이와 함께'),
               stages=[dict(category_filters=['박물관'])])
    frame = pd.DataFrame([dict(가게명='합성 어린이박물관', 카테고리='박물관')])
    selected, _ = filter_child_candidates(frame, dict(user_text=
        '아이 동반하지 말라는 건 아니고 아이와 함께 박물관', persona_tags=tags), raw)
    assert len(selected) == int(allowed)


@pytest.mark.parametrize('text,quote', [
    ('유아 없이 초등학생 박물관', '초등학생'),
    ('아이 없이 유아는 아니고 초등학생 아이와 함께 박물관', '아이와 함께'),
    ('아이 동반하지 말라는 뜻이고 아이와 함께 박물관', '아이와 함께'),
    ('아이 동반하지 말라는 건 아니고 친구와 박물관', '아이'),
])
def test_family_unsupported_or_conflicting_model_companion_is_excluded_at_http_boundary(
        monkeypatch, text, quote):
    raw = plan(('박물관', ['박물관'], []))
    raw['companion'] = dict(value='아이와 함께', quote=quote)
    preview = interpret(monkeypatch, text, raw)
    assert preview.status_code == 200
    catalogue(monkeypatch, '박물관', '합성 어린이박물관')
    result = app.app.test_client().post('/recommend/spot', json={**BASE,
        'user_text': text, 'intent_token': preview.json['intent_token']})
    assert result.status_code == 422
    assert result.json['reason'] == 'insufficient_candidates'
    assert result.json['metadata']['family_policy']['excluded_count'] == 1
