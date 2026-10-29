"""Intent -> DB pool -> model decision -> public DTO, with external I/O denied."""
import copy
import itertools
import json
import threading
import time

import pandas as pd
import pytest

import app
import travel_intent as ti
from api_request import parse_recommendation
from place_identity import ensure_ids

TEXT = '연인과 산책하다가 시끌벅적한 야장에 가고 싶다'
BASE = dict(region='천안', transport='대중교통', user_lat=36.8151, user_lng=127.1139,
            count=1, persona_tags=[], intent_version=1, plan_mode='natural')


def stage(quote, cats, conditions=(), preferences=()):
    return dict(id='s1', activity=quote, quote=quote, category_filters=cats,
                conditions=list(conditions), preferences=list(preferences))


def condition(field, quote, required=True, value=True):
    return dict(field=field, quote=quote, required=required, value=value)


def plan(stages=None, companion=None, exclusions=()):
    stages = copy.deepcopy(stages or [stage('카페', ['카페'])])
    for i, s in enumerate(stages):
        s['id'] = f's{i+1}'
    return dict(schema_version=1, companion=companion, stages=stages,
                exclusions=list(exclusions), ambiguities=[], unsupported=[], requested_visit_count=None)


def walk_beer():
    return plan([stage('산책', ['공원', '산책로']),
                 stage('야장', ['맥주', '호프'], [condition('outdoor_seating', '야장')],
                       [dict(field='lively', quote='시끌벅적한')])], dict(value='연인과', quote='연인과'))


def frame(kinds=('공원', '산책로', '카페', '카페', '보드카페', '전시관', '박물관', '맥주,호프', '호프', '한식')):
    return ensure_ids(pd.DataFrame([dict(가게명=f'장소{i}', 주소=f'충남 천안시 테스트로 {i+1}',
        지역='천안', 카테고리=kind, latitude=36.8151+i*.0001, longitude=127.1139,
        방문자수=i*100, 블로그수=0, blog_tags='{}', blog_tag_status='legacy_unverified')
        for i, kind in enumerate(kinds)]))


def choice(public, stage_id):
    return dict(stage_id=stage_id, place_id=public['place_id'],
                evidence_refs=[e['id'] for e in public['evidence']],
                reason_codes=['category_match', 'distance'],
                satisfied_condition_ids=public['satisfied_condition_ids'],
                unverified_condition_ids=public['unverified_condition_ids'])


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(app, 'get_df', lambda _: frame())
    calls = []

    def install(p, mutate=None, fail_selection=False):
        def model(system, message, **options):
            payload = json.loads(message)
            calls.append((system, payload, options))
            assert 'user_lat' not in message and 'user_lng' not in message
            assert '127.1139' not in message and '36.8151' not in message
            assert options['max_retries'] == 1
            if system != ti.SELECTION_SYSTEM:
                assert payload['source_text']
                return copy.deepcopy(p)
            if fail_selection:
                raise TimeoutError()
            assert 'source_text' not in payload
            candidates = payload['candidates']
            # Select the last suitable venue first: the AI changes selection,
            # independent of the rule order/popularity winner.
            output = []
            for n in range(min(payload['count'], min(map(len, candidates)))):
                output.append([choice(pool[-1-n], payload['stages'][i]['id']) for i, pool in enumerate(candidates)])
            result = {'courses': output}
            if mutate:
                mutate(result)
            return result
        monkeypatch.setattr(app, '_call_claude', model)
    return install, calls


def preview(p, text, setup, mode='course', **controls):
    setup[0](p)
    data = dict(BASE, user_text=text, mode=mode, **controls)
    response = app.app.test_client().post('/travel/interpret', json=data)
    assert response.status_code == 200, response.json
    return data, response.json


def test_two_visits_keep_order_and_unknown_outdoor_is_not_success(setup):
    data, reviewed = preview(walk_beer(), TEXT, setup)
    client = app.app.test_client()
    request = {**data, 'intent_token': reviewed['intent_token']}
    strict = client.post('/recommend/course', json=request)
    assert strict.status_code == 422
    assert strict.json['reason'] == 'unverified_conditions'
    assert len(setup[1]) == 1  # no paid decision for impossible mandatory evidence
    result = client.post('/recommend/course', json={**request, 'accept_unverified': True})
    assert result.status_code == 200, result.json
    dto = result.json
    assert len(dto['courses'][0]) == 2
    assert [p['travel_explanation']['stage_id'] for p in dto['courses'][0]] == ['s1', 's2']
    assert app.category_matches(dto['courses'][0][0]['category'], ['공원', '산책로'])
    assert app.category_matches(dto['courses'][0][1]['category'], ['맥주', '호프'])
    assert dto['metadata']['intent_status'] == 'unverified_alternative'
    assert dto['metadata']['constraints_relaxed'] == []
    assert dto['metadata']['travel_request']['source_text'] == TEXT
    assert dto['metadata']['verified_tag_candidate_count'] == 0
    beer = dto['courses'][0][1]['travel_explanation']
    assert beer['unverified_conditions'] == ['야외 좌석', '활기찬 분위기']
    assert all(e['checked_at'] is None for e in beer['evidence'])
    assert len(setup[1]) == 2


@pytest.mark.parametrize('text,p,categories,unknown', [
    ('친구와 조용한 카페에서 쉬고 싶어요',
     plan([stage('카페', ['카페'], preferences=[dict(field='quiet', quote='조용한')])],
          dict(value='친구와', quote='친구와')), ['카페'], ['조용함']),
    ('연인과 시원한 맥주를 마시고 싶어요',
     plan([stage('맥주', ['맥주', '호프'], preferences=[dict(field='cool', quote='시원한')])],
          dict(value='연인과', quote='연인과')), ['맥주', '호프'], ['시원함']),
    ('보드게임카페에 가고 싶어요', plan([stage('보드게임카페', ['보드게임카페'])]), ['보드카페'], []),
    ('카페 말고는 가지 않을래요', plan(), ['카페'], []),
    ('카페가 아닌 곳은 싫어요', plan(), ['카페'], []),
    ('맥주 박물관을 보고 싶어요', plan([stage('박물관', ['박물관'])]), ['박물관'], []),
])
def test_single_intents_reach_dto_with_real_candidates(setup, text, p, categories, unknown):
    data, reviewed = preview(p, text, setup, mode='spot')
    result = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert result.status_code == 200, result.json
    place = result.json['places'][0]
    assert app.category_matches(place['category'], categories, place['name'])
    assert place['travel_explanation']['unverified_conditions'] == unknown
    assert result.json['metadata']['selection_method'] == 'ai_candidates'


