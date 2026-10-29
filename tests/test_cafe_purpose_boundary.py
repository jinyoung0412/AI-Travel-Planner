"""Generic cafe stops exclude explicit amusement purposes, not inferred noise."""
import hashlib
from pathlib import Path

import pandas as pd
import pytest

import app
from category_policy import category_matches, specialized_cafe_kind
from place_identity import ensure_ids
from place_quality import filter_coordinate_candidates
from recommender.constants import CAFE_CATS, SPECIALIZED_CAFE_CATS
from recommender.diversity import select_diverse_spots


ORIGIN = {'user_lat': 36.8082, 'user_lng': 127.1506, 'transport': '대중교통'}
TEXT = '친구와 조용한 카페에서 쉬고 싶어요'
# Root's one actual /suggest/tags request returned these. Tests never call AI.
ACTUAL_TAGS = ['친구와', '조용한', '힐링/여유', '실내 위주', '카페 투어']
DB_SHA = '6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be'


def places():
    kinds = [*SPECIALIZED_CAFE_CATS, '카페,디저트', '카페', '한식', '공원']
    return ensure_ids(pd.DataFrame([{
        '가게명': f'테스트{i}', '주소': f'충남 천안시 중앙로 {i + 10}',
        '카테고리': kind, 'latitude': 36.8083 + i * .0001, 'longitude': 127.1507,
        '방문자수': 100000 - i * 10000, '블로그수': 0,
        'blog_tags': '{}', 'blog_tag_status': 'legacy_unverified',
    } for i, kind in enumerate(kinds)]))


@pytest.mark.parametrize('kind', SPECIALIZED_CAFE_CATS)
def test_purpose_kind_is_not_generic_cafe_but_explicitly_selectable(kind):
    for generic in CAFE_CATS:
        assert not category_matches(f'{kind},카페,디저트', [generic])
    assert category_matches(kind, [kind])
    assert app.extract_spot_category(kind) == [kind]
    assert app.extract_spot_category(kind[:-2] + ' 카페') == [kind]


@pytest.mark.parametrize('text', ['보드게임카페', '보드게임 카페', '보드 게임 카페', '보드카페'])
def test_board_alias_is_longest_mention_and_valid_model_category(monkeypatch, text):
    assert app.extract_spot_category(text) == ['보드카페']
    assert len(app._category_mentions(text)) == 1
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': [text]})
    assert app.extract_spot_category('보드게임을 하고 싶어요') == ['보드카페']


@pytest.mark.parametrize('kind', ['카페', '카페,디저트', '베이커리', '북카페', '갤러리카페',
                                  '브런치카페', '떡카페', '플라워카페', '한방카페',
                                  '테마카페', '고양이카페', '사주카페'])
def test_food_reading_theme_and_other_cafes_are_preserved_without_noise_claim(kind):
    assert specialized_cafe_kind(kind) is None
    assert category_matches(kind, CAFE_CATS)


@pytest.mark.parametrize('name', ['레드박스 보드게임카페', '새로운 보드 게임 카페', '퍼스트라이브카페'])
def test_clear_name_evidence_blocks_misclassified_cafe_and_allows_explicit_purpose(name):
    kind = specialized_cafe_kind('카페,디저트', name)
    assert kind in ('보드카페', '라이브카페')
    assert not category_matches('카페,디저트', CAFE_CATS, name)
    assert category_matches('카페,디저트', [kind], name)
    assert specialized_cafe_kind('한식', name) is None


@pytest.mark.parametrize('name', ['브레드보드 본점', '보드워크 카페', '라이브러리 카페',
                                  '게임 없는 카페', '보드게임 없는 카페', '카페 라이브러리'])
def test_unrelated_words_are_not_purpose_evidence(name):
    assert specialized_cafe_kind('카페,디저트', name) is None
    assert category_matches('카페,디저트', CAFE_CATS, name)


@pytest.mark.parametrize('text,expected,banned', [
    ('보드게임카페 말고 카페', ['카페'], ['보드카페']),
    ('카페 말고 보드게임카페', ['보드카페'], ['카페']),
])
def test_negative_category_scope_uses_same_specific_domain(monkeypatch, text, expected, banned):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': expected})
    assert app.excluded_categories(text) == banned
    assert app.extract_spot_category(text) == expected
    p = places()
    p.loc[5, '가게명'] = '일반분류 보드게임카페'
    available = app.filter_excluded_categories(app.filter_keywords(p, expected, []), banned)
    assert not available.empty
    assert all(category_matches(r['카테고리'], expected, r['가게명'])
               for r in available.to_dict('records'))


def test_specialized_landmark_is_not_an_explicit_specialized_request():
    assert app.extract_spot_category('보드게임카페 근처 카페') == ['카페']
    assert app.extract_spot_category('카페 근처 보드게임카페') == ['보드카페']


