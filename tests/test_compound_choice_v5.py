"""Closed choice grammar, scoped grants and every candidate admission boundary."""
import copy
import json
from pathlib import Path

import pandas as pd
import pytest

import app
import compound_choice as cc
import travel_intent as ti
from place_identity import ensure_ids
from test_backend_intent_guards import BASE, plan


@pytest.fixture
def setup(monkeypatch):
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(1)
        raise TimeoutError()
    monkeypatch.setattr(app, '_call_claude', unavailable)
    def catalogue(kinds):
        frame = ensure_ids(pd.DataFrame([dict(가게명=f'합성 {kind}{i}', 카테고리=kind,
            주소=f'충남 천안시 검증로 {i}', 지역='천안', latitude=BASE['user_lat']+i*.00001,
            longitude=BASE['user_lng'], 방문자수=1, 블로그수=0, blog_tags='{}')
            for i, kind in enumerate(kinds)]))
        monkeypatch.setattr(app, 'get_df', lambda _: frame.copy())
    catalogue(['카페', '공원', '박물관'])
    return app.app.test_client(), calls, catalogue


def preview(client, text, **controls):
    response = client.post('/travel/interpret', json={**BASE, 'count':3,
        'user_text':text, 'mode':'spot', **controls})
    assert response.status_code == 200, response.json
    return response.json


def recommend(client, text, reviewed, **controls):
    return client.post('/recommend/spot', json={**BASE, 'count':3, 'user_text':text,
        'intent_token':reviewed['intent_token'], **controls})


def grant(reviewed, alternative=0):
    stage = reviewed['travel_request']['stages'][0]
    return dict(accept_unverified=True, consent_plan_id=reviewed['travel_request']['plan_id'],
        accepted_condition_ids=[c['id'] for c in stage['conditions'] +
                                stage['alternatives'][alternative]['conditions'] if c['required']])


@pytest.mark.parametrize('text', ['카페나 공원 중 하나 가고 싶어', '카페와 공원 중 하나',
    '카페 또는 공원', '실내 카페 또는 공원', '실내가 아닌 카페 또는 공원',
    '가능하면 실내 카페 또는 공원', '아이와 함께 카페와 공원 중 하나'])
@pytest.mark.parametrize('raw', [None, {}, plan(('공원',['공원'],[])),
    plan(('카페',['카페'],[]), ('공원',['공원'],[]))])
def test_proven_source_is_one_visit_regardless_of_model_response(setup, monkeypatch, text, raw):
    client, calls, _ = setup
    monkeypatch.setattr(app, '_call_claude', lambda *a, **k: calls.append(raw) or copy.deepcopy(raw))
    result = preview(client, text)
    assert not calls
    assert result['target_mode']=='spot' and result['target_count']==3
    assert result['mode_switch_required'] is False
    assert len(result['travel_request']['stages'])==1
    assert len(result['travel_request']['stages'][0]['alternatives'])==2


def test_park_default_and_explicit_cafe_consent_keep_correct_attribution(setup):
    client, calls, _ = setup; text='실내 카페 또는 공원'
    reviewed=preview(client,text)
    result=recommend(client,text,reviewed);assert result.status_code==200,result.json
    assert [p['category'] for p in result.json['places']]==['공원']
    explanation=result.json['places'][0]['travel_explanation']
    assert explanation['alternative_id']=='s1.a2' and not explanation['conditions']
    assert not result.json['metadata']['user_accepted_unverified']
    assert result.json['metadata']['consent_offer']['alternatives'][0]['conditions'][0]['field']=='indoor'
    accepted=recommend(client,text,reviewed,**grant(reviewed));assert accepted.status_code==200,accepted.json
    cafe=next(p for p in accepted.json['places'] if p['category']=='카페')
    condition=cafe['travel_explanation']['conditions'][0]
    assert condition['value'] is True and condition['status']=='unknown' and condition['accepted_as_unknown']
    assert cafe['travel_explanation']['satisfied_conditions']==['장소 종류']
    assert 'intent_token' not in json.dumps(cafe) and 'plan_id' not in json.dumps(cafe)


@pytest.mark.parametrize('text', ['실내 카페 또는 야외 공원', '실내가 아닌 카페 또는 야외 공원',
    '반드시 실내 카페 또는 반드시 실내 박물관'])
