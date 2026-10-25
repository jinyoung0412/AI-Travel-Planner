"""A reported ambiguous subfacility must not be relabelled as its parent."""
import hashlib
from pathlib import Path

import pandas as pd
import pytest

import app
from place_identity import ensure_ids
from recommendation_review import filter_reviewed_candidates


HOLD_ID = 'local:v1:522013f58fb3caf15caf2796a86177d84eaa008499324de49792c4751ea08c8c'
PARENT_ID = 'local:v1:523c9ce0116012f2a8974dc4bdd3583acd9721f5b4904a302f930bcb966d97a1'
ORIGIN = {'region': '천안', 'user_lat': 36.8082, 'user_lng': 127.1506,
          'transport': '대중교통', 'count': 3}


def test_real_db_holds_only_unresolved_subfacility_and_preserves_parent():
    path = Path(app.__file__).with_name('places.db')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    frame = app.get_df()
    original = frame.copy(deep=True)
    selected, metadata = filter_reviewed_candidates(frame)
    assert len(frame) == 13745
    assert len(selected) == 13744
    assert set(frame['place_id']) - set(selected['place_id']) == {HOLD_ID}
    assert PARENT_ID in set(selected['place_id'])
    assert selected.loc[selected['place_id'].eq(PARENT_ID), '가게명'].item() == '충청남도교육청학생교육문화원'
    assert metadata['excluded_reason_counts'] == {'unresolved_subfacility_identity': 1}
    pd.testing.assert_frame_equal(frame, original)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_hold_is_not_an_address_wide_or_name_wide_block():
    source = app.get_df()
    flagged = source[source['place_id'].eq(HOLD_ID)]
    corrected = flagged.assign(가게명='별도로 검토된 전시실')
    moved = flagged.assign(주소='충남 천안시 다른길 41')
    for frame in (corrected, moved):
        selected, metadata = filter_reviewed_candidates(frame)
        pd.testing.assert_frame_equal(selected, frame)
        assert metadata['excluded_count'] == 0


@pytest.mark.parametrize('course', [False, True])
def test_spot_and_course_exclude_flagged_identity_without_renaming(monkeypatch, course):
    source = app.get_df('천안')
    bad = source[source['place_id'].eq(HOLD_ID)].copy()
    bad['방문자수'] = 100000000
    extras = ensure_ids(pd.DataFrame([{
        '가게명': name, '주소': f'충남 천안시 테스트로 {i+1}',
        '카테고리': category, 'latitude': 36.8083, 'longitude': 127.1506,
        '방문자수': 1, '블로그수': 0, 'blog_tags': '{}',
    } for i, (name, category) in enumerate([
        ('다른전시1', '전시관'), ('다른전시2', '전시관'), ('다른전시3', '전시관'),
        ('음식', '한식'), ('공원', '공원')])]))
    frame = pd.concat([bad, extras], ignore_index=True)
    monkeypatch.setattr(app, 'get_df', lambda _: frame)
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': ['전시']})
    extra = ({'slot_types': ['음식', '자연·산책', '문화·역사'], 'spot_count': 3, 'count': 1}
             if course else {'user_text': '카페 말고 부모님과 실내 전시를 보고 싶어요'})
    response = app.app.test_client().post('/recommend/course' if course else '/recommend/spot',
                                           json={**ORIGIN, **extra})
    assert response.status_code == 200
    body = response.json
    places = body['courses'][0] if course else body['places']
    assert all(p['place_id'] != HOLD_ID for p in places)
    assert all(p['name'] != '충청남도교육청학생교육문화원' for p in places)
    assert body['metadata']['identity_review']['excluded_count'] == 1
    assert frame.loc[frame['place_id'].eq(HOLD_ID), '가게명'].item() == '학생회관홍보관전시관'


def test_hold_only_candidates_report_a_real_shortage(monkeypatch):
    source = app.get_df('천안')
    monkeypatch.setattr(app, 'get_df', lambda _: source[source['place_id'].eq(HOLD_ID)])
    response = app.app.test_client().post('/recommend/spot', json={**ORIGIN, 'user_text': '전시관'})
    assert response.status_code == 422
    assert response.json['places'] == []
    assert response.json['metadata']['reason'] == 'insufficient_candidates'
    assert response.json['metadata']['identity_review']['excluded_count'] == 1
    assert response.json['metadata']['constraints_relaxed'] == []
