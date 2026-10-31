import copy
import pandas as pd
import pytest
import app
import travel_intent as ti
from place_identity import ensure_ids

BASE=dict(mode='course',region='천안',transport='대중교통',user_lat=36.8100,user_lng=127.1463,count=1,spot_count=3,slot_types=['맥주·호프','자연·산책','카페'],persona_tags=['연인과'],seed=42,randomize=False,intent_version=1,plan_mode='manual',user_text='기념일에 야장 가고 싶어')
RAW=dict(schema_version=1,companion=None,stages=[dict(id='s1',activity='야장',quote='야장',category_filters=['맥주','호프'],conditions=[dict(field='outdoor_seating',value=True,required=True,quote='야장')],preferences=[])],exclusions=[],ambiguities=[],unsupported=[],requested_visit_count=None)

def test_manual_beer_slot_preserves_source_and_requires_confirmation(monkeypatch):
    kinds=['맥주,호프','호프','공원','산책로','카페','한식','와인']
    frame=ensure_ids(pd.DataFrame([dict(가게명=f'장소{i}',주소=f'충남 천안시 테스트로 {i}',지역='천안',카테고리=k,latitude=36.8101+i*.00001,longitude=127.1463,방문자수=100,블로그수=0,blog_tags='{}') for i,k in enumerate(kinds)]))
    monkeypatch.setattr(app,'get_df',lambda _:frame.copy())
    def model(system,*a,**kw):
        if system==ti.SELECTION_SYSTEM:raise TimeoutError()
        return copy.deepcopy(RAW)
    monkeypatch.setattr(app,'_call_claude',model)
    client=app.app.test_client();r=client.post('/travel/interpret',json=BASE)
    assert r.status_code==200,r.json
    stage=r.json['travel_request']['stages'][0]
    assert stage['category_filters']==['맥주','호프'] and stage['conditions'][0]['required']
    body={**BASE,'intent_token':r.json['intent_token']}
    strict=client.post('/recommend/course',json=body)
    assert strict.status_code==422 and strict.json['reason']=='unverified_conditions'
    accepted=client.post('/recommend/course',json={**body,'accept_unverified':True})
    assert accepted.status_code==200,accepted.json
    assert accepted.json['courses'][0][0]['category'] in ('맥주,호프','호프')
    assert accepted.json['metadata']['intent_status']=='unverified_alternative'
    assert accepted.json['courses'][0][0]['travel_explanation']['unverified_conditions']==['야외 좌석']

def test_normal_meal_slot_remains_a_meal_and_points_to_selectable_beer_activity(monkeypatch):
    monkeypatch.setattr(app,'_call_claude',lambda *a,**kw:copy.deepcopy(RAW))
    r=app.app.test_client().post('/travel/interpret',json={**BASE,'slot_types':['음식','자연·산책','카페']})
    assert r.status_code==422 and '맥주·호프' in r.json['error']
    assert not set(app.SLOT_CATEGORY_MAP['음식']) & {'맥주','호프'}