def test_negated_cafe_indoor_exhibition_and_no_autorelaxation(setup):
    text = '카페 말고 부모님과 실내 전시를 보고 싶어요'
    p = plan([stage('전시', ['전시'], [condition('indoor', '실내')])],
             dict(value='부모님 모시고', quote='부모님과'),
             [dict(category_filters=['카페'], quote='카페 말고')])
    data, reviewed = preview(p, text, setup, mode='spot')
    result = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert result.status_code == 422
    assert result.json['reason'] == 'unverified_conditions'
    assert result.json['metadata']['candidate_counts'] == [1]
    accepted = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token'], 'accept_unverified': True})
    assert accepted.status_code == 200
    assert accepted.json['places'][0]['category'] == '전시관'


def test_spot_needs_explicit_mode_switch_and_signed_course_controls(setup):
    data, reviewed = preview(walk_beer(), TEXT, setup, mode='spot', count=5)
    assert reviewed['mode_switch_required'] is True
    assert reviewed['target_mode'] == 'course' and reviewed['target_count'] == 1
    wrong = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert wrong.status_code == 400
    switched = app.app.test_client().post('/recommend/course', json={**data, 'count': 1,
        'intent_token': reviewed['intent_token'], 'accept_unverified': True})
    assert switched.status_code == 200, switched.json
    assert len(setup[1]) == 2


@pytest.mark.parametrize('change', [dict(region='아산'), dict(transport='차'), dict(count=2),
    dict(user_text='새 카페'), dict(user_lat=36.82), dict(persona_tags=['친구와']),
    dict(plan_mode='manual', slot_types=['카페']*3, spot_count=3)])
def test_tokens_reject_changed_controls_without_more_model_calls(setup, change):
    data, reviewed = preview(plan(), '카페', setup)
    result = app.app.test_client().post('/recommend/course', json={**data, 'intent_token': reviewed['intent_token'], **change})
    assert result.status_code == 400
    assert len(setup[1]) == 1


def test_manual_slots_and_companion_override_are_visible(setup):
    data, reviewed = preview(plan(companion=dict(value='연인과', quote='연인과')), '연인과 카페', setup,
        plan_mode='manual', slot_types=['카페']*3, spot_count=3, persona_tags=['친구와', '조용한'])
    p = reviewed['travel_request']
    assert p['companion']['value'] == '친구와'
    assert len(p['stages']) == 3 and len(p['manual_overrides']) == 4
    assert p['stages'][0]['category_filters'] == ['카페']
    assert all(s['category_filters'] == app.SLOT_CATEGORY_MAP['카페'] for s in p['stages'][1:])
    assert all(s['preferences'][0]['id'] == f'{s["id"]}.p1' for s in p['stages'])
    assert all(s['preferences'][0]['field'] == 'quiet' for s in p['stages'])


def test_manual_activity_change_cannot_lose_required_conditions(setup):
    setup[0](walk_beer())
    result = app.app.test_client().post('/travel/interpret', json={**BASE, 'mode': 'course', 'user_text': TEXT,
        'plan_mode': 'manual', 'slot_types': ['카페']*3, 'spot_count': 3})
    assert result.status_code == 422 and result.json['reason'] == 'intent_conflict'


@pytest.mark.parametrize('mutate', [
    lambda r: r['courses'][0][0].update(place_id='invented'),
    lambda r: r['courses'][0][0].update(stage_id='s2'),
    lambda r: r['courses'][0].clear(),
    lambda r: r['courses'][0][0].update(evidence_refs=['fake']),
    lambda r: r['courses'][0][0].update(reason_codes=['quiet_95_percent']),
    lambda r: r['courses'][0][0].update(satisfied_condition_ids=['quiet']),
    lambda r: r['courses'][0][0].update(unverified_condition_ids=['fake']),
    lambda r: r['courses'][0][0].update(reason='현장 야외 좌석 확인 완료'),
    lambda r: r.update(courses=[]),
    lambda r: r.update(courses=r['courses']*2),
])
def test_forged_model_decisions_fall_back_honestly_without_retries(setup, mutate):
    data, reviewed = preview(plan(), '카페', setup, mode='spot')
    setup[0](plan(), mutate=mutate)
    result = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert result.status_code == 200, result.json
    assert result.json['metadata']['selection_method'] == 'rules_fallback'
    assert result.json['metadata']['intent_status'] == 'rules_fallback'
    assert len(setup[1]) == 2
    assert result.json['places'][0]['place_id'] != 'invented'


def test_duplicate_same_visit_with_two_ids_is_rejected_but_courses_may_share(setup, monkeypatch):
    f = frame(('카페', '카페', '카페'))
    duplicate = f.iloc[0].copy(); duplicate['place_id'] = 'different-provider-id'
    f = pd.concat([f, duplicate.to_frame().T], ignore_index=True)
    monkeypatch.setattr(app, 'get_df', lambda _: f)
    p = plan([stage('첫 카페', ['카페']), stage('둘째 카페', ['카페'])])
    data, reviewed = preview(p, '첫 카페 그리고 둘째 카페', setup, count=2)
    def duplicate_choice(r):
        r['courses'][0][1] = {**r['courses'][0][0], 'stage_id': 's2'}
    setup[0](p, mutate=duplicate_choice)
    result = app.app.test_client().post('/recommend/course', json={**data, 'intent_token': reviewed['intent_token']})
    assert result.status_code == 200, result.json
    assert result.json['metadata']['selection_method'] == 'rules_fallback'
    assert len(result.json['courses']) == 2
    assert all(len({p['place_id'] for p in c}) == 2 for c in result.json['courses'])
    assert set(p['place_id'] for p in result.json['courses'][0]) & set(p['place_id'] for p in result.json['courses'][1])