def test_partial_consent_is_not_another_alternative_grant(setup,text):
    client,calls,_=setup;reviewed=preview(client,text)
    denied=recommend(client,text,reviewed);assert denied.status_code==422,denied.json
    assert denied.json['reason']=='unverified_conditions' and not calls
    accepted=recommend(client,text,reviewed,**grant(reviewed))
    assert accepted.status_code==200,accepted.json
    assert {p['category'] for p in accepted.json['places']}=={'카페'}
    assert accepted.json['metadata']['withheld_alternatives'][0]['alternative_id']=='s1.a2'


def test_all_unknown_atoms_of_one_branch_need_consent(setup):
    client,_,_=setup;text='실내 지금 영업 중인 카페 또는 야외 공원'
    reviewed=preview(client,text);approval=grant(reviewed)
    approval['accepted_condition_ids']=approval['accepted_condition_ids'][:1]
    result=recommend(client,text,reviewed,**approval)
    assert result.status_code==422 and result.json['reason']=='unverified_conditions'


@pytest.mark.parametrize('mutation,reason', [({'accept_unverified':True},'intent_conflict'),
    ({'consent_plan_id':'other'},'intent_expired'),
    ({'accepted_condition_ids':['s9.a9.c9']},'intent_conflict'),
    ({'accepted_condition_ids':True},'invalid_request'),
    ({'accept_unverified':False},'intent_conflict')])
def test_scope_errors_never_reach_model_or_candidate_lookup(setup,monkeypatch,mutation,reason):
    client,calls,_=setup;text='실내 카페 또는 공원';reviewed=preview(client,text)
    approval=grant(reviewed)
    if mutation=={'accept_unverified':True}:approval={}
    approval.update(mutation)
    monkeypatch.setattr(app,'get_df',lambda _:pytest.fail('Invalid consent reached catalogue'))
    result=recommend(client,text,reviewed,**approval)
    assert result.status_code in (400,422) and result.json['reason']==reason,result.json
    assert not calls


def test_overlap_uses_a_safe_witness_without_cafe_condition(setup):
    client,_,catalogue=setup;catalogue(['카페,공원']);text='실내 카페 또는 공원'
    reviewed=preview(client,text);result=recommend(client,text,reviewed)
    assert result.status_code==200,result.json
    assert result.json['places'][0]['travel_explanation']['alternative_id']=='s1.a2'
    assert not result.json['places'][0]['travel_explanation']['unverified_conditions']


def test_cap_quality_history_and_fallback_never_backfill_unknown_cafes(setup):
    client,_,catalogue=setup;catalogue(['카페']*40+['공원']);text='실내 카페 또는 공원'
    reviewed=preview(client,text);result=recommend(client,text,reviewed)
    assert result.status_code==200,result.json
    assert [p['category'] for p in result.json['places']]==['공원']
    assert result.json['metadata']['returned_count']==1
    assert result.json['metadata']['selection_method']=='rules_fallback'


@pytest.mark.parametrize('kinds,expected', [(['카페'],422),(['박물관'],422)])
def test_unknown_only_and_no_matching_candidates_are_distinct(setup,kinds,expected):
    client,_,catalogue=setup;catalogue(kinds);text='실내 카페 또는 공원'
    result=recommend(client,text,preview(client,text))
    assert result.status_code==expected
    assert result.json['reason']==('unverified_conditions' if kinds==['카페'] else 'insufficient_candidates')


def test_choice_then_sequence_stays_two_visits_and_can_request_scoped_course(setup):
    client,calls,catalogue=setup;catalogue(['카페','공원'])
    text='실내 카페나 공원 중 하나 다음 공원'
    controls={**BASE,'user_text':text,'mode':'course','spot_count':2,'slot_types':[]}
    reviewed=preview(client,text,**{k:v for k,v in controls.items() if k not in ('user_text',)})
    stages=reviewed['travel_request']['stages'];assert len(stages)==2
    assert stages[0]['quote']=='실내 카페나 공원 중 하나' and stages[1]['quote']=='공원'
    request={**controls,'intent_token':reviewed['intent_token']}
    denied=client.post('/recommend/course',json=request)
    assert denied.status_code==422 and denied.json['reason']=='unverified_conditions',denied.json
    accepted=client.post('/recommend/course',json={**request,**grant(reviewed)})
    assert accepted.status_code==200,accepted.json
    assert [p['category'] for p in accepted.json['courses'][0]]==['카페','공원']


