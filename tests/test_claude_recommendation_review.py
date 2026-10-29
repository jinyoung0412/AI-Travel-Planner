"""Claude final F1/F3/F4: common wording and lossless manual activity binding."""
import copy
import json

import pytest
import app
import travel_intent as ti
from api_request import parse_recommendation
from intent_context import context_only
from test_feedback_recommendation import ORIGIN, frame


def interpret_model(monkeypatch, plan):
    calls=[]
    def model(system,message,**kwargs):
        calls.append((system,json.loads(message)))
        if system==ti.SELECTION_SYSTEM:raise TimeoutError()
        return copy.deepcopy(plan)
    monkeypatch.setattr(app,'_call_claude',model)
    monkeypatch.setattr(app,'get_df',lambda _:frame(('파스타','한식','공원','카페','볼링')))
    return app.app.test_client(),calls


def plan(stages=(), text=''):
    return dict(schema_version=1,companion=None,stages=list(stages),exclusions=[],
        ambiguities=[] if stages else [dict(quote=text,reason='활동 선택이 필요합니다')],
        unsupported=[],requested_visit_count=None)


def stage(quote, filters):
    return dict(id='s1',activity=quote,quote=quote,category_filters=filters,conditions=[],preferences=[])


@pytest.mark.parametrize('companion',['여자 친구','남자   친구','여친','남친','여자\t 친구'])
@pytest.mark.parametrize('ending',['',' 하고싶어',' 코스 짜줘',' 알려줘',' 하고 싶어요',' 추천해 줘'])
def test_f1_common_context_forms_keep_manual_order_and_direct_spot_choice(monkeypatch, companion, ending):
    text=f'{companion}랑 100일 기념 데이트{ending}'
    assert context_only(text)
    client,calls=interpret_model(monkeypatch,plan(text=text))
    body={**ORIGIN,'user_text':text,'mode':'course','plan_mode':'manual','spot_count':3,
          'slot_types':['음식','자연·산책','카페']}
    reviewed=client.post('/travel/interpret',json=body)
    assert reviewed.status_code==200,reviewed.json
    assert not reviewed.json['clarification_required']
    assert [s['activity'] for s in reviewed.json['travel_request']['stages']]==body['slot_types']
    body={**ORIGIN,'user_text':text,'mode':'spot'}
    original=client.post('/travel/interpret',json=body).json
    before=len(calls)
    chosen=client.post('/travel/interpret',json={**body,'activity_choice':'체험',
        'clarification_token':original['clarification']['token']})
    assert chosen.status_code==200,chosen.json
    assert len(calls)==before
    assert chosen.json['travel_request']['stages'][0]['category_filters']==ti.SLOT_CATEGORY_MAP['체험']


@pytest.mark.parametrize('companion',['여자 친구','여자   친구','남자\t 친구','여친','남친'])
def test_f4_couple_variants_ground_couple_and_never_infer_friend(monkeypatch,companion):
    monkeypatch.setattr(app,'_call_claude',lambda *a,**k:{'tags':['친구와','연인과','기념일','실내 위주','감성적인']})
    result=app.app.test_client().post('/suggest/tags',json={'user_text':f'{companion}랑 100일 기념 데이트'})
    assert result.json['tags']==['연인과','기념일']


def test_f4_real_friend_mention_beside_couple_is_not_erased(monkeypatch):
    monkeypatch.setattr(app,'_call_claude',lambda *a,**k:{'tags':['친구와','연인과']})
    result=app.app.test_client().post('/suggest/tags',json={'user_text':'여자   친구와 친구들이 함께 가요'})
    assert result.json['tags']==['친구와','연인과']


@pytest.mark.parametrize('constraint',['실내','야외','카페 말고','주차 필수','휠체어 접근 필수',
    '영업 중','100명 예약 필수','엘리베이터 필수','알레르기 대응 식사','반드시 조용한'])
def test_f1_unknown_or_real_constraints_are_not_discarded_with_casual_endings(constraint):
    assert not context_only(f'여친이랑 100일 데이트 {constraint} 코스 짜줘')


def test_f3_incompatible_literal_activity_is_actionable_conflict(monkeypatch):
    text='여자친구랑 볼링 치고 100일 기념'
    client,_=interpret_model(monkeypatch,plan([stage('볼링',['볼링'])]))
    response=client.post('/travel/interpret',json={**ORIGIN,'user_text':text,'mode':'course',
        'plan_mode':'manual','spot_count':3,'slot_types':['음식','자연·산책','카페']})
    assert response.status_code==422,response.json
    assert response.json['reason']=='intent_conflict'
    assert '볼링' in response.json['error']
    assert '문장' in response.json['error']


@pytest.mark.parametrize('kind',['파스타','닭갈비','샐러드'])
def test_f3_compatible_specific_food_is_preserved_under_food_activity(monkeypatch,kind):
    client,_=interpret_model(monkeypatch,plan([stage(kind,[kind])]))
    body={**ORIGIN,'user_text':kind,'mode':'course','plan_mode':'manual','spot_count':3,
        'slot_types':['음식','자연·산책','카페']}
    response=client.post('/travel/interpret',json=body)
    assert response.status_code==200,response.json
    assert response.json['travel_request']['stages'][0]['category_filters']==[kind]
    assert response.json['travel_request']['stages'][1]['category_filters']==ti.SLOT_CATEGORY_MAP['자연·산책']
    if kind=='파스타':
        result=client.post('/recommend/course',json={**body,'intent_token':response.json['intent_token']})
        assert result.status_code==200,result.json
        assert all(c[0]['category']=='파스타' for c in result.json['courses'])


