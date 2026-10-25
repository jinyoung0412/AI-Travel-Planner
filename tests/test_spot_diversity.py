"""Offline brand-variety policy: preserve identities, filters and honest coverage."""
import hashlib
from pathlib import Path

import pandas as pd
import pytest

import app
from place_identity import ensure_ids
from place_quality import filter_coordinate_candidates
from recommender.diversity import BRAND_SOURCE_NAMES, brand_family, select_diverse_spots
from recommender.visits import distinct_visits


ORIGIN = {'user_lat': 36.8082, 'user_lng': 127.1506, 'transport': '대중교통'}
SOURCE_NAMES = ['뚜쥬루 빵돌가마마을', '뚜쥬루과자점 성정점',
                '뚜쥬루과자점 거북이점', '뚜쥬루갤러리아백화점센터시티점']
DB_SHA = '6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be'


def frame(names=SOURCE_NAMES + ['동네카페', '아지트', '아지트']):
    return ensure_ids(pd.DataFrame([{
        '가게명': name, '주소': f'충남 천안시 중앙로 {10 + i}', '카테고리': '베이커리',
        'latitude': 36.8083 + i * .0001, 'longitude': 127.1507,
        '방문자수': 10000 - i * 1000, '블로그수': 0,
        'blog_tags': '{}', 'blog_tag_status': 'legacy_unverified',
    } for i, name in enumerate(names)]))


def post(client, **extra):
    return client.post('/recommend/spot', json={**ORIGIN, 'count': 5,
        'persona_tags': ['친구와', '카페 투어'], **extra})


def test_diversity_is_not_visit_identity_and_does_not_fuzzy_group():
    p = frame()
    assert len(distinct_visits(p)) == 7
    assert p.iloc[:4]['place_id'].nunique() == 4
    selected, metadata = select_diverse_spots(p, 4)
    assert selected['가게명'].tolist() == [SOURCE_NAMES[0], '동네카페', '아지트', '아지트']
    assert selected['place_id'].tolist() == p.iloc[[0, 4, 5, 6]]['place_id'].tolist()
    assert metadata['returned_known_brand_counts'] == {'뚜쥬루': 1}
    assert metadata['repeated_brand_backfill_count'] == 0
    for name in ['뚜쥬루와 비슷한 카페', '뚜쥬루과자점 새지점', '베이커리 카페', '아지트']:
        assert brand_family({'가게명': name}) is None


def test_exact_duplicate_is_removed_before_brand_backfill():
    p = frame(SOURCE_NAMES)
    duplicate = p.iloc[[0]].assign(place_id='provider:distinct-id')
    selected, metadata = select_diverse_spots(pd.concat([p, duplicate]), 5)
    assert selected['place_id'].tolist() == p['place_id'].tolist()
    assert metadata['distinct_candidate_count'] == 4
    assert metadata['repeated_brand_backfill_count'] == 3
    assert metadata['returned_known_brand_counts'] == {'뚜쥬루': 4}


@pytest.mark.parametrize('count,returned,backfill', [(1, 1, 0), (5, 5, 1), (10, 7, 3)])
def test_count_backfill_and_real_shortage_metadata(monkeypatch, count, returned, backfill):
    p = frame()
    monkeypatch.setattr(app, 'get_df', lambda _: p)
    response = post(app.app.test_client(), count=count)
    assert response.status_code == 200
    metadata = response.json['metadata']
    assert (metadata['requested_count'], metadata['returned_count']) == (count, returned)
    assert len(response.json['places']) == returned
    assert metadata['reason'] == ('insufficient_candidates' if returned < count else None)
    assert metadata['diversity']['repeated_brand_backfill_count'] == backfill
    assert metadata['constraints_relaxed'] == []
    assert metadata['verified_tag_candidate_count'] == 0
    assert metadata['preference_evidence'] == 'unavailable'
    assert metadata['category_preference_tags_applied'] == ['카페 투어']
    assert '활동 태그(카페 투어)는 장소 종류에 반영' in metadata['preference_limitation']
    assert '동행·분위기를 포함한 취향 일치 근거는 없습니다' in metadata['preference_limitation']