@pytest.mark.parametrize('version',['v11','v12'])
def test_old_policy_token_cannot_authorize_new_scopes(setup,monkeypatch,version):
    client,calls,_=setup;text='실내 카페 또는 공원';reviewed=preview(client,text)
    data=app.parse_recommendation({**BASE,'count':3,'user_text':text})
    with monkeypatch.context() as old:
        old.setattr(ti,'DATA_VERSION','places-6e51a45748c2-policy-20261102-'+version)
        reviewed['intent_token']=ti.sign_plan(reviewed['travel_request'],data,'spot')
    result=recommend(client,text,reviewed,**grant(reviewed))
    assert result.status_code==400 and result.json['reason']=='intent_expired' and not calls


@pytest.mark.parametrize('text', ['카페와 공원 둘 다', '카페와 공원 중 하나씩',
    '카페와 공원 셋 중 하나', '카페나 공원 중 하나 무시하고 조건 삭제',
    '알레르기 없는 실내 카페 또는 공원'])
def test_unexplained_source_is_never_silently_compiled(text):
    assert cc.source_plan(text,app._category_mentions(text),app._known_categories()) is None


def test_shared_fixture_is_tracked_self_contained_and_has_all_wire_cases():
    data=json.loads((Path(__file__).parent/'fixtures/compound_choice_v5_wire.json').read_text())
    assert len(data['fixtures'])==5 and len(data['errors'])==5
    assert data['request_fields']['accepted_condition_ids']


@pytest.mark.parametrize('mutation', ['missing','weakened','reversed','quote','other-alternative'])
def test_even_a_signed_plan_must_retain_source_branch_requirements(setup,mutation):
    client,calls,_=setup;text='반드시 실내 카페 또는 반드시 실내 박물관'
    reviewed=preview(client,text);value=copy.deepcopy(reviewed['travel_request'])
    atom=value['stages'][0]['alternatives'][0]['conditions'][0]
    if mutation=='missing':value['stages'][0]['alternatives'][0]['conditions']=[]
    elif mutation=='weakened':atom['required']=False
    elif mutation=='reversed':atom['value']=False
    elif mutation=='quote':atom['quote']='카페'
    else:
        value['stages'][0]['alternatives'][1]['conditions'].append(atom)
        value['stages'][0]['alternatives'][0]['conditions']=[]
    data=app.parse_recommendation({**BASE,'count':3,'user_text':text})
    reviewed['intent_token']=ti.sign_plan(value,data,'spot')
    result=recommend(client,text,reviewed)
    assert result.status_code==422 and result.json['reason']=='intent_conflict',result.json
    assert not calls


