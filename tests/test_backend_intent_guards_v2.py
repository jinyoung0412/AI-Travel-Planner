"""Independent-review failures and controls for the second backend revision."""
import copy

import pandas as pd
import pytest

import app
import travel_intent as ti
from family_policy import filter_child_candidates
from place_identity import ensure_ids
from test_backend_intent_guards import BASE, condition, interpret, plan


def catalogue(monkeypatch, kind='카페', name='합성 카페'):
    frame = ensure_ids(pd.DataFrame([dict(가게명=name, 카테고리=kind,
        주소='충남 천안시 검증로 1', 지역='천안', latitude=BASE['user_lat'],
        longitude=BASE['user_lng'], 방문자수=1, 블로그수=0, blog_tags='{}')]))
    monkeypatch.setattr(app, 'get_df', lambda _: frame.copy())
    def unavailable(*args, **kwargs):
        raise TimeoutError()
    monkeypatch.setattr(app, '_call_claude', unavailable)


@pytest.mark.parametrize('text', ['반드시 실내에서 조용히 데이트',
    '실내에서 하루를 보내고 싶어', '실내에서 친구와 놀고 싶어'])
@pytest.mark.parametrize('conditions,expected', [([], 422),
    ([condition(required=False)], 422), ([condition(value=False)], 422), ([condition()], 200)])
def test_i01_clarified_activity_keeps_adverbial_required_condition(monkeypatch, text, conditions, expected):
    initial = plan()
    initial['ambiguities'] = [dict(quote=text, reason='활동 선택 필요')]
    companion = dict(value='친구와', quote='친구와') if '친구와' in text else None
    initial['companion'] = companion
    first = interpret(monkeypatch, text, initial)
    assert first.status_code == 200
    selected = plan(('카페·디저트', ['카페'], conditions))
    selected['companion'] = companion
    if '조용히' in text:
        selected['stages'][0]['preferences'] = [dict(field='quiet', quote='조용히')]
    controls = dict(activity_choice='카페', clarification_token=first.json['clarification']['token'])
    second = interpret(monkeypatch, text, selected, **controls)
    assert second.status_code == expected, second.json
    if expected == 422:
        assert second.json['metadata']['failure_code'] == 'intent_dropped_condition'
        assert 'intent_token' not in second.json
    else:
        catalogue(monkeypatch)
        request = {**BASE, **controls, 'user_text': text, 'intent_token': second.json['intent_token']}
        denied = app.app.test_client().post('/recommend/spot', json=request)
        assert denied.status_code == 422 and denied.json['reason'] == 'unverified_conditions'
        accepted = app.app.test_client().post('/recommend/spot', json={**request, 'accept_unverified': True})
        assert accepted.status_code == 200
        assert accepted.json['metadata']['user_accepted_unverified'] is True
        assert accepted.json['places'][0]['travel_explanation']['satisfied_conditions'] == ['장소 종류']


@pytest.mark.parametrize('text', [
    '반드시 실내 카페 또는 반드시 실내 박물관',
    '반드시 실내 카페 혹은 반드시 실내 박물관',
    '반드시 실내 카페나 반드시 실내 박물관',
    '반드시 실내 박물관이나 반드시 실내 카페',
])
@pytest.mark.parametrize('conditions,expected', [([], 422),
    ([condition(required=False)], 422), ([condition(value=False)], 422), ([condition()], 200)])
def test_i02_all_or_branches_share_the_same_required_condition(monkeypatch, text, conditions, expected):
    result = interpret(monkeypatch, text, plan((text, ['카페', '박물관'], conditions)))
    assert result.status_code == expected, result.json
    if expected == 422:
        assert result.json['metadata']['failure_code'] == 'intent_dropped_condition'
    else:
        catalogue(monkeypatch)
        denied = app.app.test_client().post('/recommend/spot', json={**BASE,
            'user_text': text, 'intent_token': result.json['intent_token']})
        assert denied.status_code == 422 and denied.json['reason'] == 'unverified_conditions'


@pytest.mark.parametrize('text', ['실내 카페를 선호해요', '실내 카페면 좋겠어요',
    '실내 카페도 괜찮아요', '실내 카페가 좋겠어요', '실내 카페여도 괜찮아요',
    '가능하면 실내 카페', '가급적 실내 카페', '되도록 실내 카페'])
def test_i03_explicit_preference_is_not_promoted_to_required(monkeypatch, text):
    result = interpret(monkeypatch, text, plan(('카페', ['카페'], [condition(required=False)])))
    assert result.status_code == 200, result.json
    kept = result.json['travel_request']['stages'][0]['conditions']
    assert len(kept) == 1 and kept[0]['value'] is True and kept[0]['required'] is False


