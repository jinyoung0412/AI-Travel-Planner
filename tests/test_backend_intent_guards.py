"""Source preservation and worker contracts, using synthetic data and no APIs."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

import app
import travel_intent as ti
from family_policy import filter_child_candidates
from place_identity import ensure_ids


BASE = dict(region='천안', transport='대중교통', user_lat=36.8066, user_lng=127.1469,
            count=1, persona_tags=[], intent_version=1, plan_mode='natural')


def condition(field='indoor', *, required=True, value=True, quote='실내'):
    return dict(field=field, required=required, value=value, quote=quote)


def plan(*visits):
    return dict(schema_version=1, companion=None,
        stages=[dict(id=f's{i+1}', activity=quote, quote=quote, category_filters=cats,
                     conditions=conditions, preferences=[])
                for i, (quote, cats, conditions) in enumerate(visits)],
        exclusions=[], ambiguities=[], unsupported=[], requested_visit_count=None,
        requested_result_count=None)


def interpret(monkeypatch, text, raw, **controls):
    calls = []
    def model(*args, **kwargs):
        calls.append(kwargs)
        return copy.deepcopy(raw)
    monkeypatch.setattr(app, '_call_claude', model)
    response = app.app.test_client().post('/travel/interpret', json={**BASE,
        'user_text': text, 'mode': 'spot', **controls})
    assert len(calls) == 1  # Source rejection never retries the provider.
    return response


@pytest.mark.parametrize('conditions', [[], [condition(required=False)], [condition(value=False)]])
def test_mandatory_indoor_cannot_disappear_weaken_or_reverse(monkeypatch, conditions):
    response = interpret(monkeypatch, '반드시 실내 카페', plan(('카페', ['카페'], conditions)))
    assert response.status_code == 422
    assert response.json['reason'] == 'intent_conflict'
    assert response.json['metadata']['failure_code'] == 'intent_dropped_condition'
    assert 'intent_token' not in response.json


@pytest.mark.parametrize('text,field,quote', [
    ('실내 카페', 'indoor', '실내'), ('반드시 야외 공원', 'outdoor', '야외'),
    ('꼭 야외 좌석이 있는 카페', 'outdoor_seating', '야외 좌석'),
    ('지금 영업 중인 카페', 'open_now', '지금 영업 중인'),
    ('휠체어 접근이 가능한 카페', 'accessible', '휠체어 접근이 가능한'),
])
def test_other_clear_positive_modifiers_remain_unverified(monkeypatch, text, field, quote):
    kind = '공원' if '공원' in text else '카페'
    bad = interpret(monkeypatch, text, plan((kind, [kind], [])))
    assert bad.status_code == 422
    good = interpret(monkeypatch, text, plan((kind, [kind], [condition(field, quote=quote)])))
    assert good.status_code == 200
    frame = ensure_ids(pd.DataFrame([dict(가게명='합성 장소', 주소='충남 천안시 검증로 1',
        지역='천안', 카테고리=kind, latitude=BASE['user_lat'], longitude=BASE['user_lng'],
        방문자수=1, 블로그수=0, blog_tags='{}')]))
    monkeypatch.setattr(app, 'get_df', lambda _: frame.copy())
    def unavailable(*a, **kw):
        raise TimeoutError()
    monkeypatch.setattr(app, '_call_claude', unavailable)
    request = {**BASE, 'user_text': text, 'intent_token': good.json['intent_token']}
    client = app.app.test_client()
    denied = client.post('/recommend/spot', json=request)
    assert denied.status_code == 422 and denied.json['reason'] == 'unverified_conditions'
    accepted = client.post('/recommend/spot', json={**request, 'accept_unverified': True})
    assert accepted.status_code == 200
    assert accepted.json['metadata']['user_accepted_unverified'] is True
    explanation = accepted.json['places'][0]['travel_explanation']
    assert explanation['satisfied_conditions'] == ['장소 종류']
    assert explanation['unverified_conditions']


@pytest.mark.parametrize('text,cats,conditions', [
    ('가능하면 실내 카페', ['카페'], [condition(required=False)]),
    ('가급적 야외 공원', ['공원'], [condition('outdoor', required=False, quote='야외')]),
    ('실내가 아닌 카페', ['카페'], [condition(value=False, quote='실내가 아닌')]),
    ('실내 말고 카페', ['카페'], []),
    ('실내 카페는 싫지 않아요', ['카페'], []),
    ('실내 카페 말고는 안 가요', ['카페'], []),
    ('실내 카페가 아닌 곳은 싫어요', ['카페'], []),
    ('실내 카페도 좋아요', ['카페'], []),
    ('실내 카페 또는 공원', ['카페', '공원'], []),
    ('카페 또는 실내 박물관', ['카페', '박물관'], []),
    ('실내 놀거리', ['볼링'], []), ('실내놀이터', ['실내놀이터'], []),
    ('실내 박물관 근처 카페', ['카페'], []),
])
def test_preference_negation_kind_and_landmark_do_not_invent_hard_fact(monkeypatch, text, cats, conditions):
    quote = text if '놀' in text else ('공원' if cats == ['공원'] else '카페')
    response = interpret(monkeypatch, text, plan((quote, cats, conditions)))
    assert response.status_code == 200, response.json
    if '가능하면' in text or '가급적' in text:
        assert all(not c['required'] for c in response.json['travel_request']['stages'][0]['conditions'])


@pytest.mark.parametrize('swap', [False, True])
def test_each_required_condition_must_stay_on_its_own_visit(monkeypatch, swap):
    indoor = condition()
    outdoor = condition('outdoor', quote='야외')
    good = plan(('카페', ['카페'], [indoor]), ('공원', ['공원'], [outdoor]))
    bad = copy.deepcopy(good)
    if swap:
        bad['stages'][0]['conditions'], bad['stages'][1]['conditions'] = [outdoor], [indoor]
    else:
        bad['stages'][0]['conditions'] = []
        bad['stages'][1]['conditions'] = [indoor, outdoor]
    text = '반드시 실내 카페 다음 야외 공원'
    assert interpret(monkeypatch, text, bad, mode='course').status_code == 422
    assert interpret(monkeypatch, text, good, mode='course').status_code == 200


def test_separate_soft_clause_does_not_weaken_next_required_visit(monkeypatch):
    text = '가능하면 실내 카페 다음 반드시 야외 공원'
    raw = plan(('카페', ['카페'], [condition(required=False)]),
               ('공원', ['공원'], [condition('outdoor', quote='야외', required=False)]))
    assert interpret(monkeypatch, text, raw, mode='course').status_code == 422
    raw['stages'][1]['conditions'][0]['required'] = True
    assert interpret(monkeypatch, text, raw, mode='course').status_code == 200


def test_same_kind_visits_keep_separate_conditions_and_manual_rebinding(monkeypatch):
    raw = plan(('카페', ['카페'], [condition()]),
               ('카페', ['카페'], [condition('outdoor', quote='야외')]))
    text = '실내 카페 다음 야외 카페'
    assert interpret(monkeypatch, text, raw, mode='course').status_code == 200
    raw['stages'][1]['conditions'] = []
    assert interpret(monkeypatch, text, raw, mode='course').status_code == 422
    raw = plan(('카페', ['카페'], [condition()]))
    manual = interpret(monkeypatch, '반드시 실내 카페', raw, mode='course',
        plan_mode='manual', slot_types=['음식', '카페', '자연·산책'], spot_count=3)
    assert manual.status_code == 200
    stages = manual.json['travel_request']['stages']
    assert not stages[0]['conditions'] and stages[1]['conditions'][0]['required']
    assert not stages[2]['conditions']


@pytest.mark.parametrize('text', ['반드시 실내 데이트', '실내에서 데이트', '꼭 실내에서 놀고 싶어'])
@pytest.mark.parametrize('conditions,expected', [([], 422), ([condition(required=False)], 422),
                                               ([condition()], 200)])
def test_activity_clarification_preserves_original_required_condition(monkeypatch, text, conditions, expected):
    raw = plan()
    raw['ambiguities'] = [dict(quote=text, reason='활동 선택 필요')]
    initial = interpret(monkeypatch, text, raw)
    assert initial.status_code == 200
    selected = plan(('카페·디저트', ['카페'], conditions))
    response = interpret(monkeypatch, text, selected, activity_choice='카페',
        clarification_token=initial.json['clarification']['token'])
    assert response.status_code == expected, response.json


@pytest.mark.parametrize('text,tags,companion,expected', [
    ('카페 말고 아이와 함께 박물관', [], '아이와 함께', True),
    ('아이와 함께 카페 말고 박물관', [], '아이와 함께', True),
    ('야외는 싫고 유아 동반 박물관', [], '유아/영아 동반', True),
    ('아이 없이 박물관', [], '아이와 함께', False),
    ('아이와 함께 가고 싶지 않아요', [], '아이와 함께', False),
    ('아이 동반 안 할래요', [], '아이와 함께', False),
    ('아이 동반은 안 할래요', [], '아이와 함께', False),
    ('아이 동반은 싫어요', [], '아이와 함께', False),
    ('아이를 안 데려갈래요', [], '아이와 함께', False),
    ('아이를 데리고 가지 않을래요', [], '아이와 함께', False),
    ('아이 안 데리고 가요', [], '아이와 함께', False),
    ('아이 없이 안 가요', [], '아이와 함께', True),
    ('아이와 함께는 싫지 않아요', [], '아이와 함께', True),
    ('아이와 함께 가지 않는 건 아니에요', [], '아이와 함께', True),
    ('아이 동반하지 않을 수는 없어요', [], '아이와 함께', True),
    ('아이 없이 박물관', ['아이와 함께'], '아이와 함께', True),
    ('아이와 함께 박물관', ['친구와'], '아이와 함께', False),
    ('박물관', [], None, False),
    # Legacy stays conservative even though structured interpretation improves.
    ('카페 말고 아이와 함께 박물관', [], 'legacy', False),
])
def test_child_companion_scope_and_manual_priority(text, tags, companion, expected):
    structured = (None if companion == 'legacy' else dict(
        companion=dict(value=companion) if companion else None,
        stages=[dict(category_filters=['박물관'])]))
    frame = pd.DataFrame([dict(가게명='합성 어린이박물관', 카테고리='박물관')])
    result, meta = filter_child_candidates(frame, dict(user_text=text, persona_tags=tags), structured)
    assert meta['child_venues_allowed'] is expected
    assert len(result) == int(expected)


def test_unrelated_exclusion_child_museum_reaches_final_recommendation(monkeypatch):
    text = '카페 말고 아이와 함께 박물관'
    raw = plan(('박물관', ['박물관'], []))
    raw['companion'] = dict(value='아이와 함께', quote='아이와 함께')
    raw['exclusions'] = [dict(category_filters=['카페'], quote='카페 말고')]
    preview = interpret(monkeypatch, text, raw)
    assert preview.status_code == 200
    catalogue = ensure_ids(pd.DataFrame([dict(가게명='합성 어린이박물관',
        주소='충남 천안시 검증로 1', 지역='천안', 카테고리='박물관',
        latitude=BASE['user_lat'], longitude=BASE['user_lng'], 방문자수=1, 블로그수=0,
        blog_tags='{}')]))
    monkeypatch.setattr(app, 'get_df', lambda _: catalogue.copy())
    def unavailable(*a, **kw):
        raise TimeoutError()
    monkeypatch.setattr(app, '_call_claude', unavailable)
    response = app.app.test_client().post('/recommend/spot', json={**BASE,
        'user_text': text, 'intent_token': preview.json['intent_token']})
    assert response.status_code == 200
    assert response.json['metadata']['family_policy']['excluded_count'] == 0
    assert response.json['places'][0]['source_name'] == '합성 어린이박물관'


WORKER = '''
import json,sys,os
from pathlib import Path
r=Path.cwd();sys.path[:0]=[str(r),str(r/'Flask_server')]
from scripts.offline_environment import install
install()
import travel_intent as t
v=json.loads(sys.stdin.read())
if v.get('key') is not None:os.environ['TRAVEL_INTENT_SIGNING_KEY']=v['key']
if v.get('dotenv'):
 import dotenv
 def fake_load(*a,**k):os.environ['TRAVEL_INTENT_SIGNING_KEY']=v['dotenv']
 dotenv.load_dotenv=fake_load
try:
 if v.get('dotenv'):import app
 if v['op']=='sign':result={'token':t.sign_plan({'synthetic':True},v['data'],'spot')}
 else:result={'accepted':t.read_plan(v['token'],v['data'],'spot')=={'synthetic':True}}
except t.IntentError as e:result={'reason':e.reason,'status':e.status}
except ValueError as e:result={'configuration_error':str(e)}
print(json.dumps(result))
'''


def worker(**value):
    result = subprocess.run([sys.executable, '-B', '-c', WORKER],
        input=json.dumps(value), capture_output=True, text=True, check=True,
        cwd=Path(__file__).resolve().parents[1])
    return json.loads(result.stdout)


def test_independent_workers_share_configured_key_and_reject_other_key():
    key = '01' * 32  # Deterministic synthetic test value, never a real key.
    data = dict(BASE, user_text='카페')
    token = worker(op='sign', key=key, data=data)['token']
    assert worker(op='read', key=key, data=data, token=token) == {'accepted': True}
    assert worker(op='read', key='02'*32, data=data, token=token)['reason'] == 'intent_expired'
    assert worker(op='read', data=data, token=token)['reason'] == 'intent_expired'


def test_dotenv_configuration_is_used_after_early_intent_import():
    key = '03' * 32
    data = dict(BASE, user_text='카페')
    token = worker(op='sign', dotenv=key, data=data)['token']
    assert worker(op='read', key=key, data=data, token=token) == {'accepted': True}
    invalid = worker(op='sign', dotenv='invalid-synthetic-value', data=data)
    assert invalid == {'configuration_error': 'Invalid TRAVEL_INTENT_SIGNING_KEY configuration.'}


@pytest.mark.parametrize('bad', ['too-short', 'g'*64, ' '+('01'*32), '01'*33])
def test_invalid_config_fails_without_disclosing_value(monkeypatch, bad):
    monkeypatch.setenv('TRAVEL_INTENT_SIGNING_KEY', bad)
    with pytest.raises(ValueError, match='^Invalid TRAVEL_INTENT_SIGNING_KEY configuration\\.$') as exc:
        ti.sign_plan({}, BASE, 'spot')
    assert bad not in str(exc.value)


@pytest.mark.parametrize('change', ['fingerprint', 'data_version', 'purpose', 'ttl', 'tamper', 'rotation', 'removal'])
def test_configured_signatures_keep_all_token_guards(monkeypatch, change):
    monkeypatch.setenv('TRAVEL_INTENT_SIGNING_KEY', '04'*32)
    monkeypatch.setattr(ti.time, 'time', lambda: 1000)
    data = dict(BASE, user_text='카페')
    token = ti.sign_plan({'synthetic': True}, data, 'spot')
    purpose = 'recommendation'
    assert ti.read_plan(token, data, 'spot') == {'synthetic': True}
    if change == 'fingerprint':data = {**data, 'count': 2}
    elif change == 'data_version':monkeypatch.setattr(ti, 'DATA_VERSION', 'changed')
    elif change == 'purpose':purpose = 'activity_clarification'
    elif change == 'ttl':monkeypatch.setattr(ti.time, 'time', lambda: 1000 + ti.TOKEN_TTL + 1)
    elif change == 'tamper':token = ('A' if token[0] != 'A' else 'B') + token[1:]
    elif change == 'rotation':monkeypatch.setenv('TRAVEL_INTENT_SIGNING_KEY', '05'*32)
    elif change == 'removal':monkeypatch.delenv('TRAVEL_INTENT_SIGNING_KEY')
    with pytest.raises(ti.IntentError) as exc:
        ti.read_plan(token, data, 'spot', purpose=purpose)
    assert (exc.value.reason, exc.value.status) == ('intent_expired', 400)


def test_unconfigured_single_process_development_still_works(monkeypatch):
    monkeypatch.delenv('TRAVEL_INTENT_SIGNING_KEY', raising=False)
    token = ti.sign_plan({'synthetic': True}, BASE, 'spot')
    assert ti.read_plan(token, BASE, 'spot') == {'synthetic': True}


def _fork_read(connection, token, data):
    connection.send(ti.read_plan(token, data, 'spot') == {'synthetic': True})
    connection.close()


def test_preloaded_fork_inherits_the_development_key(monkeypatch):
    import multiprocessing
    if 'fork' not in multiprocessing.get_all_start_methods():
        pytest.skip('preloaded fork is not available on this platform')
    monkeypatch.delenv('TRAVEL_INTENT_SIGNING_KEY', raising=False)
    token = ti.sign_plan({'synthetic': True}, BASE, 'spot')
    parent, child = multiprocessing.get_context('fork').Pipe()
    process = multiprocessing.get_context('fork').Process(target=_fork_read, args=(child, token, BASE))
    process.start()
    try:
        assert parent.poll(3) and parent.recv() is True
        process.join(3)
        assert process.exitcode == 0
    finally:
        parent.close()
        child.close()
        if process.is_alive():
            process.terminate()
            process.join(3)


def test_fresh_unconfigured_workers_still_need_a_shared_setting():
    token = worker(op='sign', data=BASE)['token']
    assert worker(op='read', data=BASE, token=token)['reason'] == 'intent_expired'