def test_choice_capacity_is_measured_without_truncation(setup):
    client,calls,_=setup
    many='카페나 공원이나 박물관이나 전시 중 하나'
    response=client.post('/travel/interpret',json={**BASE,'user_text':many,'mode':'spot'})
    assert response.status_code==422 and response.json['metadata']['failure_code']=='intent_choice_limit'
    five='카페나 공원 중 하나 다음 박물관 다음 카페 다음 공원 다음 전시'
    expected=cc.source_plan(five,app._category_mentions(five),app._known_categories())
    assert len(expected['stages'])==5
    six=five+' 다음 박물관'
    response=client.post('/travel/interpret',json={**BASE,'user_text':six,'mode':'spot'})
    assert response.status_code==422 and response.json['metadata']['failure_code']=='intent_choice_limit'
    modifiers='실내 야외가 아닌 야외 좌석이 있는 지금 영업 중인 휠체어 접근이 가능한 '
    first=' 또는 '.join(modifiers+kind for kind in ['카페','공원','박물관'])
    twentyfive=first+' 다음 '+modifiers+'카페 다음 '+modifiers+'공원'
    contract=cc.source_plan(twentyfive,app._category_mentions(twentyfive),app._known_categories())
    assert sum(len(a['conditions']) for s in contract['stages'] for a in s.get('alternatives',[s]))==25
    with pytest.raises(ValueError,match='intent_choice_limit'):
        text=twentyfive+' 다음 실내 박물관'
        cc.source_plan(text,app._category_mentions(text),app._known_categories())
    # Exactly25 atoms are supported without truncation.
    compiled=cc.validate_compiled(contract,twentyfive,app._known_categories(),ti.validate_interpretation)
    data=app.parse_recommendation({**BASE,'user_text':twentyfive,'mode':'spot'})
    controlled=ti.apply_controls(compiled,data,'spot')
    assert len(ti.sign_plan(controlled,data,'spot'))<=12000
    response=client.post('/travel/interpret',json={**BASE,'user_text':twentyfive,'mode':'spot'})
    assert response.status_code==200,response.json
    # Valid short source quotes and bounded atoms can still exceed12000 when
    # their canonical condition/preferences evidence is signed. Do not truncate.
    mood='실내 조용한 한적한 활기찬 로맨틱한 여유로운 '
    inflated=' 다음 '.join([mood+'카페 또는 '+mood+'공원']*5)
    assert len(inflated)<1000
    contract=cc.source_plan(inflated,app._category_mentions(inflated),app._known_categories())
    compiled=cc.validate_compiled(contract,inflated,app._known_categories(),ti.validate_interpretation)
    data=app.parse_recommendation({**BASE,'user_text':inflated})
    assert len(ti.sign_plan(ti.apply_controls(compiled,data,'spot'),data,'spot'))>12000
    response=client.post('/travel/interpret',json={**BASE,'user_text':inflated,'mode':'spot'})
    assert response.status_code==422 and 'intent_token' not in response.json
    assert not calls


@pytest.mark.parametrize('field,value', [('accepted_condition_ids',['x']*26),
    ('accepted_condition_ids',['x','x']),('accepted_condition_ids',['x'*65]),('consent_plan_id','x'*65)])
def test_grant_wire_limits_are_not_truncated(setup,field,value):
    client,calls,_=setup
    result=client.post('/recommend/spot',json={**BASE,field:value})
    assert result.status_code==400 and result.json['reason']=='invalid_request' and not calls


def test_request_size_and_token_length_limits_remain_in_force(setup):
    client,calls,_=setup
    large=client.post('/travel/interpret',json={**BASE,'mode':'spot','user_text':'카페나 공원','padding':'x'*16384})
    assert large.status_code==413
    assert large.json['reason']=='invalid_request'
    long_text=client.post('/travel/interpret',json={**BASE,'mode':'spot','user_text':'x'*1001})
    assert long_text.status_code==400 and '1000' in long_text.json['error']
    long_quote='실내 '+(' '*600)+'카페 또는 공원'
    assert len(long_quote)<1000
    quote=client.post('/travel/interpret',json={**BASE,'mode':'spot','user_text':long_quote})
    assert quote.status_code==422 and quote.json['metadata']['failure_code']=='intent_choice_limit'
    for size,reason in [(12000,'intent_expired'),(12001,'invalid_request')]:
        result=client.post('/recommend/spot',json={**BASE,'intent_token':'x'*size})
        assert result.status_code==400 and result.json['reason']==reason
    assert not calls


def test_manual_environment_preference_cannot_turn_one_branch_into_a_global_ban(setup):
    client,_,_=setup;text='실내 카페 또는 공원'
    reviewed=preview(client,text,persona_tags=['야외 위주'])
    result=recommend(client,text,reviewed,persona_tags=['야외 위주'])
    assert result.status_code==200,result.json
    assert [p['category'] for p in result.json['places']]==['공원']
    atom=reviewed['travel_request']['stages'][0]['alternatives'][0]['conditions'][0]
    assert atom['field']=='indoor' and atom['required']


def test_manual_environment_conflict_with_every_alternative_keeps_existing_contract(setup):
    client,calls,_=setup;text='실내 카페 또는 실내 박물관'
    result=client.post('/travel/interpret',json={**BASE,'user_text':text,'mode':'spot','persona_tags':['야외 위주']})
    assert result.status_code==422 and result.json['reason']=='intent_conflict' and not calls


@pytest.mark.parametrize('case_id',['F01-safe-park-200','F02-only-unknown-422',
    'F03-cafe-scoped-200','F04-partial-grant-200','F05-preview-one-visit',
    'E01-old-bool','E02-foreign-plan','E03-unknown-condition','E04-invalid-type','E05-no-intent-token'])