@pytest.mark.parametrize('mutation', [
    lambda p: p['stages'][0].update(id='s2'),
    lambda p: p['stages'][0].update(quote='없는 원문'),
    lambda p: p['stages'][0].update(category_filters=['없는 종류']),
    lambda p: p.update(schema_version=True),
    lambda p: p.update(requested_visit_count=dict(value=float('nan'), quote='카페')),
    lambda p: p.update(stages=p['stages']*6),
    lambda p: p['stages'][0].update(conditions=[condition('indoor', '카페'), condition('outdoor', '카페')]),
])
def test_invalid_interpretation_does_not_search_or_select(setup, monkeypatch, mutation):
    p = plan(); mutation(p); setup[0](p)
    monkeypatch.setattr(app, 'get_df', lambda _: pytest.fail('invalid plan cannot search'))
    result = app.app.test_client().post('/travel/interpret', json={**BASE, 'user_text': '카페'})
    assert result.status_code == 503
    assert len(setup[1]) == 1


def test_dropped_direct_exclusion_is_rejected(setup):
    setup[0](plan([stage('전시', ['전시'])]))
    result = app.app.test_client().post('/travel/interpret', json={**BASE, 'user_text': '카페 말고 전시'})
    assert result.status_code == 503


def test_unavailable_interpretation_has_no_fake_ai_success(monkeypatch):
    monkeypatch.setattr(app, '_call_claude', lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    result = app.app.test_client().post('/travel/interpret', json={**BASE, 'user_text': '카페'})
    assert result.status_code == 503 and result.json['reason'] == 'intent_unavailable'


def test_selection_timeout_falls_back_and_late_result_is_ignored(setup):
    data, reviewed = preview(plan(), '카페', setup, mode='spot')
    setup[0](plan(), fail_selection=True)
    result = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert result.status_code == 200 and result.json['metadata']['selection_method'] == 'rules_fallback'
    done = threading.Event()
    def slow(*args, **kwargs):
        done.wait(.5)
        return {'late': True}
    before = time.monotonic()
    with pytest.raises(TimeoutError):
        ti.bounded_model(slow, 's', {}, .01)
    assert time.monotonic() - before < .3
    done.set()


def test_candidate_pool_includes_nearby_low_popularity_and_rare_kind(setup, monkeypatch):
    f = frame(['공원']*80 + ['산책로'])
    f.loc[0, '방문자수'] = 0
    f.loc[80, '방문자수'] = 0
    monkeypatch.setattr(app, 'get_df', lambda _: f)
    data, reviewed = preview(plan([stage('산책', ['공원', '산책로'])]), '산책', setup, mode='spot')
    result = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert result.status_code == 200, result.json
    candidates = setup[1][-1][1]['candidates'][0]
    assert len(candidates) == 30
    assert f.iloc[0]['place_id'] in {c['place_id'] for c in candidates}
    assert f.iloc[80]['place_id'] in {c['place_id'] for c in candidates}


def test_no_candidates_and_count_shortage_keep_constraints(setup, monkeypatch):
    monkeypatch.setattr(app, 'get_df', lambda _: frame(('카페',)))
    data, reviewed = preview(plan([stage('전시', ['전시'])]), '전시', setup, mode='spot')
    result = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert result.status_code == 422 and result.json['metadata']['candidate_counts'] == [0]
    assert len(setup[1]) == 1
    data, reviewed = preview(plan(), '카페', setup, mode='spot', count=3)
    result = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert result.status_code == 200 and len(result.json['places']) == 1
    assert result.json['metadata']['reason'] == 'insufficient_candidates'


def test_fixed_plan_model_is_deterministic_and_key_changes_with_evidence(setup, monkeypatch):
    data, reviewed = preview(plan(), '카페', setup, mode='spot')
    req = {**data, 'intent_token': reviewed['intent_token']}
    a = app.app.test_client().post('/recommend/spot', json=req).json
    b = app.app.test_client().post('/recommend/spot', json=req).json
    assert a == b
    assert a['metadata']['request_key']
    changed = frame()
    changed.loc[changed['카테고리'].eq('카페'), '가게명'] = '새 자료의 카페명'
    monkeypatch.setattr(app, 'get_df', lambda _: changed)
    c = app.app.test_client().post('/recommend/spot', json=req).json
    assert c['metadata']['request_key'] != a['metadata']['request_key']


def test_cafe_only_ai_variants_use_diverse_validated_rules(monkeypatch):
    f = frame(['한식']*3 + ['공원']*3 + ['카페']*4)
    f['방문자수'] = 100
    monkeypatch.setattr(app, 'get_df', lambda _: f)
    p = plan([stage('한식',['한식']),stage('산책',['공원']),stage('카페',['카페'])])
    calls=[]
    def model(system, message, **options):
        if system != ti.SELECTION_SYSTEM:
            return copy.deepcopy(p)
        payload=json.loads(message);calls.append(payload)
        return {'courses':[[choice(pool[0 if i<2 else n],f's{i+1}')
                            for i,pool in enumerate(payload['candidates'])] for n in range(3)]}
    monkeypatch.setattr(app,'_call_claude',model)
    req=dict(BASE,user_text='한식 먹고 산책하고 카페',count=3,seed=77,randomize=True)
    response=app.app.test_client().post('/recommend/course',json=req)
    assert response.status_code==200,response.json
    body=response.json
    assert body['metadata']['selection_method']=='rules_fallback'
    assert body['metadata']['course_diversity']['similar_pair_count']==0
    assert body['metadata']['course_diversity']['randomized']
    assert body['metadata']['seed']==77
    assert calls[0]['selection_seed']==77
    assert len(calls)==1
    assert body['metadata']['constraints_relaxed']==[]
    for a,b in itertools.combinations(body['courses'],2):
        assert len({r['place_id'] for r in a}&{r['place_id'] for r in b})<=1


def test_seeded_course_fallback_replays_and_varies_without_changing_stages(setup,monkeypatch):
    f=frame(['공원']*4+['카페']*4);f['방문자수']=100
    monkeypatch.setattr(app,'get_df',lambda _:f)
    p=plan([stage('산책',['공원']),stage('카페',['카페'])])
    setup[0](p,fail_selection=True)
    def recommend(seed):
        r=app.app.test_client().post('/recommend/course',json=dict(BASE,
            user_text='산책 후 카페',count=3,seed=seed,randomize=True))
        assert r.status_code==200,r.json
        assert r.json['metadata']['course_diversity']['similar_pair_count']==0
        assert all(len(c)==2 for c in r.json['courses'])
        return [[v['place_id'] for v in c] for c in r.json['courses']]
    a=recommend(20)
    assert recommend(20)==a
    assert any(recommend(seed)!=a for seed in range(21,25))


def test_review_token_binds_randomization_and_seed(setup):
    data,reviewed=preview(plan(),'카페',setup,mode='spot',seed=123,randomize=True)
    client=app.app.test_client()
    for changed in [{'seed':124},{'randomize':False}]:
        r=client.post('/recommend/spot',json={**data,'intent_token':reviewed['intent_token'],**changed})
        assert r.status_code==400 and r.json['reason']=='intent_expired'


def test_ai_course_with_long_cross_town_legs_is_rejected_by_server_cost(monkeypatch):
    f=frame(['한식','한식','공원','공원','카페','카페'])
    f['방문자수']=100
    f['latitude']=[36.85,36.78]*3
    monkeypatch.setattr(app,'get_df',lambda _:f)
    p=plan([stage('한식',['한식']),stage('산책',['공원']),stage('카페',['카페'])])
    bad_ids=[f.iloc[i]['place_id'] for i in (0,3,4)]
    def model(system,message,**opts):
        if system!=ti.SELECTION_SYSTEM:return copy.deepcopy(p)
        payload=json.loads(message)
        return {'courses':[[choice(next(c for c in pool if c['place_id']==bad_ids[i]),f's{i+1}')
                            for i,pool in enumerate(payload['candidates'])]]}
    monkeypatch.setattr(app,'_call_claude',model)
    response=app.app.test_client().post('/recommend/course',json=dict(BASE,
        user_text='한식 먹고 산책 후 카페',count=1))
    assert response.status_code==200,response.json
    assert response.json['metadata']['selection_method']=='rules_fallback'
    assert [r['place_id'] for r in response.json['courses'][0]]!=bad_ids
    assert response.json['course_metrics'][0]['estimated_distance_km']<5
    assert response.json['metadata']['constraints_relaxed']==[]


def test_ai_changes_real_selection_and_failure_is_distinct(setup):
    data, reviewed = preview(plan(), '카페', setup, mode='spot')
    req = {**data, 'intent_token': reviewed['intent_token']}
    ai = app.app.test_client().post('/recommend/spot', json=req).json
    setup[0](plan(), fail_selection=True)
    rules = app.app.test_client().post('/recommend/spot', json=req).json
    assert ai['places'][0]['place_id'] != rules['places'][0]['place_id']
    assert ai['metadata']['selection_method'] == 'ai_candidates'
    assert rules['metadata']['selection_method'] == 'rules_fallback'


def test_token_tampering_expiry_and_unreviewed_alternative_are_rejected(setup, monkeypatch):
    data, reviewed = preview(plan(), '카페', setup, mode='spot')
    client = app.app.test_client()
    assert client.post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']+'x'}).status_code == 400
    before = time.time()
    monkeypatch.setattr(ti.time, 'time', lambda: before + ti.TOKEN_TTL + 1)
    assert client.post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']}).status_code == 400
    assert client.post('/recommend/spot', json={**data, 'accept_unverified': True}).status_code == 400


def test_capacity_is_bounded_without_launching_more_model_work():
    for _ in range(4):
        assert ti._MODEL_SLOTS.acquire(timeout=.5)
    try:
        with pytest.raises(RuntimeError, match='intent_capacity'):
            ti.bounded_model(lambda *a, **k: pytest.fail('must not launch'), 's', {}, .1)
    finally:
        for _ in range(4):
            ti._MODEL_SLOTS.release()


def test_unsupported_conditions_stop_before_search(setup, monkeypatch):
    p = plan(); p['unsupported'] = [dict(quote='휠체어 경사도', reason='경사도 자료가 없습니다.')]
    data, reviewed = preview(p, '카페 휠체어 경사도 확인해줘', setup, mode='spot')
    monkeypatch.setattr(app, 'get_df', lambda _: pytest.fail('cannot ignore unsupported condition'))
    result = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert result.status_code == 422 and result.json['reason'] == 'intent_conflict'


@pytest.mark.parametrize('text,p', [
    (TEXT, plan([stage('산책', ['공원']), stage('야장', ['맥주', '호프'])])),
    ('닭갈비', plan([stage('닭갈비', ['한식'])])),
    ('산책', plan([stage('산책', ['카페'])])),
])
def test_literal_hard_requirements_cannot_be_dropped_by_model(setup, text, p):
    setup[0](p)
    result = app.app.test_client().post('/travel/interpret', json={**BASE, 'user_text': text})
    assert result.status_code == 503


def test_unrelated_nearby_word_cannot_disable_required_yard_check(setup,monkeypatch):
    p=plan([stage('산책',['공원']),stage('야장',['맥주','호프'])])
    setup[0](p)
    monkeypatch.setattr(app,'get_df',lambda _:pytest.fail('dropped required condition cannot search'))
    result=app.app.test_client().post('/travel/interpret',json={**BASE,
        'user_text':'가까운 데서 산책하다가 야장'})
    assert result.status_code==503 and result.json['reason']=='intent_unavailable'


@pytest.mark.parametrize('text',['야장 근처 카페','야장 말고 카페','야장보다 카페'])
def test_yard_landmark_or_exclusion_is_not_an_outdoor_requirement(text):
    app._validate_literal_intent(plan(),text)


def test_new_model_pool_cannot_include_kids_from_indoor_entertainment(setup, monkeypatch):
    monkeypatch.setattr(app, 'get_df', lambda _: frame(('키즈카페,실내놀이터', '볼링')))
    p = plan([stage('실내 오락', ['키즈카페', '볼링', '오락'])])
    data, reviewed = preview(p, '실내 오락', setup, mode='spot', persona_tags=['친구와'])
    result = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert result.status_code == 200, result.json
    assert result.json['metadata']['family_policy']['excluded_count'] == 1
    assert setup[1][-1][1]['candidates'][0][0]['category'] == '볼링'


def test_result_quantity_does_not_manufacture_a_second_visit(setup):
    p = plan(); p['requested_result_count'] = {'value': 2, 'quote': '두 곳'}
    data, reviewed = preview(p, '카페 두 곳 추천해줘', setup, mode='spot', count=3)
    assert reviewed['mode_switch_required'] is False
    assert len(reviewed['travel_request']['stages']) == 1
    assert '3개' in reviewed['travel_request']['manual_overrides'][0]
    result = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert result.status_code == 200
    assert result.json['metadata']['requested_count'] == 3


def test_natural_one_two_to_five_visits_only_and_legacy_minimum_three():
    for n in range(1, 6):
        assert parse_recommendation({**BASE, 'spot_count': n}, True)['spot_count'] == n
    for n in (0, 6, True, float('nan')):
        with pytest.raises(ValueError):
            parse_recommendation({**BASE, 'spot_count': n}, True)
    with pytest.raises(ValueError):
        parse_recommendation({**BASE, 'intent_version': None, 'spot_count': 2}, True)


@pytest.mark.parametrize('text', ['음식점 또는 카페', '음식점이나 카페', '음식점/카페',
    '음식점 또는 조용한 카페', '음식점이나 가까운 카페'])
def test_alternative_food_and_cafe_keeps_both_candidate_purposes(setup, monkeypatch, text):
    monkeypatch.setattr(app, 'get_df', lambda _: frame(('한식', '카페')))
    p = plan([stage(text, ['음식점', '카페'])])
    data, reviewed = preview(p, text, setup, mode='spot', count=2)
    assert '한식' in reviewed['travel_request']['stages'][0]['category_filters']
    response = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert response.status_code == 200, response.json
    assert {v['category'] for v in response.json['places']} == {'한식', '카페'}


def test_manual_environment_and_unsupported_tags_remain_honest(setup):
    data, reviewed = preview(plan(), '카페', setup, mode='spot',
        persona_tags=['친구와', '실내 위주', '감성적인', '생일'])
    p = reviewed['travel_request']
    assert p['unapplied_manual_tags'] == ['감성적인', '생일']
    assert all(tag in ' '.join(p['manual_overrides']) for tag in ['실내 위주', '감성적인', '생일'])
    assert p['stages'][0]['conditions'] == [dict(id='s1.c1', field='indoor', value=True,
        required=False, quote=None, source='manual')]
    response = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert response.status_code == 200, response.json
    detail = response.json['places'][0]['travel_explanation']
    assert detail['unverified_conditions'] == ['실내']
    assert detail['satisfied_conditions'] == ['장소 종류']


def test_manual_environment_cannot_silently_override_required_opposite(setup):
    setup[0](plan([stage('카페', ['카페'], [condition('outdoor', '야외')])]))
    response = app.app.test_client().post('/travel/interpret', json={**BASE, 'mode':'spot',
        'user_text':'야외 카페', 'persona_tags':['실내 위주']})
    assert response.status_code == 422
    assert response.json['reason'] == 'intent_conflict'


def test_switch_reapplying_controls_does_not_duplicate_environment_conditions(setup):
    data, reviewed = preview(plan([stage('산책', ['공원']), stage('카페', ['카페'])]),
        '산책 후 카페', setup, mode='spot', persona_tags=['야외 위주', '생일'])
    assert reviewed['mode_switch_required'] is True
    p = reviewed['travel_request']
    assert all(len(s['conditions']) == 1 for s in p['stages'])
    assert p['unapplied_manual_tags'] == ['생일']


@pytest.mark.parametrize('text,filters,expected', [
    ('닭갈비 음식점', ['닭갈비', '음식점'], {'닭갈비'}),
    ('닭갈비 음식점 또는 카페', ['닭갈비', '음식점', '카페'], {'닭갈비', '카페'}),
])
def test_specific_food_modifier_does_not_become_broad_or_alternative(setup, text, filters, expected):
    _, reviewed = preview(plan([stage(text, filters)]), text, setup, mode='spot')
    assert set(reviewed['travel_request']['stages'][0]['category_filters']) == expected


def test_negative_environment_condition_keeps_its_polarity_in_confirmation_and_result(setup):
    text = '실내가 아닌 카페'
    p = plan([stage('카페', ['카페'], [condition('indoor', '실내가 아닌', value=False)])])
    data, reviewed = preview(p, text, setup, mode='spot')
    client = app.app.test_client()
    request = {**data, 'intent_token': reviewed['intent_token']}
    strict = client.post('/recommend/spot', json=request)
    assert strict.status_code == 422
    assert strict.json['metadata']['unverified_conditions'][0]['label'] == '실내 아님'
    accepted = client.post('/recommend/spot', json={**request, 'accept_unverified': True})
    assert accepted.status_code == 200
    assert accepted.json['places'][0]['travel_explanation']['unverified_conditions'] == ['실내 아님']


@pytest.mark.parametrize('first', ['음식점 또는 카페', '음식점 또는 조용한 카페'])
def test_category_normalization_uses_each_stage_quote_not_another_stage_alternative(setup, first):
    text = first + '에 갔다가 닭갈비 음식점'
    p = plan([stage(first, ['음식점', '카페']),
              stage('닭갈비 음식점', ['닭갈비', '음식점'])])
    _, reviewed = preview(p, text, setup)
    actual = reviewed['travel_request']['stages']
    assert '한식' in actual[0]['category_filters'] and '카페' in actual[0]['category_filters']
    assert actual[1]['category_filters'] == ['닭갈비']


@pytest.mark.parametrize('text', ['천안역 근처 닭갈비', '붐비지 않는 닭갈비', '시끄러운 곳보다 닭갈비'])
def test_unrelated_spatial_or_negative_phrase_cannot_disable_specific_kind_guard(setup, text):
    setup[0](plan([stage('닭갈비', ['한식'])]))
    response = app.app.test_client().post('/travel/interpret', json={**BASE, 'mode':'spot', 'user_text':text})
    assert response.status_code == 503
    assert response.json['reason'] == 'intent_unavailable'


@pytest.mark.parametrize('text', ['카페 근처 닭갈비', '카페 말고 닭갈비', '카페보다 닭갈비'])
def test_kind_guard_respects_local_landmark_exclusion_and_comparison(text):
    app._validate_literal_intent(plan([stage('닭갈비', ['닭갈비'])]), text)


def test_specific_food_cannot_be_expanded_even_if_original_kind_is_in_the_array(setup):
    setup[0](plan([stage('닭갈비 맛집', app.FOOD_CATS)]))
    response = app.app.test_client().post('/travel/interpret', json={**BASE, 'mode':'spot', 'user_text':'닭갈비 맛집'})
    assert response.status_code == 503 and response.json['reason'] == 'intent_unavailable'


def test_manual_slots_preserve_specific_food_and_cafe_kinds(setup):
    p = plan([stage('닭갈비', ['닭갈비']), stage('카페', ['카페'])])
    _, reviewed = preview(p, '닭갈비 먹고 카페', setup, plan_mode='manual',
        slot_types=['음식','자연·산책','카페'], spot_count=3)
    stages = reviewed['travel_request']['stages']
    assert stages[0]['category_filters'] == ['닭갈비']
    assert stages[1]['category_filters'] == app.SLOT_CATEGORY_MAP['자연·산책']
    assert stages[2]['category_filters'] == ['카페']
    assert '종류 범위 전체' not in ' '.join(reviewed['travel_request']['manual_overrides'])


def test_ai_spot_poor_popularity_and_origin_distance_falls_back(monkeypatch):
    f = frame(('카페','카페'))
    f['방문자수'] = [1000, 0]
    f['latitude'] = [BASE['user_lat'], BASE['user_lat'] + .035]
    monkeypatch.setattr(app, 'get_df', lambda _: f)
    worst = f.iloc[1]['place_id']
    def model(system, message, **options):
        if system != ti.SELECTION_SYSTEM:
            return plan()
        payload = json.loads(message)
        public = next(p for p in payload['candidates'][0] if p['place_id'] == worst)
        return {'courses':[[choice(public,'s1')]]}
    monkeypatch.setattr(app, '_call_claude', model)
    response = app.app.test_client().post('/recommend/spot', json={**BASE,'user_text':'카페'})
    assert response.status_code == 200, response.json
    assert response.json['places'][0]['place_id'] == f.iloc[0]['place_id']
    assert response.json['metadata']['selection_method'] == 'rules_fallback'
    assert response.json['metadata']['display_order'] == 'rule_quality_order'
    assert response.json['metadata']['spot_quality']['quality_window'] == .15


@pytest.mark.parametrize('natural', [False, True])
def test_spot_new_seed_varies_near_equal_candidates_and_same_seed_replays(setup, monkeypatch, natural):
    f = frame(('카페',)*8)
    f['방문자수'] = 100
    f['latitude'] = BASE['user_lat']
    monkeypatch.setattr(app, 'get_df', lambda _: f)
    setup[0](plan(), fail_selection=True)
    body = dict(BASE, user_text='카페', randomize=True)
    if not natural:
        body.pop('intent_version')
        body['plan_mode'] = 'manual'
    client = app.app.test_client()
    def result(seed):
        response = client.post('/recommend/spot', json={**body,'seed':seed})
        assert response.status_code == 200, response.json
        assert response.json['metadata']['spot_quality']['randomized'] is True
        return tuple(p['place_id'] for p in response.json['places'])
    outcomes = [result(seed) for seed in range(8)]
    assert len(set(outcomes)) > 1
    assert result(0) == outcomes[0]


def test_intent_does_not_call_empty_search_label_factual_category(setup, monkeypatch):
    f = frame(('카페',''))
    f['search_category'] = '카페'
    f['category_source'] = 'legacy_unknown'
    monkeypatch.setattr(app,'get_df',lambda _:f)
    setup[0](plan(), fail_selection=True)
    response = app.app.test_client().post('/recommend/spot', json={**BASE,'user_text':'카페'})
    assert response.status_code == 200
    place = response.json['places'][0]
    assert place['place_id'] == f.iloc[0]['place_id']
    category = place['travel_explanation']['evidence'][0]
    assert category['value'] == '카페' and category['category_source'] == 'legacy_unknown'
    assert '등록된 장소 분류' in place['travel_explanation']['reason']



def test_manual_activity_notice_uses_picker_label_but_preserves_wire_tag(setup):
    _, reviewed = preview(plan(), '카페', setup, mode='spot', persona_tags=['카페 투어'])
    p = reviewed['travel_request']
    assert p['unapplied_manual_tags'] == ['카페 투어']
    assert p['applied_controls']['persona_tags'] == ['카페 투어']
    notices = ' '.join(p['manual_overrides'])
    assert '카페·디저트' in notices and '카페 투어' not in notices


@pytest.mark.parametrize('error,expected', [
    (TimeoutError('private-provider-text'), 'deadline'),
    (ti.ModelBoundaryError('input_limit'), 'input_limit'),
    (ti.ModelBoundaryError('capacity'), 'capacity'),
    (ti.ModelBoundaryError('provider_timeout'), 'provider_timeout'),
    (ti.ModelBoundaryError('model_unavailable'), 'model_unavailable'),
    (ValueError('selection_spot_quality'), 'quality_guard'),
    (ValueError('selection_brand_variety'), 'diversity_guard'),
    (ValueError('private-provider-text'), 'invalid_selection'),
])
def test_fallback_metadata_exposes_only_safe_reason_codes(setup, monkeypatch, error, expected):
    data, reviewed = preview(plan(), '카페', setup, mode='spot')
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(ti, 'bounded_model', fail)
    response = app.app.test_client().post('/recommend/spot', json={**data,'intent_token':reviewed['intent_token']})
    assert response.status_code == 200
    assert response.json['metadata']['selection_method'] == 'rules_fallback'
    assert response.json['metadata']['selection_fallback_reason'] == expected
    assert response.json['metadata']['selection_validation_reason'] == (
        str(error) if str(error) in {'selection_spot_quality', 'selection_brand_variety'} else None)
    assert 'private-provider-text' not in response.get_data(as_text=True)


def test_bounded_model_reports_input_output_and_provider_failure_separately():
    with pytest.raises(ti.ModelBoundaryError) as input_error:
        ti.bounded_model(lambda *a, **kw: pytest.fail('must not call'), 's', {'text':'x'*36000},1)
    assert input_error.value.reason == 'input_limit'
    with pytest.raises(ti.ModelBoundaryError) as output_error:
        ti.bounded_model(lambda *a, **kw: {'text':'x'*24000},'s',{},1)
    assert output_error.value.reason == 'output_limit'
    def provider_timeout(*args, **kwargs):
        raise TimeoutError('private-provider-text')
    with pytest.raises(ti.ModelBoundaryError) as provider_error:
        ti.bounded_model(provider_timeout,'s',{},1)
    assert provider_error.value.reason == 'provider_timeout'
    assert 'private-provider-text' not in str(provider_error.value)


def test_successful_ai_selection_has_no_fallback_reason(setup):
    data, reviewed = preview(plan(), '카페', setup, mode='spot')
    response = app.app.test_client().post('/recommend/spot',json={**data,'intent_token':reviewed['intent_token']})
    assert response.status_code == 200
    assert response.json['metadata']['selection_method']=='ai_candidates'
    assert response.json['metadata']['selection_fallback_reason'] is None
    assert response.json['metadata']['selection_validation_reason'] is None
    interpretation_options, selection_options = [call[2] for call in setup[1]]
    assert 'timeout_seconds' not in interpretation_options
    assert selection_options['timeout_seconds'] == 8
    assert selection_options['max_retries'] == 1


@pytest.mark.parametrize('mutate,reason', [
    (lambda r: r['courses'][0][0].update(evidence_refs=[r['courses'][0][0]['place_id'] + ':category']), 'selection_evidence'),
    (lambda r: r['courses'][0][0].update(unverified_condition_ids=['invented']), 'selection_conditions'),
    (lambda r: r.update(courses=[]), 'selection_count'),
    (lambda r: r['courses'][0][0].update(extra='private-value'), 'intent_schema'),
])
def test_local_selection_validation_code_identifies_failure_without_relaxing_guard(setup, mutate, reason):
    data, reviewed = preview(plan(), '카페', setup, mode='spot')
    setup[0](plan(), mutate=mutate)
    response = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert response.status_code == 200
    assert response.json['metadata']['selection_method'] == 'rules_fallback'
    assert response.json['metadata']['selection_fallback_reason'] == 'invalid_selection'
    assert response.json['metadata']['selection_validation_reason'] == reason
    assert 'private-value' not in response.get_data(as_text=True)


def test_selection_payload_supplies_exact_feasible_count_when_below_requested_count(setup):
    data, reviewed = preview(plan(), '카페', setup, mode='spot', count=3)
    response = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token': reviewed['intent_token']})
    assert response.status_code == 200
    payload = setup[1][-1][1]
    assert payload['count'] == 3
    assert payload['expected_count'] == len(response.json['places']) == 2


def test_selection_prompt_example_satisfies_actual_evidence_and_condition_contract():
    candidate_line = next(line for line in ti.SELECTION_SYSTEM.splitlines() if line.startswith('예시 후보:'))
    output_line = next(line for line in ti.SELECTION_SYSTEM.splitlines() if line.startswith('예시 출력('))
    public = json.loads(candidate_line.split(': ', 1)[1])
    result = json.loads(output_line.split(': ', 1)[1])
    row = frame(('카페',)).iloc[0].to_dict()
    row['place_id'] = public['place_id']
    pools = [[{'public': public, 'row': row}]]
    assert ti.validate_selection(result, pools, plan(), 1, 'spot', expected=1) == result['courses']
    assert len(result['courses'][0][0]['evidence_refs']) == 2


def unresolved_date(text):
    value = plan(companion={'value': '연인과', 'quote': '연인이랑'})
    value['stages'] = []
    value['ambiguities'] = [{'quote': text, 'reason': '방문할 활동 선택이 필요합니다'}]
    return value


def clarify_date(setup, text='연인이랑 데이트 할 곳을 찾고있어요', **controls):
    data, body = preview(unresolved_date(text), text, setup, mode='spot', **controls)
    assert body['clarification_required'] is True
    assert 'intent_token' not in body
    assert body['travel_request']['source_text'] == text
    return data, body['clarification']['token']


def chosen_date(text, indoor=False):
    return plan([stage('카페·디저트', ['카페'],
                       [condition('indoor', '실내')] if indoor else [],
                       [{'field': 'quiet', 'quote': '조용한'}] if indoor else [])],
                companion={'value': '연인과', 'quote': '연인이랑'})


def test_generic_date_clarifies_without_guessing_activity_or_first_date(setup):
    data, token = clarify_date(setup, persona_tags=['연인과', '첫 데이트'])
    first = app.app.test_client().post('/travel/interpret', json={**data, 'mode': 'spot'}).json
    assert [option['value'] for option in first['clarification']['options']] == list(ti.CORE_ACTIVITY_LABELS)
    assert first['travel_request']['stages'] == []
    assert first['travel_request']['applied_controls']['persona_tags'] == ['연인과', '첫 데이트']
    setup[0](chosen_date(data['user_text']))
    selected = {**data, 'mode': 'spot', 'activity_choice': '카페', 'clarification_token': token}
    response = app.app.test_client().post('/travel/interpret', json=selected)
    assert response.status_code == 200, response.json
    assert response.json['clarification_required'] is False
    result = response.json['travel_request']
    assert result['source_text'] == data['user_text']
    assert result['activity_choice'] == '카페'
    assert result['companion']['value'] == '연인과'
    assert result['unapplied_manual_tags'] == ['첫 데이트']
    token = response.json['intent_token']
    assert ti.read_plan(token, parse_recommendation(selected), 'spot')['activity_choice'] == '카페'
    for changed in ({'activity_choice': '음식'}, {'activity_choice': None}):
        changed_data = parse_recommendation(selected)
        changed_data.update(changed)
        with pytest.raises(ti.IntentError):
            ti.read_plan(token, changed_data, 'spot')


@pytest.mark.parametrize('drop', [None, 'condition', 'preference', 'companion'])
def test_activity_choice_preserves_original_indoor_quiet_and_companion(setup, drop):
    text = '연인이랑 조용한 실내 데이트'
    data, token = clarify_date(setup, text)
    resolved = chosen_date(text, indoor=True)
    if drop == 'condition': resolved['stages'][0]['conditions'] = []
    if drop == 'preference': resolved['stages'][0]['preferences'] = []
    if drop == 'companion': resolved['companion'] = None
    setup[0](resolved)
    response = app.app.test_client().post('/travel/interpret', json={**data, 'mode': 'spot',
        'activity_choice': '카페', 'clarification_token': token})
    assert response.status_code == (503 if drop else 200), response.json
    if not drop:
        result = response.json['travel_request']
        assert result['source_text'] == text
        assert result['stages'][0]['conditions'][0]['required'] is True
        assert result['stages'][0]['preferences'][0]['field'] == 'quiet'


@pytest.mark.parametrize('change', [
    {'user_text': '연인이랑 닭갈비 먹을 곳'}, {'seed': 7}, {'persona_tags': ['혼자']},
    {'clarification_token': 'invalid'}, {'clarification_token': ''}, {'activity_choice': None},
    {'activity_choice': '관광지'}, {'activity_choice': ['카페']},
])
def test_activity_choice_rejects_changed_context_or_missing_invalid_selection_before_model(setup, change):
    data, token = clarify_date(setup)
    before = len(setup[1])
    request = {**data, 'mode': 'spot', 'activity_choice': '카페', 'clarification_token': token, **change}
    response = app.app.test_client().post('/travel/interpret', json=request)
    assert response.status_code == 400 or response.status_code == 422
    assert len(setup[1]) == before


def test_activity_choice_rejects_expired_and_wrong_purpose_tokens(setup, monkeypatch):
    data, token = clarify_date(setup)
    parsed = parse_recommendation(data)
    with pytest.raises(ti.IntentError):
        ti.read_plan(token, parsed, 'spot')
    now = ti.time.time()
    monkeypatch.setattr(ti.time, 'time', lambda: now + ti.TOKEN_TTL + 1)
    response = app.app.test_client().post('/travel/interpret', json={**data, 'mode':'spot',
        'activity_choice':'카페', 'clarification_token':token})
    assert response.status_code == 400


def test_explicit_kind_cannot_be_erased_into_activity_clarification(setup):
    text = '연인이랑 닭갈비 데이트'
    setup[0](unresolved_date(text))
    response = app.app.test_client().post('/travel/interpret', json={**BASE, 'mode':'spot', 'user_text':text})
    assert response.status_code == 503
    assert 'clarification' not in response.json


def test_unresolved_interpretation_cannot_reach_recommendation(setup):
    data, token = clarify_date(setup)
    response = app.app.test_client().post('/recommend/spot', json={**data, 'intent_token':token})
    assert response.status_code == 400
    response = app.app.test_client().post('/recommend/spot', json=data)
    assert response.status_code == 422
    assert response.json['reason'] == 'activity_clarification_required'


@pytest.mark.parametrize('activity,label', ti.CORE_ACTIVITY_LABELS.items())
def test_every_clarification_activity_is_one_visit_with_structured_or_categories(setup, activity, label):
    data, token = clarify_date(setup)
    setup[0](plan([stage(label, ti.SLOT_CATEGORY_MAP[activity])],
                  companion={'value':'연인과', 'quote':'연인이랑'}))
    response = app.app.test_client().post('/travel/interpret', json={**data, 'mode':'spot',
        'activity_choice':activity, 'clarification_token':token})
    assert response.status_code == 200, response.json
    result = response.json['travel_request']
    assert len(result['stages']) == 1
    assert result['source_text'] == data['user_text']
    assert set(result['stages'][0]['category_filters']) == set(ti.SLOT_CATEGORY_MAP[activity])
    # A context-only choice is bound directly; UI punctuation is never reinterpreted.
    assert len(setup[1]) == 1
    assert result['activity_choice'] == activity


def test_context_only_activity_cannot_be_split_by_a_second_model_response(setup):
    # A provider that would split the label is no longer called for this selection.
    data, token = clarify_date(setup)
    setup[0](plan([stage('카페',['카페']), stage('디저트',['디저트'])],
                  companion={'value':'연인과','quote':'연인이랑'}))
    response = app.app.test_client().post('/travel/interpret', json={**data, 'mode':'spot',
        'activity_choice':'카페','clarification_token':token})
    assert response.status_code == 200
    assert len(response.json['travel_request']['stages']) == 1
    assert len(setup[1]) == 1


def test_explicit_multiple_visits_cannot_be_collapsed_by_single_activity_clarification(setup):
    text='연인이랑 두 곳을 방문하는 데이트'
    p=unresolved_date(text)
    p['requested_visit_count']={'value':2,'quote':'두 곳'}
    setup[0](p)
    response=app.app.test_client().post('/travel/interpret',json={**BASE,'mode':'spot','user_text':text})
    assert response.status_code == 422
    assert response.json['reason'] == 'intent_conflict'
    assert 'clarification' not in response.json and 'intent_token' not in response.json
