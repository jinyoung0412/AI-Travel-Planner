"""Six visible activities share purpose filters across manual and AI paths."""
import hashlib
from pathlib import Path
import re

import pandas as pd
import pytest

import app
import travel_intent as intent
from api_request import parse_recommendation
from category_policy import category_matches
from place_identity import ensure_ids
from recommendation_ai import fixed_categories
from recommender.constants import (CORE_ACTIVITY_LABELS, CORE_ACTIVITY_TAG_SLOTS,
    DEFAULT_COURSE_SLOTS, SLOT_CATEGORY_MAP, CAFE_CATS)
from runtime_llm import PERSONA_TAG_GROUPS


ORIGIN = dict(user_lat=36.8151, user_lng=127.1139, transport='대중교통', count=1,
              persona_tags=['친구와'], seed=0)


def records():
    kinds = ['한식', '공원', '카페,디저트', '베이커리', '볼링장', 'PC방',
             '보드카페', '방탈출카페', '키즈카페,실내놀이터', '라이브카페',
             '슬라임카페', '등산,아웃도어', '산', '등산로', '스포츠의류', '공방',
             '체험,홍보관', '관람,체험', '국가유산청', '박물관']
    return ensure_ids(pd.DataFrame([dict(가게명=f'시설{i}', 주소=f'충남 천안시 중앙로 {i+1}',
        카테고리=c, 지역='천안', latitude=36.8151+i*.00001, longitude=127.1139,
        방문자수=9999 if c in ('카페,디저트','등산,아웃도어') else i,
        블로그수=0, blog_tags='{}', blog_tag_status='legacy_unverified')
        for i,c in enumerate(kinds)]))


def test_six_ui_and_server_choices_keep_stable_wire_values():
    expected = ['식사','카페·디저트','산책·자연','전시·문화관람','체험·만들기','실내 놀거리']
    assert list(CORE_ACTIVITY_LABELS.values()) == expected
    assert PERSONA_TAG_GROUPS['어떤 활동'] == list(CORE_ACTIVITY_TAG_SLOTS)
    dart=(Path(__file__).resolve().parents[1]/'android_app/lib/input_options.dart').read_text()
    styles=dart.split('const _kSlotStyles = {',1)[1].split('};',1)[0]
    labels=dart.split('const _kSlotLabels = {',1)[1].split('};',1)[0]
    tag_choices=re.search(r"'어떤 활동':\s*\[([^\]]+)\]",dart).group(1)
    assert re.findall(r"'([^']+)': _SlotStyle",styles) == list(CORE_ACTIVITY_LABELS)
    assert dict(re.findall(r"'([^']+)': '([^']+)'",labels)) == CORE_ACTIVITY_LABELS
    assert re.findall(r"'([^']+)'",tag_choices) == list(CORE_ACTIVITY_TAG_SLOTS)
    assert fixed_categories(3) == [SLOT_CATEGORY_MAP[s] for s in DEFAULT_COURSE_SLOTS[:3]]
    for tag,slot in CORE_ACTIVITY_TAG_SLOTS.items():
        assert app.derive_category_from_tags([tag]) == SLOT_CATEGORY_MAP[slot]
    # Removed buttons still accept saved/older request values.
    for old in ('쇼핑','관광지','등산'):
        request=parse_recommendation({**ORIGIN,'spot_count':3,'slot_types':['음식',old,'카페']},True)
        assert request['slot_types'][1] == old


@pytest.mark.parametrize('category', ['볼링장','노래방','코인노래연습장','PC방','피시방',
    '오락실','보드카페','방탈출카페','음식점>보드게임카페'])
def test_indoor_play_has_concrete_game_purpose(category):
    assert category_matches(category,SLOT_CATEGORY_MAP['실내 오락'])


@pytest.mark.parametrize('category,name', [
    ('카페','일반 카페'),('카페,디저트','PC 분위기 카페'),('베이커리','볼링라운지'),
    ('펜션','익스펜션PC방'),('노래,발성,보컬교육','보컬학원'),
    ('스포츠,오락','테니스 시설'),('오락용품판매점','게임 상점'),
    ('카페,오락','일반 카페'),
    ('라이브카페','라이브카페'),('슬라임카페','슬라임카페'),
])
def test_indoor_play_does_not_use_cafes_or_name_only_guesses(category,name):
    assert not category_matches(category,SLOT_CATEGORY_MAP['실내 오락'],name)


@pytest.mark.parametrize('category', ['등산,아웃도어','쇼핑>등산,아웃도어',
    '스포츠의류','스포츠용품>등산용품점','등산용품','골프용품판매점'])
def test_outdoor_retail_is_not_a_hike_or_sports_experience(category):
    for cats in (SLOT_CATEGORY_MAP['등산'],app.derive_category_from_tags(['스포츠/레저'])):
        assert not category_matches(category,cats)


@pytest.mark.parametrize('category', ['산','등산로','트레킹코스'])
def test_hiking_places_are_kept_without_inventing_route_facts(category):
    assert category_matches(category,SLOT_CATEGORY_MAP['등산'])


