"""D-01–D-04: fixed offline evidence and synthetic policy boundary regressions."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import app
from place_identity import ensure_ids, local_aliases
from place_quality import (coordinate_quality, display_name,
                           display_address, filter_coordinate_candidates)
from Preprocess.RunPreprocess import data_pipeline as pipeline
from Preprocess.crawler import parser, saver

ORIGIN = {'user_lat': 36.8082, 'user_lng': 127.1506, 'transport': '대중교통'}


def row(name='전시관', address='충남 천안시 중앙로 10', category='전시관', **kw):
    return {'가게명': name, '주소': address, '카테고리': category,
            'latitude': 36.8083, 'longitude': 127.1507, '방문자수': 1, '블로그수': 0, **kw}


@pytest.mark.parametrize('address', ['', '충남', '충남 천안시 동남구',
    '충남 천안시 서북구 불당동', '충남 아산시 음봉면 덕지리',
    '충남 천안시 중앙로', '충남 천안시 중앙로\n1천안역 1번 출구에서 100m\n미터'])
def test_locality_never_becomes_place_coordinate(address):
    quality = coordinate_quality(row(address=address, provider_place_id='123',
                                     place_coordinate_verified=True))
    assert quality['reason_codes'] == ['address_not_specific']
    assert quality['status'] == 'blocked'
    assert not any(quality[k] for k in ('recommendation_eligible', 'distance_eligible', 'map_coordinate_eligible'))


@pytest.mark.parametrize('address', ['충남 천안시 중앙로 10', '충남 천안시 성정동 123-4',
    '충남 천안시 목천읍 덕전리 산 10-2', '충남 천안시 충절로 410 1층',
    '충남 천안시 성성2길 95\n1천안역 1번 출구에서 100m\n미터'])
def test_specific_address_is_eligible_but_never_verified(address):
    quality = coordinate_quality(row(address=address))
    assert quality['recommendation_eligible']
    assert quality['status'] == 'unverified'
    assert quality['place_coordinate_verified'] is False
    assert quality['coordinate_source'] == 'legacy_unknown'


@pytest.mark.parametrize('lat,lng', [(float('nan'), 127), (36, float('inf')), (91, 127), (36, -181), (None, 127)])
def test_nonfinite_or_invalid_coordinates_are_blocked(lat, lng):
    quality = coordinate_quality(row(latitude=lat, longitude=lng))
    assert quality['reason_codes'] == ['invalid_coordinates']
    assert quality['map_coordinate_eligible'] is False


@pytest.mark.parametrize('path,extra', [('/recommend/spot', {'user_text': '공원'}),
    ('/recommend/course', {'slot_types': ['음식', '자연·산책', '카페'], 'spot_count': 3})])
def test_qa_park_excluded_before_recommendation_and_distance(monkeypatch, path, extra):
    unsafe = row('천안삼거리공원도시,테마공원', '충남 천안시 동남구', '도시,테마공원',
                 latitude=36.81083006, longitude=127.1488888, 방문자수=100000)
    frame = ensure_ids(pd.DataFrame([unsafe, row('음식', category='한식'),
        row('안전한형식공원', category='공원'), row('카페', category='카페')]))
    monkeypatch.setattr(app, 'get_df', lambda _: frame)
    response = app.app.test_client().post(path, json={**ORIGIN, **extra, 'count': 1})
    assert response.status_code == 200
    body = response.json
    result = body.get('places') or body['courses'][0]
    assert unsafe['가게명'] not in [p['name'] for p in result]
    assert frame.iloc[0]['place_id'] not in [p['place_id'] for p in result]
    coverage = body['metadata']['candidate_quality']
    assert (coverage['input_count'], coverage['excluded_count'], coverage['eligible_count']) == (4, 1, 3)
    assert coverage['excluded_reason_counts'] == {'address_not_specific': 1}
    assert all(p['coordinate_quality']['status'] == 'unverified' for p in result)


def test_all_uncertain_candidates_report_shortage_without_relaxing(monkeypatch):
    frame = ensure_ids(pd.DataFrame([row(address='충남 천안시 동남구', category='공원')]))
    monkeypatch.setattr(app, 'get_df', lambda _: frame)
    for path, extra in [('/recommend/spot', {'user_text': '공원'}),
                        ('/recommend/course', {'slot_types': ['자연·산책'] * 3})]:
        response = app.app.test_client().post(path, json={**ORIGIN, **extra})
        assert response.status_code == 422
        assert response.json['metadata']['candidate_quality']['excluded_count'] == 1
        assert response.json['metadata']['constraints_relaxed'] == []


@pytest.mark.parametrize('text', ['맛집', '밥집', '음식점', '음식'])
def test_generic_food_uses_actual_food_categories_offline(text):
    assert app.extract_spot_category(text) == app.FOOD_CATS


def test_model_food_alias_validated_and_normalized(monkeypatch):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': ['맛집']})
    assert app.extract_spot_category('저녁 먹을 곳') == app.FOOD_CATS


@pytest.mark.parametrize('value', ['맛있는곳', '.*', '아무곳', '최고의 분위기'])
def test_unknown_model_filters_are_actionable_not_false_shortage(monkeypatch, value):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': [value]})
    response = app.app.test_client().post('/recommend/spot', json={**ORIGIN, 'user_text': '추천해줘'})
    assert response.status_code == 422
    assert response.json['reason'] == 'category_required'
    assert 'metadata' not in response.json


def test_specific_chicken_is_never_broadened_even_with_generic_words(monkeypatch):
    assert app.extract_spot_category('맛집 닭갈비 음식점') == ['닭갈비']
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': ['맛집']})
    assert app.extract_spot_category('카페 말고 닭갈비 맛집') == ['닭갈비']


def test_food_exclusion_is_hard_even_when_actual_category_contains_broad_food(monkeypatch):
    frame = ensure_ids(pd.DataFrame([row('닭갈비', category='한식,닭갈비'), row('다른음식', category='한식')]))
    monkeypatch.setattr(app, 'get_df', lambda _: frame)
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': ['맛집']})
    response = app.app.test_client().post('/recommend/spot', json={**ORIGIN, 'user_text': '닭갈비 말고 맛집'})
    assert response.status_code == 200
    assert [p['name'] for p in response.json['places']] == ['다른음식']
    assert response.json['metadata']['excluded_category_filters'] == ['닭갈비']


def test_model_cannot_reintroduce_explicit_negative(monkeypatch):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': ['카페']})
    response = app.app.test_client().post('/recommend/spot', json={**ORIGIN, 'user_text': '카페 말고 공원'})
    assert response.status_code == 422
    assert response.json['reason'] == 'category_required'


def test_overlapping_category_mentions_keep_their_own_negation_scope(monkeypatch):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': ['카페']})
    assert app.excluded_categories('카페 말고 키즈카페') == ['카페']
    assert app.excluded_categories('키즈카페 말고 카페') == ['키즈카페']
    assert app.extract_spot_category('키즈카페 말고 카페') == ['카페']


def test_unspecified_outing_does_not_default_to_property_showroom():
    frame = pd.DataFrame([row('주택', category='주택전시관'), row('전시', category='전시관')])
    assert app.filter_keywords(frame, [], [])['가게명'].tolist() == ['전시']


@pytest.mark.parametrize('housing', ['주택전시관', '모델하우스', '분양홍보관', '견본주택'])
def test_property_domain_is_distinct_from_generic_exhibitions(housing):
    assert not app.category_matches(housing, ['전시', '전시관', '공원', '박물관'])
    assert app.category_matches(housing, ['주택전시관'])
    assert app.category_matches('전시관', ['전시'])


def test_parent_indoor_exhibition_and_course_share_domain_policy(monkeypatch):
    # Give the showroom a specific address so D-01 cannot mask D-03.
    frame = ensure_ids(pd.DataFrame([row('주택', category='주택전시관', 방문자수=10000),
        row('문화전시', category='전시관'), row('문화전시2', address='충남 천안시 중앙로 12'),
        row('문화전시3', address='충남 천안시 중앙로 14')]))
    monkeypatch.setattr(app, 'get_df', lambda _: frame)
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': ['전시']})
    client = app.app.test_client()
    response = client.post('/recommend/spot', json={**ORIGIN,
        'user_text': '카페 말고 부모님과 실내 전시를 보고 싶어요', 'persona_tags': ['박물관/전시']})
    assert response.status_code == 200
    assert '주택' not in [p['name'] for p in response.json['places']]
    course = client.post('/recommend/course', json={**ORIGIN, 'slot_types': ['문화·역사'] * 3, 'count': 1})
    assert course.status_code == 200
    assert '주택' not in [p['name'] for p in course.json['courses'][0]]
    explicit = client.post('/recommend/spot', json={**ORIGIN, 'user_text': '모델하우스 관람'})
    assert explicit.status_code == 200
    assert [p['name'] for p in explicit.json['places']] == ['주택']


def test_geocoder_never_calls_provider_for_broad_address(monkeypatch):
    monkeypatch.setattr(pipeline, '_get', lambda *a, **k: pytest.fail('No centroid geocoding'))
    assert pipeline.get_coords('충남 천안시 동남구', 'synthetic') == (None, None)


@pytest.mark.parametrize('address_type,address,expected', [
    ('REGION', '충남 천안시 동남구', (None, None)),
    ('REGION_ADDR', '충남 천안시 성정동', (None, None)),
    ('ROAD_ADDR', '충남 천안시 중앙로 10', (36.8, 127.1)),
    ('REGION_ADDR', '충남 천안시 성정동 10-2', (None, None))])
def test_geocoder_response_must_be_an_address_not_an_administrative_point(monkeypatch, address_type, address, expected):
    monkeypatch.setattr(pipeline, '_get', lambda *a, **k: SimpleNamespace(json=lambda: {
        'documents': [{'address_type': address_type, 'address_name': address, 'y': '36.8', 'x': '127.1'}]}))
    assert pipeline.get_coords('충남 천안시 중앙로 10', 'synthetic') == expected


def test_pipeline_rejects_cached_locality_without_changing_source_identity(tmp_path, monkeypatch):
    source, output = tmp_path / 'source', tmp_path / 'out'
    source.mkdir()
    raw = pd.DataFrame([row('도시공원도시,테마공원', '충남 천안시 동남구', '도시,테마공원'),
                        row('동명카페', category='카페')])
    raw.to_csv(source / '충남_천안시_공원.csv', index=False)
    monkeypatch.setattr(pipeline, 'get_coords', lambda *a: pytest.fail('Existing coords need no API'))
    result = pipeline.run_pipeline(source, output)
    assert len(result) == 1
    assert result.iloc[0]['place_id'] == ensure_ids(raw).iloc[1]['place_id']
    held = pd.read_csv(output / 'preprocess_rejected.csv')
    assert held.iloc[0]['preprocess_error'] == 'address_not_specific'
    assert held.iloc[0]['가게명'] == raw.iloc[0]['가게명']


def test_display_cleanup_preserves_source_ids_aliases_and_same_name_branches():
    raw = ensure_ids(pd.DataFrame([
        row('공원도시,테마공원', category='도시,테마공원'),
        row('공원도시,테마공원', '충남 천안시 중앙로 12', '도시,테마공원')]))
    outputs = [app._fmt(r) for r in raw.to_dict('records')]
    assert [r['name'] for r in outputs] == ['공원', '공원']
    assert len({r['place_id'] for r in outputs}) == 2
    for original, formatted in zip(raw.to_dict('records'), outputs):
        assert formatted['source_name'] == original['가게명']
        assert formatted['identity_key'] == original['identity_key']
        assert set(formatted['identity_aliases']) == local_aliases(original)
    assert display_name('골목카페', '카페') == '골목카페'
    assert display_name('전시관', '전시관') == '전시관'


def test_transit_suffix_cleanup_is_narrow_and_not_address_identity():
    original = '충남 천안시 중앙로 10 1층\n1봉명역 1번 출구에서 992m\n미터'
    assert display_address(original) == '충남 천안시 중앙로 10 1층'
    assert display_address('충남 천안시 중앙로 10 출구빌딩 2층') == '충남 천안시 중앙로 10 출구빌딩 2층'
    assert display_address('충남 천안시 중앙로 10\n별관 2층') == '충남 천안시 중앙로 10\n별관 2층'
    formatted = app._fmt(ensure_ids(pd.DataFrame([row(address=original)])).iloc[0].to_dict())
    assert formatted['source_address'] == original
    assert formatted['address'] == '충남 천안시 중앙로 10 1층'


def test_saver_stores_raw_evidence_separately_from_display(tmp_path):
    path = tmp_path / 'source.csv'
    name, address = '공원도시,테마공원', '충남 천안시 중앙로 10\n1천안역 1번 출구에서 100m\n미터'
    pid = saver.save_item(path, {'name': name, 'address': address, 'category': '도시,테마공원',
                                'source_list_text': 'raw provider wrapper'})
    record = pd.read_csv(path).iloc[0]
    assert record['가게명'] == record['source_name'] == name
    assert record['주소'] == record['source_address'] == address
    assert record['display_name'] == '공원'
    assert record['display_address'] == '충남 천안시 중앙로 10'
    assert record['source_list_text'] == 'raw provider wrapper'
    assert pid == ensure_ids(pd.DataFrame([row(name, address, '도시,테마공원')])).iloc[0]['place_id']


def test_parser_prefers_narrow_address_field_and_preserves_raw_name():
    calls = []
    def find(_by, selector):
        calls.append(selector)
        return [SimpleNamespace(text='충남 천안시 중앙로 10' if selector == 'span.LDgIH' else 'wrapper directions')]
    driver = SimpleNamespace(find_elements=find)
    assert parser.first_available_text(driver, 'span.LDgIH', 'div.vV_z_') == '충남 천안시 중앙로 10'
    assert calls == ['span.LDgIH']
    item = SimpleNamespace(find_elements=lambda *a: [SimpleNamespace(text='공원\n도시,테마공원')])
    assert parser.extract_name_element(item)[1] == '공원\n도시,테마공원'
    assert display_name(parser.extract_name_element(item)[1], '도시,테마공원') == '공원'


def test_frozen_database_quality_is_readonly_and_qa_park_is_blocked():
    path = Path(app.__file__).with_name('places.db')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    original = app.get_df()
    eligible, metadata = filter_coordinate_candidates(original)
    park = original[original['가게명'].eq('천안삼거리공원도시,테마공원')]
    assert len(park) == 1
    assert park.iloc[0]['place_id'] not in set(eligible['place_id'])
    assert len(original) == 13745
    assert metadata['input_count'] == metadata['eligible_count'] + metadata['excluded_count']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before == '6e51a45748c26ef6d4239974950098291249246b5f0ae0146b919fabe9d6b3be'
