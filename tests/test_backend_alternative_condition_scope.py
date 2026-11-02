"""P05: refuse unsupported branch requirements without erasing or spreading them."""
import copy

import pytest

import app
import travel_intent as ti
from test_backend_intent_guards import BASE, condition, interpret, plan
from test_backend_intent_guards_v2 import catalogue


P05 = '실내 카페와 공원 중 하나 가고 싶어'
CODE = 'intent_alternative_condition_scope'


def assert_scope_error(response):
    assert response.status_code == 422, response.json
    assert response.json['reason'] == 'intent_conflict'
    assert response.json['metadata']['failure_code'] == CODE
    assert '선택지마다 필수 조건' in response.json['error']
    assert '활동 하나를 골라' in response.json['error']
    assert '그 활동의 조건과 함께' in response.json['error']
    assert 'intent_token' not in response.json
    assert not response.json.get('places')
    assert not response.json.get('courses')


@pytest.mark.parametrize('text', [
    P05, '실내 카페 또는 공원', '카페 또는 실내 박물관',
    '실내카페나공원', '실내 카페와 야외 공원 중 하나',
    '지금 영업 중인 카페와 공원 중 하나',
    '야외 좌석이 있는 카페 또는 공원',
    '휠체어 접근이 가능한 박물관과 공원 중 하나',
    '반드시 실내 카페 또는 가능하면 실내 박물관',
    '카페와 공원과 실내 박물관 셋 중 하나',
])
def test_clear_asymmetric_required_choices_fail_before_the_model(monkeypatch, text):
    # The response would be malformed; source-only rejection must precede it.
    response = interpret(monkeypatch, text, {}, model_calls=0, count=3)
    assert_scope_error(response)


@pytest.mark.parametrize('raw', [
    plan((P05, ['카페', '공원'], [])),
    plan(('공원', ['공원'], [])),
    plan(('실내 카페', ['카페'], [condition()]), ('공원', ['공원'], [])),
])
def test_p05_does_not_need_a_good_model_response_to_give_specific_guidance(monkeypatch, raw):
    assert_scope_error(interpret(monkeypatch, P05, raw, model_calls=0))


@pytest.mark.parametrize('token_policy', [None, 'v11', 'v12'])
@pytest.mark.parametrize('accept', [False, True])
def test_indoor_unverified_cafe_http_path_cannot_bypass_scope_with_tokens_or_consent(
        monkeypatch, token_policy, accept):
    # Before v4 this exact cafe-only catalogue + common-only OR plan returned
    # 200 without consent. Never treat a cafe category as evidence of indoor.
    catalogue(monkeypatch, '카페', '합성 실내 여부 미확인 카페')
    def forbidden(*args, **kwargs):
        pytest.fail('Unsupported branch request must reach neither model nor catalogue')
    monkeypatch.setattr(app, '_call_claude', forbidden)
    monkeypatch.setattr(app, 'get_df', forbidden)
    request = {**BASE, 'user_text': P05, 'accept_unverified': accept}
    if token_policy:
        data = app.parse_recommendation(request)
        raw = plan((P05, ['카페', '공원'], []))
        validated = ti.apply_controls(ti.validate_interpretation(
            copy.deepcopy(raw), P05, app._known_categories()), data, 'spot')
        with monkeypatch.context() as policy:
            policy.setattr(ti, 'DATA_VERSION', f'places-6e51a45748c2-policy-20261102-{token_policy}')
            request['intent_token'] = ti.sign_plan(validated, data, 'spot')
    response = app.app.test_client().post('/recommend/spot', json=request)
    if token_policy == 'v11' or (accept and not token_policy):
        assert response.status_code == 400
        assert response.json['reason'] == 'intent_expired'
    else:
        assert_scope_error(response)


@pytest.mark.parametrize('text,kinds', [
    ('카페와 공원 중 하나 가고 싶어', ['카페', '공원']),
    ('카페 또는 공원', ['카페', '공원']),
    ('카페와 박물관과 공원 셋 중 하나', ['카페', '박물관', '공원']),
    ('가능하면 실내 카페 또는 공원', ['카페', '공원']),
    ('실내 카페를 선호해요 또는 공원', ['카페', '공원']),
    ('실내가 아닌 카페 또는 공원', ['카페', '공원']),
    ('실내 카페와 공원 중 하나는 싫지 않아요', ['카페', '공원']),
    ('실내 박물관 근처 카페 또는 공원', ['카페', '공원']),
])
def test_plain_soft_negative_and_landmark_choices_are_not_blanket_rejected(monkeypatch, text, kinds):
    response = interpret(monkeypatch, text, plan((text, kinds, [])))
    assert response.status_code == 200, response.json
    assert response.json['mode_switch_required'] is False