def test_explicit_brand_request_preserves_multiple_ranked_branches(monkeypatch):
    p = frame()
    monkeypatch.setattr(app, 'get_df', lambda _: p)
    response = post(app.app.test_client(), user_text='뚜쥬루 베이커리', count=3)
    assert response.status_code == 200
    assert {r['place_id'] for r in response.json['places']} == set(p.iloc[:3]['place_id'])
    metadata = response.json['metadata']
    assert metadata['diversity']['requested_brand_exemptions'] == ['뚜쥬루']
    assert metadata['diversity']['repeated_brand_backfill_count'] == 0
    assert metadata['category_preference_tags_applied'] == []


@pytest.mark.parametrize('text', ['뚜쥬루 말고 카페', '뚜쥬루 주변 카페', '뚜쥬루 근처 베이커리',
                                  '안뚜쥬루 카페', '카페'])
def test_ambiguous_or_unrelated_brand_mentions_do_not_disable_variety(text):
    assert app._requested_brand_families(text) == []


def test_diversity_backfill_cannot_restore_filtered_places(monkeypatch):
    p = frame(SOURCE_NAMES)
    p.loc[1, 'latitude'] = 36.9  # Beyond transit radius.
    p.loc[2, '카테고리'] = '카페'  # Explicitly excluded below.
    p.loc[3, '주소'] = '충남 천안시 동남구'  # No usable address.
    monkeypatch.setattr(app, 'get_df', lambda _: p)
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': ['베이커리']})
    response = post(app.app.test_client(), user_text='카페 말고 베이커리')
    assert response.status_code == 200
    assert [r['place_id'] for r in response.json['places']] == [p.iloc[0]['place_id']]
    metadata = response.json['metadata']
    assert metadata['reason'] == 'insufficient_candidates'
    assert metadata['excluded_category_filters'] == ['카페']
    assert metadata['diversity']['distinct_candidate_count'] == 1
    assert metadata['constraints_relaxed'] == []


# Generic cafe policy now excludes explicit entertainment-purpose cafe kinds
# (and clear board-cafe name evidence), so these pools shrink by 29 / 20.
@pytest.mark.parametrize('transport,expected_pool', [('차', 1790), ('대중교통', 957)])
@pytest.mark.parametrize('count', [5, 10])
def test_frozen_db_station_cafe_variety_and_repeatability(monkeypatch, transport, expected_pool, count):
    path = Path(app.__file__).with_name('places.db')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == DB_SHA
    monkeypatch.setattr(app, 'DB_PATH', str(path))
    original = app.get_df()
    eligible, quality = filter_coordinate_candidates(original)
    pool = app.filter_keywords(app.filter_radius(eligible, ORIGIN['user_lat'], ORIGIN['user_lng'],
                                               transport), ['카페', '베이커리'], [])
    ranked = app.add_scores(pool, []).sort_values(['score', 'origin_distance_km', 'place_id'],
                                                ascending=[False, True, True])
    baseline = distinct_visits(ranked).head(count)
    assert sum(brand_family(r) == '뚜쥬루' for r in baseline.to_dict('records')) == 3
    assert len(original) == 13745
    assert quality['eligible_count'] == 13318
    assert len(pool) == expected_pool
    assert pool['blog_tag_status'].eq('verified').sum() == 0
    assert len(pool[pool['가게명'].isin(BRAND_SOURCE_NAMES['뚜쥬루'])]) == 4
    monkeypatch.setattr(app, 'get_df', lambda _: original)
    client = app.app.test_client()
    first = post(client, count=count, transport=transport)
    second = post(client, count=count, transport=transport)
    assert first.status_code == second.status_code == 200
    assert first.json == second.json
    places = first.json['places']
    assert len(places) == count
    assert len({p['place_id'] for p in places}) == count
    assert sum(p['source_name'] in BRAND_SOURCE_NAMES['뚜쥬루'] for p in places) == 1
    metadata = first.json['metadata']
    assert metadata['returned_count'] == metadata['requested_count'] == count
    assert metadata['diversity']['distinct_candidate_count'] == expected_pool
    assert metadata['diversity']['known_brand_candidate_count'] == 4
    assert metadata['diversity']['repeated_brand_backfill_count'] == 0
    assert metadata['constraints_relaxed'] == []
    assert metadata['verified_tag_candidate_count'] == 0
    assert metadata['preference_evidence'] == 'unavailable'
    assert {p['place_id'] for p in places} <= set(pool['place_id'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