def test_f3_specific_play_kind_is_kept_when_matching_activity_is_available(monkeypatch):
    client,_=interpret_model(monkeypatch,plan([stage('볼링',['볼링'])]))
    response=client.post('/travel/interpret',json={**ORIGIN,'user_text':'볼링','mode':'course',
        'plan_mode':'manual','spot_count':3,'slot_types':['음식','실내 오락','카페']})
    assert response.status_code==200,response.json
    assert response.json['travel_request']['stages'][1]['category_filters']==['볼링']


@pytest.mark.parametrize('text,expected',[
    ('여자   친구 말고 친구와 데이트',['친구와']),
    ('친구 말고 남친이랑 데이트',['연인과']),
])
def test_f4_couple_normalization_keeps_explicit_negation(monkeypatch,text,expected):
    monkeypatch.setattr(app,'_call_claude',lambda *a,**k:{'tags':['친구와','연인과']})
    result=app.app.test_client().post('/suggest/tags',json={'user_text':text})
    assert result.json['tags']==expected


def test_f3_specific_meal_parent_binding_keeps_mandatory_condition(monkeypatch):
    s=stage('실내 파스타',['파스타'])
    s['conditions']=[dict(field='indoor',value=True,required=True,quote='실내')]
    client,_=interpret_model(monkeypatch,plan([s]))
    body={**ORIGIN,'user_text':'실내 파스타','mode':'course','plan_mode':'manual','spot_count':3,
        'slot_types':['음식','자연·산책','카페'],'persona_tags':[]}
    reviewed=client.post('/travel/interpret',json=body)
    assert reviewed.status_code==200,reviewed.json
    first=reviewed.json['travel_request']['stages'][0]
    assert first['category_filters']==['파스타']
    assert first['conditions'][0]['required'] is True
    result=client.post('/recommend/course',json={**body,'intent_token':reviewed.json['intent_token']})
    assert result.status_code==422 and result.json['reason']=='unverified_conditions'


def test_f3_meal_activity_relation_does_not_accept_purpose_cafes_or_drinking():
    from category_policy import filters_for_activity
    for kind in ('보드카페','키즈카페','맥주','호프','바(Bar)','주스','차(음료)'):
        assert not filters_for_activity([kind],ti.SLOT_CATEGORY_MAP['음식'])


@pytest.mark.parametrize('filters,text',[(['카페','공원'],'카페나 공원 한 곳'),
    (['파스타','맥주'],'파스타나 맥주 한 곳')])
def test_f3_manual_binding_cannot_silently_drop_cross_activity_or_alternatives(monkeypatch,filters,text):
    client,_=interpret_model(monkeypatch,plan([stage(text,filters)]))
    response=client.post('/travel/interpret',json={**ORIGIN,'user_text':text,'mode':'course',
        'plan_mode':'manual','spot_count':3,'slot_types':['음식','자연·산책','카페']})
    assert response.status_code==422,response.json
    assert response.json['reason']=='intent_conflict'
    assert all(kind in response.json['error'] for kind in filters)
    assert '문장' in response.json['error'] and '방문 순서' in response.json['error']


@pytest.mark.parametrize('filters,slot',[
    (ti.SLOT_CATEGORY_MAP['음식'],'음식'),
    (ti.SLOT_CATEGORY_MAP['카페'],'카페'),
    (['파스타','샐러드'],'음식'),(['볼링','노래방'],'실내 오락'),
])
def test_f3_full_alternative_sets_remain_intact_in_compatible_activity(filters,slot):
    p=plan([stage('선택한 활동',filters)])
    p['source_text']='선택한 활동'
    slots=['음식',slot,'카페']
    body=parse_recommendation({**ORIGIN,'plan_mode':'manual','spot_count':3,'slot_types':slots},True)
    applied=ti.apply_controls(p,body,'course')
    matched=next(s for s in applied['stages'] if s['category_filters']==filters)
    assert matched['category_filters']==filters


def test_f1_casual_go_want_phrase_without_occasion_keeps_manual_course(monkeypatch):
    text='여친이랑 데이트 가고 싶어'
    assert context_only(text)
    client,_=interpret_model(monkeypatch,plan(text=text))
    response=client.post('/travel/interpret',json={**ORIGIN,'user_text':text,'mode':'course',
        'plan_mode':'manual','spot_count':3,'slot_types':['음식','자연·산책','카페']})
    assert response.status_code==200,response.json
    assert response.json['clarification_required'] is False


@pytest.mark.parametrize('companion',['여자 친구들','여자   친구들','남자 친구들','남자\t친구 들'])
def test_f4_plural_gendered_friends_are_not_a_couple_tag(monkeypatch,companion):
    monkeypatch.setattr(app,'_call_claude',lambda *a,**k:{'tags':['친구와','연인과','카페 투어']})
    result=app.app.test_client().post('/suggest/tags',json={'user_text':companion+'이랑 카페 투어'})
    assert result.json['tags']==['친구와','카페 투어']