def test_unconditioned_or_reaches_a_cafe_without_manufacturing_an_indoor_requirement(monkeypatch):
    text = '카페와 공원 중 하나 가고 싶어'
    preview = interpret(monkeypatch, text, plan((text, ['카페', '공원'], [])))
    assert preview.status_code == 200
    catalogue(monkeypatch)
    response = app.app.test_client().post('/recommend/spot', json={
        **BASE, 'user_text': text, 'intent_token': preview.json['intent_token']})
    assert response.status_code == 200, response.json
    assert response.json['metadata']['unverified_conditions'] == []


def test_unconditioned_choice_does_not_lose_the_kind_omission_guard(monkeypatch):
    text = '카페와 공원 중 하나'
    response = interpret(monkeypatch, text, plan(('공원', ['공원'], [])))
    assert response.status_code == 422
    assert response.json['metadata']['failure_code'] == 'intent_dropped_kind'


@pytest.mark.parametrize('tags', [[], ['친구와', '조용한']])
def test_general_manual_tags_do_not_block_an_unconditioned_choice(monkeypatch, tags):
    text = '카페와 공원 중 하나'
    response = interpret(monkeypatch, text, plan((text, ['카페', '공원'], [])), persona_tags=tags)
    assert response.status_code == 200, response.json
    assert not response.json['travel_request']['stages'][0]['conditions']


def test_explicit_child_companion_does_not_block_an_unconditioned_choice(monkeypatch):
    text = '아이와 함께 카페와 공원 중 하나'
    raw = plan(('카페와 공원 중 하나', ['카페', '공원'], []))
    raw['companion'] = dict(value='아이와 함께', quote='아이와 함께')
    response = interpret(monkeypatch, text, raw)
    assert response.status_code == 200, response.json
    assert response.json['travel_request']['companion']['value'] == '아이와 함께'


@pytest.mark.parametrize('text,kinds', [
    ('반드시 실내 카페', ['카페']),
    ('반드시 실내 카페와 반드시 실내 박물관 중 하나', ['카페', '박물관']),
])
def test_supported_individual_and_common_v12_conditions_still_need_consent(monkeypatch, text, kinds):
    assert ti.DATA_VERSION.endswith('-v12')
    preview = interpret(monkeypatch, text, plan((text, kinds, [condition()])))
    assert preview.status_code == 200, preview.json
    catalogue(monkeypatch)
    request = {**BASE, 'user_text': text, 'intent_token': preview.json['intent_token']}
    client = app.app.test_client()
    denied = client.post('/recommend/spot', json=request)
    assert denied.status_code == 422 and denied.json['reason'] == 'unverified_conditions'
    accepted = client.post('/recommend/spot', json={**request, 'accept_unverified': True})
    assert accepted.status_code == 200, accepted.json
    assert accepted.json['metadata']['user_accepted_unverified'] is True
    assert accepted.json['places'][0]['travel_explanation']['satisfied_conditions'] == ['장소 종류']


@pytest.mark.parametrize('purpose', ['recommendation', 'activity_clarification'])
def test_v11_recommendation_and_clarification_tokens_are_retired(monkeypatch, purpose):
    text = '실내에서 하루를 보내고 싶어'
    data = app.parse_recommendation({**BASE, 'user_text': text})
    raw = plan()
    raw['ambiguities'] = [dict(quote=text, reason='활동 선택 필요')]
    with monkeypatch.context() as previous:
        previous.setattr(ti, 'DATA_VERSION', 'places-6e51a45748c2-policy-20261102-v11')
        token = ti.sign_plan(raw, data, 'spot', purpose=purpose)
    def forbidden(*args, **kwargs):
        pytest.fail('An old token must be rejected without a model call')
    monkeypatch.setattr(app, '_call_claude', forbidden)
    client = app.app.test_client()
    if purpose == 'recommendation':
        response = client.post('/recommend/spot', json={
            **BASE, 'user_text': text, 'intent_token': token})
    else:
        response = client.post('/travel/interpret', json={**BASE, 'user_text': text,
            'mode': 'spot', 'clarification_token': token, 'activity_choice': '카페'})
    assert response.status_code == 400
    assert response.json['reason'] == 'intent_expired'


@pytest.mark.parametrize('change', ['fingerprint', 'tamper', 'purpose', 'ttl'])
def test_new_v12_tokens_keep_the_other_integrity_checks(monkeypatch, change):
    data = app.parse_recommendation({**BASE, 'user_text': '카페'})
    raw = plan(('카페', ['카페'], []))
    token = ti.sign_plan(raw, data, 'spot')
    purpose = 'recommendation'
    if change == 'fingerprint':
        data = {**data, 'count': 2}
    elif change == 'tamper':
        token = ('A' if token[0] != 'A' else 'B') + token[1:]
    elif change == 'purpose':
        purpose = 'activity_clarification'
    else:
        now = ti.time.time()
        monkeypatch.setattr(ti.time, 'time', lambda: now + ti.TOKEN_TTL + 1)
    with pytest.raises(ti.IntentError) as error:
        ti.read_plan(token, data, 'spot', purpose=purpose)
    assert error.value.reason == 'intent_expired'
