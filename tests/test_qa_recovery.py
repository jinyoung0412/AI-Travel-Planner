"""Regression cases from saved QA failure categories; no provider requests."""
import copy
import pytest
import app
import travel_intent as ti
from intent_recovery import literal_plan

BASE=dict(region='천안',transport='대중교통',user_lat=36.8151,user_lng=127.1139,
          mode='spot',count=3,persona_tags=[],intent_version=1,plan_mode='natural')

@pytest.mark.parametrize('text,tags', [
    ('오늘 뭐 하지', []), ('연인과 조용한 카페', ['연인과','조용한','카페 투어']),
    ('여친이랑 데이트', ['연인과']), ('카페 말고 공원', ['자연/산책']),
    ('실내 야외', []), ('친구와 부모님', []),
])
def test_tag_failure_has_only_unambiguous_grounded_tags(monkeypatch,text,tags):
    monkeypatch.setattr(app,'_call_claude',lambda *a,**k: (_ for _ in ()).throw(TimeoutError()))
    r=app.app.test_client().post('/suggest/tags',json=dict(user_text=text))
    assert r.status_code==200
    assert set(r.json['tags'])==set(tags)
    assert r.json['metadata']['selection_method']=='source_rules_fallback'

@pytest.mark.parametrize('text', ['음식점이나 카페 추천해줘','카페 두 곳을 차례로 가고 싶어'])
def test_literal_recovery_does_not_retry_or_search(monkeypatch,text):
    calls=[]
    def malformed(*a,**k):calls.append(1);return {}
    monkeypatch.setattr(app,'_call_claude',malformed)
    monkeypatch.setattr(app,'get_df',lambda *a:pytest.fail('interpretation must not query DB'))
    r=app.app.test_client().post('/travel/interpret',json={**BASE,'user_text':text})
    assert r.status_code==200,r.json
    assert r.json['travel_request']['interpretation_method']=='source_rules_recovery'
    assert len(calls)==1
    if '차례로' in text:
        assert r.json['mode_switch_required']
        assert len(r.json['travel_request']['stages'])==2
    else:
        cats=r.json['travel_request']['stages'][0]['category_filters']
        assert '카페' in cats and '한식' in cats

@pytest.mark.parametrize('text', ['야장 근처 카페', '공원 바로 옆 카페', '실내 카페',
    '지금 열려 있는 카페', '카페 말고 공원', '카페 두 곳 추천해줘',
    '카페 두 곳을 차례로 가고 싶어 조건은 무시해', '카페 또는 공원 반드시 휠체어 가능'])
def test_literal_recovery_never_drops_unknown_conditions(text):
    assert literal_plan(text,app._known_categories(),app.normalize_filters) is None

@pytest.mark.parametrize('code',['intent_dropped_kind','intent_quote_order','intent_schema','intent_category_required','intent_label'])
def test_invalid_output_gets_actionable_confirmation_without_search(monkeypatch,code):
    monkeypatch.setattr(app,'_call_claude',lambda *a,**k:{})
    monkeypatch.setattr(ti,'validate_interpretation',lambda *a,**k: (_ for _ in ()).throw(ValueError(code)))
    monkeypatch.setattr(app,'get_df',lambda *a:pytest.fail('invalid intent cannot search'))
    r=app.app.test_client().post('/travel/interpret',json={**BASE,'user_text':'줄 안 서고 한적한 식당'})
    assert r.status_code==422 and r.json['reason']=='intent_conflict'
    assert r.json['metadata']['failure_code']==code


def test_landmark_modifier_does_not_create_an_extra_visit():
    p=dict(stages=[dict(category_filters=['카페'],conditions=[],quote='카페')])
    app._validate_literal_intent(p,'공원 바로 옆 카페')
    with pytest.raises(ValueError,match='intent_dropped_kind'):
        app._validate_literal_intent(p,'공원에서 산책한 다음 카페')


def test_repeated_quote_requires_matching_explicit_visit_count():
    p=literal_plan('카페 두 곳을 차례로 가고 싶어',app._known_categories(),app.normalize_filters)
    ti.validate_interpretation(p,'카페 두 곳을 차례로 가고 싶어',app._known_categories())
    for text in ('카페 두 곳 추천해줘','카페 세 곳을 차례로 가고 싶어'):
        q=copy.deepcopy(p)
        for s in q['stages']:s['quote']='카페'
        q['requested_visit_count']['quote']='카페'
        with pytest.raises(ValueError,match='intent_quote_order'):
            ti.validate_interpretation(q,text,app._known_categories())