@pytest.mark.parametrize('text', [TEXT, ''])
def test_original_sentence_and_manual_tags_reject_amusement_without_claiming_quiet(monkeypatch, text):
    p = places()
    p.loc[5, '가게명'] = '일반분류 보드게임카페'
    monkeypatch.setattr(app, 'get_df', lambda _: p)
    response = app.app.test_client().post('/recommend/spot', json={**ORIGIN, 'count': 5,
        'user_text': text, 'persona_tags': ACTUAL_TAGS})
    assert response.status_code == 200
    assert [r['place_id'] for r in response.json['places']] == [p.iloc[6]['place_id']]
    metadata = response.json['metadata']
    assert metadata['returned_count'] == 1 and metadata['reason'] == 'insufficient_candidates'
    assert metadata['verified_tag_candidate_count'] == 0
    assert metadata['preference_evidence'] == 'unavailable'
    assert '취향 일치 근거는 없습니다' in metadata['preference_limitation']
    assert metadata['constraints_relaxed'] == []
    assert p['blog_tags'].eq('{}').all()


def test_manual_indoor_activity_and_explicit_board_request_remain_available(monkeypatch):
    p = places()
    monkeypatch.setattr(app, 'get_df', lambda _: p)
    client = app.app.test_client()
    indoor = client.post('/recommend/spot', json={**ORIGIN, 'count': 5,
        'persona_tags': ['노래방/실내 오락']})
    assert indoor.status_code == 200
    assert {r['category'] for r in indoor.json['places']} == {'보드카페', '방탈출카페'}
    assert indoor.json['metadata']['family_policy']['child_venues_allowed'] is False
    board = client.post('/recommend/spot', json={**ORIGIN, 'count': 5,
        'user_text': '조용한 보드게임카페', 'persona_tags': ACTUAL_TAGS})
    assert board.status_code == 200
    assert [r['category'] for r in board.json['places']] == ['보드카페']


def test_course_cafe_slot_uses_same_boundary_and_indoor_slot_is_preserved(monkeypatch):
    p = places()
    p.loc[5, '가게명'] = '일반분류 보드게임카페'
    monkeypatch.setattr(app, 'get_df', lambda _: p)
    for last in ['카페', '실내 오락']:
        response = app.app.test_client().post('/recommend/course', json={**ORIGIN,
            'slot_types': ['음식', '자연·산책', last], 'spot_count': 3, 'count': 1,
            'persona_tags': ACTUAL_TAGS})
        assert response.status_code == 200
        chosen = response.json['courses'][0][-1]
        if last == '카페':
            assert chosen['place_id'] == p.iloc[6]['place_id']
        else:
            assert chosen['category'] in {'보드카페', '방탈출카페'}
        assert response.json['metadata']['constraints_relaxed'] == []


@pytest.mark.parametrize('transport,old_text,new_text,old_manual,new_manual', [
    ('차', 1516, 1487, 1819, 1790), ('대중교통', 802, 782, 977, 957)])
def test_frozen_db_exact_original_actual_tags_and_manual_cafe_boundary(
        monkeypatch, transport, old_text, new_text, old_manual, new_manual):
    path = Path(app.__file__).with_name('places.db')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == DB_SHA
    monkeypatch.setattr(app, 'DB_PATH', str(path))
    p = app.get_df()
    eligible, _ = filter_coordinate_candidates(p)
    radius = app.filter_radius(eligible, ORIGIN['user_lat'], ORIGIN['user_lng'], transport)
    monkeypatch.setattr(app, 'get_df', lambda _: p)
    for text, cats, old_count, new_count in [(TEXT, ['카페'], old_text, new_text),
                                          ('', ['카페', '베이커리'], old_manual, new_manual)]:
        # Frozen previous matcher, to show the intentional candidate delta.
        old = radius[radius['카테고리'].map(lambda c: any(
            term in c and not (term == '카페' and '키즈카페' in c) for term in cats))]
        new = app.filter_keywords(radius, cats, [])
        assert (len(old), len(new)) == (old_count, new_count)
        removed = old.loc[~old['place_id'].isin(new['place_id'])]
        assert len(removed) == old_count - new_count
        assert removed.apply(lambda r: specialized_cafe_kind(r['카테고리'], r['가게명']) is not None,
                             axis=1).all()
        assert not new.apply(lambda r: specialized_cafe_kind(r['카테고리'], r['가게명']) is not None,
                             axis=1).any()
        if transport == '대중교통' and text:
            ranked = app.add_scores(old, []).sort_values(['score', 'origin_distance_km', 'place_id'],
                                                        ascending=[False, True, True])
            previous, _ = select_diverse_spots(ranked, 10)
            assert '홈즈앤루팡 보드게임카페 천안점' in set(previous['가게명'])
        response = app.app.test_client().post('/recommend/spot', json={**ORIGIN,
            'transport': transport, 'user_text': text, 'persona_tags': ACTUAL_TAGS, 'count': 10})
        assert response.status_code == 200
        assert len(response.json['places']) == 10
        assert {r['place_id'] for r in response.json['places']} <= set(new['place_id'])
        assert response.json['metadata']['verified_tag_candidate_count'] == 0
        assert response.json['metadata']['preference_evidence'] == 'unavailable'
        assert response.json['metadata']['constraints_relaxed'] == []
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
