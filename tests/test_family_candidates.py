"""Child-purpose places must be gated before either engine/model sees them."""
import pandas as pd
import pytest
import app
from family_policy import children_allowed, filter_child_candidates
from place_identity import ensure_ids


@pytest.mark.parametrize('text,tags,allowed', [
    ('', ['친구와'], False), ('', ['연인과', '실내 위주'], False),
    ('', ['카페 투어'], False), ('', ['가족 나들이'], False),
    ('아이와 함께 쉬어요', [], True), ('아이 없이 쉬어요', [], False),
    ('아이와 함께 가고 싶지 않아요', [], False), ('아이 동반 안 할래요', [], False),
    ('아이와 함께', ['친구와'], False), ('아이 없이', ['아이와 함께'], True),
    ('', ['아이와 함께'], True), ('', ['유아/영아 동반'], True),
    ('키즈카페', ['친구와'], True), ('실내놀이터', ['연인과'], True),
    ('키즈카페 말고 카페', [], False), ('실내놀이터는 싫어요', [], False),
    ('', ['아이와 함께', '친구와'], False),
])
def test_child_scope_manual_priority_and_explicit_activity(text, tags, allowed):
    assert children_allowed({'user_text': text, 'persona_tags': tags}) is allowed


def candidates():
    kinds = ['한식']*3 + ['카페']*3 + ['공원']*3 + ['볼링']*3 + ['키즈카페,실내놀이터']*5
    return ensure_ids(pd.DataFrame([dict(가게명=f'장소{i}', 주소=f'충남 천안시 테스트로 {i+1}',
        지역='천안', 카테고리=c, latitude=36.8151+i*.0001, longitude=127.1139,
        방문자수=100000 if '키즈' in c else 1, 블로그수=0, blog_tags='{}') for i, c in enumerate(kinds)]))


@pytest.mark.parametrize('slots', [[], ['음식', '실내 오락', '카페'], ['카페']*3])
def test_legacy_course_gate_precedes_default_activity_or_manual_slots(monkeypatch, slots):
    monkeypatch.setattr(app, 'get_df', lambda _: candidates())
    response = app.app.test_client().post('/recommend/course', json=dict(
        user_lat=36.8151, user_lng=127.1139, region='천안', transport='대중교통',
        persona_tags=['친구와', '실내 위주', '카페 투어'], count=1, slot_types=slots, spot_count=3))
    assert response.status_code == 200, response.json
    assert response.json['metadata']['family_policy']['excluded_count'] == 5
    assert all('키즈' not in p['category'] and '실내놀이터' not in p['category']
               for c in response.json['courses'] for p in c)


def test_child_companion_does_not_change_general_cafe_slot(monkeypatch):
    monkeypatch.setattr(app, 'get_df', lambda _: candidates())
    response = app.app.test_client().post('/recommend/course', json=dict(
        user_lat=36.8151, user_lng=127.1139, region='천안', transport='차',
        persona_tags=['아이와 함께'], count=1, slot_types=['카페']*3, spot_count=3))
    assert response.status_code == 200
    assert response.json['metadata']['family_policy']['child_venues_allowed'] is True
    assert all(p['category'] == '카페' for p in response.json['courses'][0])


def test_structured_child_negative_and_double_negative_are_distinct():
    def p(cats, who=None):
        return {'stages': [{'category_filters': cats}], 'companion': {'value': who} if who else None}
    assert not children_allowed({'user_text': '아이 없이 카페', 'persona_tags': []}, p(['카페'], '아이와 함께'))
    assert not children_allowed({'user_text': '키즈카페 말고 박물관', 'persona_tags': []}, p(['박물관']))
    assert children_allowed({'user_text': '키즈카페 말고는 가지 않을래요', 'persona_tags': []}, p(['키즈카페']))
    assert children_allowed({'user_text': '아이 없이 키즈카페', 'persona_tags': ['친구와']}, p(['키즈카페']))


def test_wrongly_generic_cafe_name_is_gated_without_mutating_source():
    f = candidates().iloc[:1].copy()
    f.loc[f.index[0], '카테고리'] = '카페'
    f.loc[f.index[0], '가게명'] = '까블랑 키즈카페'
    before = f.copy(deep=True)
    filtered, metadata = filter_child_candidates(f, {'persona_tags': ['친구와']})
    assert filtered.empty and metadata['excluded_count'] == 1
    pd.testing.assert_frame_equal(f, before)


def test_explicit_child_venue_is_supported_without_general_cafe_broadening(monkeypatch):
    monkeypatch.setattr(app, 'get_df', lambda _: candidates())
    response = app.app.test_client().post('/recommend/spot', json=dict(
        user_text='실내놀이터', user_lat=36.8151, user_lng=127.1139,
        region='천안', persona_tags=['친구와'], count=2))
    assert response.status_code == 200
    assert all('실내놀이터' in p['category'] for p in response.json['places'])