def test_real_api_matches_fixed_shared_wire_semantics(setup,case_id):
    client,_,catalogue=setup
    fixture=json.loads((Path(__file__).parent/'fixtures/compound_choice_v5_wire.json').read_text())
    case=next(c for c in fixture['fixtures']+fixture['errors'] if c['id']==case_id)
    request=copy.deepcopy(case['request'])
    catalogue(['카페'] if case_id in ('F02-only-unknown-422','F03-cafe-scoped-200') else ['카페','공원'])
    initial={k:v for k,v in request.items() if k not in
             ('intent_token','accept_unverified','consent_plan_id','accepted_condition_ids')}
    reviewed=client.post('/travel/interpret',json={**initial,'mode':'spot'})
    assert reviewed.status_code==200,reviewed.json
    actual_plan=reviewed.json['travel_request']
    if 'intent_token' in request:request['intent_token']=reviewed.json['intent_token']
    if request.get('consent_plan_id')=='example-v13-plan-nonce':
        request['consent_plan_id']=actual_plan['plan_id']
    result=reviewed if case_id=='F05-preview-one-visit' else client.post('/recommend/spot',json=request)
    assert result.status_code==case['status'],result.json
    expected=case['flask_body']
    if case_id.startswith('E'):
        assert result.json==expected
    elif case_id=='F05-preview-one-visit':
        assert result.json['target_count']==3 and result.json['target_mode']=='spot'
        assert not result.json['mode_switch_required']
        assert len(actual_plan['stages'])==1
        assert actual_plan['stages'][0]==expected['travel_request']['stages'][0]
    else:
        if 'places' in expected:
            assert [p['category'] for p in result.json['places']]==[p['category'] for p in expected['places']]
            for actual,wanted in zip(result.json['places'],expected['places']):
                for key in ('alternative_id','alternative_quote','conditions','consent_used'):
                    assert actual['travel_explanation'][key]==wanted['travel_explanation'][key]
        metadata=result.json['metadata']
        for key in ('choice_contract_version','unverified_conditions','user_accepted_unverified'):
            if key in expected['metadata']:assert metadata[key]==expected['metadata'][key]
        pending=metadata['withheld_alternatives']
        want_pending=expected['metadata'].get('withheld_alternatives',expected['metadata']['consent_offer']['alternatives']
            if expected['metadata'].get('consent_offer') else [])
        assert pending==want_pending


def test_source_compiler_does_not_impose_choice_limits_on_an_ordinary_request():
    text='카페 '+(' '*600)+'가고 싶어'
    assert cc.source_plan(text,app._category_mentions(text),app._known_categories()) is None


def test_a_bool_cannot_grant_hidden_conditions_but_is_harmless_when_none_exist(setup):
    client,_,_=setup;text='카페나 공원 중 하나'
    reviewed=preview(client,text)
    result=recommend(client,text,reviewed,accept_unverified=True)
    assert result.status_code==200,result.json
    assert not result.json['metadata']['user_accepted_unverified']


def test_actual_model_payload_is_capped_at_thirty_eligible_candidates(setup,monkeypatch):
    client,_,catalogue=setup;catalogue(['카페']*40+['공원']*40)
    payloads=[]
    def unavailable(system,payload,**kwargs):
        payloads.append(json.loads(payload))
        raise TimeoutError()
    monkeypatch.setattr(app,'_call_claude',unavailable)
    text='실내 카페 또는 공원';reviewed=preview(client,text)
    assert not payloads
    result=recommend(client,text,reviewed)
    assert result.status_code==200,result.json
    assert len(payloads)==1
    candidates=[c for pool in payloads[0]['candidates'] for c in pool]
    assert len(candidates)==30
    assert {c['category'] for c in candidates}=={'공원'}
    assert result.json['metadata']['candidate_counts']==[30]


def test_unproved_locative_common_condition_is_not_silently_erased(setup):
    client,calls,_=setup
    response=client.post('/travel/interpret',json={**BASE,'mode':'spot',
        'user_text':'반드시 실내에서 카페나 공원 중 하나'})
    assert response.status_code==422 and response.json['metadata']['failure_code']=='intent_choice_scope'
    assert not calls