def test_hiking_activity_alias_keeps_mountains_but_a_trail_request_stays_specific():
    assert app.extract_spot_category('등산') == SLOT_CATEGORY_MAP['등산']
    assert app.extract_spot_category('등산로') == ['등산로']


def test_six_filters_respect_viewing_and_craft_purpose():
    assert category_matches('국가유산',SLOT_CATEGORY_MAP['문화·역사'])
    assert not category_matches('국가유산청',SLOT_CATEGORY_MAP['문화·역사'])
    for category in ('공방','관람,체험','체험마을'):
        assert category_matches(category,SLOT_CATEGORY_MAP['체험'])
    for category in ('공방용품점','체험,홍보관','주택전시관'):
        assert not category_matches(category,SLOT_CATEGORY_MAP['체험'])
    assert not app.derive_category_from_tags(['사진 명소','멋진 야경','야경'])


def test_broad_activity_alias_is_an_alternative_but_specific_kind_is_required():
    def p(cats):
        return {'stages':[{'category_filters':cats,'conditions':[]}]}
    app._validate_literal_intent(p(['한식']), '식사')
    app._validate_literal_intent(p(['볼링']), '실내 놀거리')
    app._validate_literal_intent(p(['맥주','호프']), '맥주 맛집')
    with pytest.raises(ValueError):
        app._validate_literal_intent(p(['카페']), '실내 놀거리')
    with pytest.raises(ValueError):
        app._validate_literal_intent(p(['카페']), '볼링')


def test_manual_spot_and_course_use_play_purpose_before_ranking(monkeypatch):
    monkeypatch.setattr(app,'get_df',lambda _:records())
    client=app.app.test_client()
    spot=client.post('/recommend/spot',json={**ORIGIN,'count':20,
        'persona_tags':['친구와','노래방/실내 오락']})
    assert spot.status_code==200,spot.json
    assert {p['category'] for p in spot.json['places']}=={'볼링장','PC방','보드카페','방탈출카페'}
    course=client.post('/recommend/course',json={**ORIGIN,'spot_count':3,
        'slot_types':['음식','실내 오락','카페']})
    assert course.status_code==200,course.json
    places=course.json['courses'][0]
    assert places[1]['category'] in {'볼링장','PC방','보드카페','방탈출카페'}
    assert category_matches(places[2]['category'],CAFE_CATS)
    craft=client.post('/recommend/course',json={**ORIGIN,'spot_count':3,
        'slot_types':['음식','체험','카페']})
    assert craft.status_code==200,craft.json
    assert craft.json['courses'][0][1]['category'] in {'공방','관람,체험'}


@pytest.mark.parametrize('text,filters,forbidden', [
    ('등산',['등산'],{'등산,아웃도어','스포츠의류'}),
    ('실내 놀거리',SLOT_CATEGORY_MAP['실내 오락'],{'카페,디저트','베이커리','라이브카페','슬라임카페','키즈카페,실내놀이터'}),
])
def test_natural_plan_candidate_pool_and_fallback_obey_same_filters(monkeypatch,text,filters,forbidden):
    monkeypatch.setattr(app,'get_df',lambda _:records())
    plan=dict(schema_version=1,companion=None,stages=[dict(id='s1',activity=text,quote=text,
        category_filters=filters,conditions=[],preferences=[])],exclusions=[],ambiguities=[],unsupported=[],requested_visit_count=None)
    seen=[]
    def model(system,message,**options):
        if system==intent.SELECTION_SYSTEM:
            import json
            seen.extend(json.loads(message)['candidates'][0])
            raise TimeoutError()
        return plan
    monkeypatch.setattr(app,'_call_claude',model)
    response=app.app.test_client().post('/recommend/spot',json={**ORIGIN,'user_text':text,
        'intent_version':1,'plan_mode':'natural'})
    assert response.status_code==200,response.json
    assert seen and not {p['category'] for p in seen}.intersection(forbidden)
    assert not {p['category'] for p in response.json['places']}.intersection(forbidden)
    assert response.json['metadata']['constraints_relaxed']==[]


def test_real_db_eight_outdoor_shops_are_filtered_without_db_mutation():
    path=Path(app.__file__).with_name('places.db')
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    frame=app.get_df()
    retailers=frame[frame['카테고리'].eq('등산,아웃도어')]
    assert len(retailers)==8
    hiking=app.filter_keywords(frame,SLOT_CATEGORY_MAP['등산'],[])
    assert not hiking.empty and not set(retailers.place_id).intersection(hiking.place_id)
    play=app.filter_keywords(frame,SLOT_CATEGORY_MAP['실내 오락'],[])
    ordinary=frame[frame['카테고리'].isin(['카페','카페,디저트','베이커리'])]
    # Cafe rows with a complete board/escape-room purpose in the source name are
    # intentionally classified by that purpose; ordinary cafes never backfill.
    from category_policy import specialized_cafe_kind
    ordinary=ordinary[~ordinary.apply(lambda r:bool(specialized_cafe_kind(r['카테고리'],r['가게명'])),axis=1)]
    assert not set(ordinary.place_id).intersection(play.place_id)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