@pytest.mark.parametrize('text', ['실내 카페나 공원', '실내 카페 또는 공원',
    '실내 카페 혹은 공원', '실내 박물관이나 공원', '실내 카페나 야외 공원',
    '실내 카페 또는 야외 공원', '실내카페나공원'])
def test_i04_branch_conditions_cannot_be_discarded_or_applied_to_the_whole_or(monkeypatch, text):
    kinds = ['박물관', '공원'] if '박물관' in text else ['카페', '공원']
    result = interpret(monkeypatch, text, plan((text, kinds, [])), model_calls=0)
    assert result.status_code == 422, result.json
    assert result.json['metadata']['failure_code'] == 'intent_alternative_condition_scope'
    assert 'intent_token' not in result.json


@pytest.mark.parametrize('text', ['나들이는 반드시 실내 카페',
    '혼자 나들이로 반드시 실내 카페', '야외 나들이 대신 반드시 실내 카페'])
def test_i04_syllables_inside_words_do_not_disable_required_checks(monkeypatch, text):
    result = interpret(monkeypatch, text, plan(('카페', ['카페'], [])))
    assert result.status_code == 422
    assert result.json['metadata']['failure_code'] == 'intent_dropped_condition'


@pytest.mark.parametrize('text', ['아이 동반하지 말고 박물관',
    '아이를 데려가지 말고 박물관', '아이와 가는 대신 친구와 박물관',
    '아이 동반하기 싫어서 혼자 박물관에 가고 싶어',
    '아이를 데려가는 건 싫고 박물관은 가고 싶어'])
@pytest.mark.parametrize('tags,allowed', [([], False), (['아이와 함께'], True), (['친구와'], False)])
def test_i05_direct_child_companion_negative_and_manual_priority(text, tags, allowed):
    structured = dict(companion=dict(value='아이와 함께'),
                      stages=[dict(category_filters=['박물관'])])
    frame = pd.DataFrame([dict(가게명='합성 어린이박물관', 카테고리='박물관')])
    selected, meta = filter_child_candidates(frame, dict(user_text=text, persona_tags=tags), structured)
    assert meta['child_venues_allowed'] is allowed
    assert len(selected) == int(allowed)


@pytest.mark.parametrize('text', ['아이 동반하지 말고 박물관',
    '아이를 데려가지 말고 박물관', '아이와 가는 대신 친구와 박물관'])
def test_i05_erroneous_model_companion_cannot_admit_child_museum(monkeypatch, text):
    raw = plan(('박물관', ['박물관'], []))
    raw['companion'] = dict(value='아이와 함께', quote='아이')
    preview = interpret(monkeypatch, text, raw)
    assert preview.status_code == 200
    catalogue(monkeypatch, '박물관', '합성 어린이박물관')
    response = app.app.test_client().post('/recommend/spot', json={**BASE,
        'user_text': text, 'intent_token': preview.json['intent_token']})
    assert response.status_code == 422
    assert response.json['metadata']['family_policy']['excluded_count'] == 1


@pytest.mark.parametrize('text', ['카페 말고 아이와 박물관',
    '아이와 가는 카페 말고 박물관', '아이와 함께는 싫지 않아요',
    '아이 동반하기는 싫지 않아요', '아이를 데려가지 않는 건 아니에요'])
def test_i05_unrelated_venue_negative_and_double_negative_are_not_companion_bans(text):
    structured = dict(companion=dict(value='아이와 함께'), stages=[dict(category_filters=['박물관'])])
    frame = pd.DataFrame([dict(가게명='합성 어린이박물관', 카테고리='박물관')])
    selected, _ = filter_child_candidates(frame, dict(user_text=text, persona_tags=[]), structured)
    assert len(selected) == 1


def test_or_on_another_visit_does_not_hide_the_first_required_condition(monkeypatch):
    text = '반드시 실내 카페에 들른 뒤 공원 또는 박물관'
    raw = plan(('카페', ['카페'], []), ('공원 또는 박물관', ['공원', '박물관'], []))
    assert interpret(monkeypatch, text, raw, mode='course').status_code == 422
    raw['stages'][0]['conditions'] = [condition()]
    assert interpret(monkeypatch, text, raw, mode='course').status_code == 200


