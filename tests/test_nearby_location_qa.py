"""Frozen nearby candidates and actual responses enforce the service-city gate."""
import hashlib
from pathlib import Path

import pytest
import app
from place_quality import filter_coordinate_candidates


@pytest.mark.parametrize('mode', ['spot', 'course'])
@pytest.mark.parametrize('origin,expected_status', [
    ((36.8151, 127.1139), 200),  # Original nearby center/car radius includes 76 outside-city rows.
    ((37.05, 127.35), 422),  # Inside the origin box, but no supported-city venue in radius.
])
def test_nearby_excludes_unsupported_regions_from_frozen_db(mode, origin, expected_status, monkeypatch):
    path = Path(app.DB_PATH)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    source = app.get_df('내 주변')
    # get_df remains a read-only catalog reader. The common recommendation
    # candidate gate, rather than that raw reader, owns service-area policy.
    coordinate_rows, _ = filter_coordinate_candidates(source)
    nearby = app.filter_radius(coordinate_rows, *origin, '차')
    assert (~nearby['지역'].isin(['천안', '아산'])).any()
    eligible, gate = app.filter_service_candidates(nearby, '내 주변')
    assert gate['excluded_count'] > 0
    assert eligible['지역'].isin(['천안', '아산']).all()
    assert eligible['주소'].str.match(r'^(?:충남|충청남도)\s+(?:천안시|아산시)\s').all()
    if expected_status == 422:
        assert eligible.empty
    else:
        assert not eligible.empty
    # Reuse exactly that frozen reader; no provider calls or data writes.
    monkeypatch.setattr(app, 'get_df', lambda _: source)
    body = dict(user_lat=origin[0], user_lng=origin[1], region='내 주변', transport='차',
                user_text='', persona_tags=['친구와'], count=3 if mode == 'course' else 5,
                seed=42, randomize=True)
    if mode == 'course':
        body.update(spot_count=3, slot_types=['음식', '자연·산책', '카페'])
    response = app.app.test_client().post(f'/recommend/{mode}', json=body)
    assert response.status_code == expected_status, response.json
    places = (response.json['places'] if mode == 'spot' else
              [p for course in response.json['courses'] for p in course])
    regions = source.set_index('place_id')['지역'].to_dict()
    assert all(regions[p['place_id']] in ('천안', '아산') for p in places)
    assert all('안성' not in p['address'] for p in places)
    assert response.json['metadata']['candidate_service_area']['excluded_count'] > 0
    assert response.json['metadata']['constraints_relaxed'] == []
    if expected_status == 200:
        assert places  # Positive origin must exercise actual returned venues.
    else:
        assert not places
        assert response.json['metadata']['reason'] in ('insufficient_candidates', 'missing_slot_candidates')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
