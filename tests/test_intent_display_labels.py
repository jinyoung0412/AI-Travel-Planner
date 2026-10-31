"""Verbose presentation text must not erase or invalidate grounded requirements."""
import copy
import pytest
import app
import travel_intent as ti

TEXT='부모님 모시고 야장 가고 싶어 줄 안 서고'

def response():
    return dict(schema_version=1,companion=dict(value='부모님 모시고',quote='부모님 모시고'),
        stages=[dict(id='s1',activity='야외 좌석에서 부모님과 식사하는 활동 설명 '*12,quote='야장',
            category_filters=['맥주','호프'],conditions=[dict(field='outdoor_seating',value=True,required=True,quote='야장')],preferences=[])],
        exclusions=[],ambiguities=[],unsupported=[dict(quote='줄 안 서고',reason='실시간 대기 상태를 확인할 수 없습니다. '*12)],requested_visit_count=None)


def test_verbose_labels_are_bounded_without_losing_unverified_requirements():
    raw=response();before=copy.deepcopy(raw)
    plan=ti.validate_interpretation(raw,TEXT,app._known_categories())
    app._validate_literal_intent(plan,TEXT)
    assert len(plan['stages'][0]['activity'])==80
    assert len(plan['unsupported'][0]['reason'])==80
    assert plan['stages'][0]['category_filters']==['맥주','호프']
    assert plan['stages'][0]['conditions'][0]['required'] is True
    assert plan['stages'][0]['conditions'][0]['quote']=='야장'
    assert plan['unsupported'][0]['quote']=='줄 안 서고'
    assert raw==before

@pytest.mark.parametrize('value',[None,4,[],{},'', '  ', 'x'*2049])
def test_malformed_or_absurd_labels_are_still_rejected(value):
    raw=response();raw['stages'][0]['activity']=value
    with pytest.raises(ValueError,match='intent_label'):
        ti.validate_interpretation(raw,TEXT,app._known_categories())

@pytest.mark.parametrize('mutation,code',[
    (lambda p:p['stages'][0].update(category_filters=[]),'intent_category_required'),
    (lambda p:p['stages'][0].update(quote='없는 근거'),'intent_quote'),
    (lambda p:p['stages'][0]['conditions'][0].update(value='true'),'intent_condition'),
    (lambda p:p['stages'][0]['conditions'][0].update(quote='없는 조건'),'intent_quote'),
    (lambda p:p['unsupported'][0].update(reason=None),'intent_label'),
])
def test_display_normalization_does_not_relax_data_validation(mutation,code):
    raw=response();mutation(raw)
    with pytest.raises(ValueError,match=code):ti.validate_interpretation(raw,TEXT,app._known_categories())


def test_waiting_negation_is_not_an_exclusion_of_restaurants():
    raw=dict(schema_version=1,companion=None,stages=[dict(id='s1',activity='식사',quote='식당',category_filters=['음식점'],conditions=[],preferences=[])],
        exclusions=[dict(category_filters=['음식점'],quote='줄 안 서고',reason='대기 없는 곳')],ambiguities=[],unsupported=[],requested_visit_count=None)
    with pytest.raises(ValueError,match='intent_schema'):
        ti.validate_interpretation(raw,'줄 안 서고 한적한 식당',app._known_categories())


def test_parent_example_does_not_invent_accessibility_or_cuisine_constraints(monkeypatch):
    text='부모님 모시고 식사하고 싶어'
    raw=dict(schema_version=1,companion=dict(value='부모님 모시고',quote='부모님 모시고'),stages=[dict(id='s1',activity='부모님과 함께 식사 '*20,quote='식사',category_filters=['음식점'],conditions=[],preferences=[])],
             exclusions=[],ambiguities=[],unsupported=[],requested_visit_count=None)
    monkeypatch.setattr(app,'_call_claude',lambda *a,**kw:copy.deepcopy(raw))
    r=app.app.test_client().post('/travel/interpret',json=dict(mode='spot',region='천안',transport='대중교통',user_lat=36.8151,user_lng=127.1139,count=3,persona_tags=[],intent_version=1,plan_mode='natural',user_text=text))
    assert r.status_code==200
    p=r.json['travel_request']
    assert p['companion']['value']=='부모님 모시고'
    assert not p['stages'][0]['conditions'] and not p['ambiguities']
    assert '중식' in p['stages'][0]['category_filters'] and '한식' in p['stages'][0]['category_filters']