def test_each_or_group_keeps_its_own_common_condition(monkeypatch):
    text = '실내 카페 또는 실내 박물관 다음 야외 공원'
    raw = plan(('카페 또는 실내 박물관', ['카페', '박물관'], [condition()]),
               ('공원', ['공원'], [condition('outdoor', quote='야외')]))
    assert interpret(monkeypatch, text, raw, mode='course').status_code == 200
    bad = copy.deepcopy(raw)
    bad['stages'][0]['conditions'] = []
    assert interpret(monkeypatch, text, bad, mode='course').status_code == 422


def test_longer_first_quote_does_not_reassign_the_next_visit_to_its_substring(monkeypatch):
    text = '실내 카페 다음 야외 카페'
    raw = plan(('실내 카페', ['카페'], [condition()]),
               ('카페', ['카페'], [condition('outdoor', quote='야외')]))
    assert interpret(monkeypatch, text, raw, mode='course').status_code == 200
    raw['stages'][1]['conditions'] = []
    assert interpret(monkeypatch, text, raw, mode='course').status_code == 422


@pytest.mark.parametrize('text,conditions,expected', [
    ('가능하면 실내에서 친구와 놀고 싶어', [condition(required=False)], 200),
    ('실내에서 친구와 놀면 좋겠어요', [condition(required=False)], 200),
    ('실내에서 놀지 않고 야외에서 데이트', [condition(value=False),
        condition('outdoor', quote='야외')], 200),
    ('실내 데이트 또는 야외 나들이', [], 200),
    ('실내에서 아이를 데려가지 말고 데이트', [], 422),
])
def test_i01_context_scope_does_not_turn_optional_or_negated_outings_into_hard_facts(
        monkeypatch, text, conditions, expected):
    initial = plan()
    initial['ambiguities'] = [dict(quote=text, reason='활동 선택 필요')]
    first = interpret(monkeypatch, text, initial)
    assert first.status_code == 200
    selected = plan(('카페·디저트', ['카페'], conditions))
    result = interpret(monkeypatch, text, selected, activity_choice='카페',
        clarification_token=first.json['clarification']['token'])
    assert result.status_code == expected, result.json


@pytest.mark.parametrize('purpose', ['recommendation', 'activity_clarification'])
def test_previous_condition_policy_tokens_cannot_skip_the_new_validation(monkeypatch, purpose):
    # A previous server could sign these incomplete interpretations. Keeping a
    # shared key across deployment must not preserve that old policy approval.
    previous = 'places-6e51a45748c2-policy-20261029-v10'
    assert ti.DATA_VERSION != previous
    monkeypatch.setenv('TRAVEL_INTENT_SIGNING_KEY', 'cd' * 32)  # Synthetic fixture.
    text = '반드시 실내 카페' if purpose == 'recommendation' else '반드시 실내에서 하루를 보내고 싶어'
    data = app.parse_recommendation({**BASE, 'user_text': text})
    raw = plan(('카페', ['카페'], [])) if purpose == 'recommendation' else plan()
    if purpose == 'activity_clarification':
        raw['ambiguities'] = [dict(quote=text, reason='활동 선택 필요')]
    with monkeypatch.context() as old:
        old.setattr(ti, 'DATA_VERSION', previous)
        token = ti.sign_plan(raw, data, 'spot', purpose=purpose)
    client = app.app.test_client()
    if purpose == 'recommendation':
        response = client.post('/recommend/spot', json={**BASE, 'user_text': text, 'intent_token': token})
    else:
        response = client.post('/travel/interpret', json={**BASE, 'user_text': text,
            'mode': 'spot', 'activity_choice': '카페', 'clarification_token': token})
    assert response.status_code == 400
    assert response.json['reason'] == 'intent_expired'


@pytest.mark.parametrize('text,keep_companion,expected_code', [
    ('반드시 실내에서 조용히 데이트', True, 'intent_dropped_preference'),
    ('조용히 말고 반드시 실내 데이트', True, None),
    ('반드시 실내에서 친구와 놀고 싶어', False, 'intent_dropped_companion'),
])
def test_i01_selected_activity_preserves_positive_mood_and_companion(
        monkeypatch, text, keep_companion, expected_code):
    initial = plan()
    initial['ambiguities'] = [dict(quote=text, reason='활동 선택 필요')]
    if '친구와' in text:
        initial['companion'] = dict(value='친구와', quote='친구와')
    first = interpret(monkeypatch, text, initial)
    assert first.status_code == 200
    selected = plan(('카페·디저트', ['카페'], [condition()]))
    if keep_companion:
        selected['companion'] = initial['companion']
    result = interpret(monkeypatch, text, selected, activity_choice='카페',
        clarification_token=first.json['clarification']['token'])
    assert result.status_code == (422 if expected_code else 200), result.json
    if expected_code:
        assert result.json['metadata']['failure_code'] == expected_code
