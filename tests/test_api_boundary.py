"""Flask contracts: invalid input, offline extraction, optional evidence and failures."""
import hashlib
import sqlite3
from pathlib import Path

import pytest

import app
from api_request import parse_recommendation
from place_identity import ensure_ids

ORIGIN = {'user_lat': 36.8151, 'user_lng': 127.1139}
SLOTS = ['음식', '자연·산책', '카페']


@pytest.fixture
def client(monkeypatch, places):
    monkeypatch.setattr(app, 'get_df', lambda region: ensure_ids(places))
    return app.app.test_client()


@pytest.mark.parametrize('body', [[], None, True, 3, 'text', {'user_text': 2},
    {'user_text': []}, {'user_text': None}, {'user_text': 'x' * 1001}])
def test_suggestions_validate_before_calling_model(client, body):
    response = client.post('/suggest/tags', json=body)
    assert response.status_code == 400
    assert response.json['reason'] == 'invalid_request'


def test_blank_suggestions_are_local_success(client):
    assert client.post('/suggest/tags', json={'user_text': '  '}).json == {'tags': []}


def test_suggestion_schema_and_allowlist(client, monkeypatch):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'tags': [' 조용한 ', '카페 투어', '조용한', '목록 밖']})
    response = client.post('/suggest/tags', json={'user_text': '조용한 카페'})
    assert response.status_code == 200
    assert response.json['tags'] == ['조용한', '카페 투어']
    for malformed in ({}, {'tags': '카페 투어'}, {'tags': [12]}, {'tags': ['']}, []):
        monkeypatch.setattr(app, '_call_claude', lambda *a: malformed)
        failed = client.post('/suggest/tags', json={'user_text': '추천'})
        assert failed.status_code == 200
        assert failed.json['metadata']['selection_method'] == 'source_rules_fallback'


@pytest.mark.parametrize('text,expected', [
    ('연인이랑 데이트 할 곳을 찾고있어요', ['연인과']),
    ('연인이랑 첫 데이트 할 곳', ['연인과', '첫 데이트']),
    ('첫 데이트 말고 평소처럼 데이트', []),
    ('a first date', ['첫 데이트']),
])
def test_first_date_suggestion_requires_explicit_source_evidence(client, monkeypatch, text, expected):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'tags': ['연인과', '첫 데이트']})
    response = client.post('/suggest/tags', json={'user_text': text})
    assert response.status_code == 200
    assert response.json['tags'] == expected


def test_missing_model_is_service_failure_without_exception_text(client, monkeypatch):
    def fail(*args):
        raise RuntimeError('secret-key-private-host')
    monkeypatch.setattr(app, '_call_claude', fail)
    for path, data in [('/suggest/tags', {'user_text': '추천'}),
                       ('/recommend/spot', {**ORIGIN, 'user_text': '도자기 만드는 곳'})]:
        response = client.post(path, json=data)
        assert response.status_code == (200 if path == '/suggest/tags' else 503)
        assert 'secret' not in response.get_data(as_text=True)


@pytest.mark.parametrize('text,expected', [
    ('닭갈비 음식점', ['닭갈비']), ('아산 카페', ['카페']), ('해산물', ['해산물']),
    ('산', ['산']), ('키즈카페', ['키즈카페']), ('수영하고 싶어', ['수영']),
])
def test_known_explicit_categories_work_without_model(text, expected):
    assert app.extract_spot_category(text) == expected


@pytest.mark.parametrize('text', ['카페 싫어 공원', '닭갈비 말고 카페', '카페 없이 공원',
    '카페 아닌 공원', '공원 대신 카페', '카페 원치 않아'])
def test_negations_never_use_positive_substring_fallback(client, text):
    response = client.post('/recommend/spot', json={**ORIGIN, 'user_text': text})
    assert response.status_code == 503
    assert response.json['reason'] == 'category_unavailable'


def test_model_negation_result_wins_over_persona_category(client, monkeypatch):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': ['공원']})
    response = client.post('/recommend/spot', json={**ORIGIN, 'user_text': '카페 싫어 공원',
                                                    'persona_tags': ['카페 투어']})
    assert response.status_code == 200
    assert response.json['metadata']['category_filters'] == ['공원']
    assert all(p['category'] == '공원' for p in response.json['places'])


def test_empty_or_malformed_category_result_does_not_drop_explicit_constraint(client, monkeypatch):
    for result in ({}, {'category_filters': '카페'}, {'category_filters': [2]}):
        monkeypatch.setattr(app, '_call_claude', lambda *a: result)
        response = client.post('/recommend/spot', json={**ORIGIN, 'user_text': '닭갈비 말고 카페',
                                                        'persona_tags': ['자연/산책']})
        assert response.status_code == 503


def test_only_exclusions_without_a_target_is_an_actionable_client_error(client, monkeypatch):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': []})
    response = client.post('/recommend/spot', json={**ORIGIN, 'user_text': '카페 말고',
                                                   'persona_tags': ['카페 투어']})
    assert response.status_code == 422
    assert response.json['reason'] == 'category_required'


@pytest.mark.parametrize('path,extra', [('/recommend/spot', {}),
    ('/recommend/course', {'slot_types': SLOTS})])
def test_unverified_candidates_skip_expansion_and_expose_evidence_limit(client, monkeypatch, path, extra):
    def fail(*args):
        pytest.fail('No model call is useful without verified candidate tags')
    monkeypatch.setattr(app, '_call_claude', fail)
    response = client.post(path, json={**ORIGIN, **extra, 'persona_tags': ['힐링/여유']})
    assert response.status_code == 200
    metadata = response.json['metadata']
    assert metadata['verified_tag_candidate_count'] == 0
    assert metadata['preference_evidence'] == 'unavailable'
    assert metadata['preference_requested'] is True
    assert metadata['preference_limitation']
    assert all(p['blog_tag_status'] != 'verified' for p in response.json.get('places', []))


def test_verified_candidate_tags_expand_once_and_keep_ranking_evidence(client, places, monkeypatch):
    p = ensure_ids(places.head(3))
    p['카테고리'], p['방문자수'], p['블로그수'] = '카페', 0, 0
    p['blog_tag_status'] = ['legacy_unverified', 'verified', 'legacy_unverified']
    p['blog_tags'] = ['{}', '{"조용한": 1}', '{}']
    calls = []
    monkeypatch.setattr(app, 'get_df', lambda region: p)
    monkeypatch.setattr(app, '_call_claude', lambda *a: calls.append(a) or {'blog_tag_keywords': ['조용한']})
    response = client.post('/recommend/spot', json={**ORIGIN, 'user_text': '카페',
        'persona_tags': ['조용한'], 'count': 1})
    assert response.status_code == 200
    assert len(calls) == 1
    assert response.json['places'][0]['place_id'] == p.iloc[1]['place_id']
    assert response.json['metadata']['preference_evidence'] == 'verified_tags_available'
    assert response.json['metadata']['verified_tag_candidate_count'] == 1


def test_verified_but_ineligible_category_does_not_trigger_expansion(client, places, monkeypatch):
    p = ensure_ids(places)
    p['blog_tag_status'] = p['카테고리'].map(lambda c: 'verified' if c == '카페' else 'legacy_unverified')
    monkeypatch.setattr(app, 'get_df', lambda region: p)
    response = client.post('/recommend/spot', json={**ORIGIN, 'user_text': '공원', 'persona_tags': ['조용한']})
    assert response.status_code == 200
    assert response.json['metadata']['verified_tag_candidate_count'] == 0


def test_course_evidence_filter_does_not_change_engine_scoring_pool(client, places, monkeypatch):
    p = ensure_ids(places.head(4))
    p.loc[p.index[-1], '카테고리'] = '주차장'
    p['blog_tag_status'] = ['legacy_unverified'] * 3 + ['verified']
    monkeypatch.setattr(app, 'get_df', lambda region: p)
    original = app.search_courses
    def search(df, *args, **kwargs):
        # The engine normalizes popularity over the full radius pool. Preserve it.
        assert '주차장' in df['카테고리'].tolist()
        return original(df, *args, **kwargs)
    monkeypatch.setattr(app, 'search_courses', search)
    response = client.post('/recommend/course', json={**ORIGIN, 'slot_types': SLOTS,
                                                     'persona_tags': ['조용한']})
    assert response.status_code == 200
    assert response.json['metadata']['verified_tag_candidate_count'] == 0


def test_verified_preference_failure_stays_soft(client, places, monkeypatch):
    p = ensure_ids(places)
    p['blog_tag_status'], p['blog_tags'] = 'verified', '{"힐링": 1}'
    monkeypatch.setattr(app, 'get_df', lambda region: p)
    response = client.post('/recommend/course', json={**ORIGIN, 'slot_types': SLOTS,
                                                     'persona_tags': ['힐링/여유']})
    assert response.status_code == 200
    assert response.json['metadata']['constraints_relaxed'] == []


@pytest.mark.parametrize('path', ['/recommend/spot', '/recommend/course'])
def test_extreme_number_is_validation_error(client, path):
    response = client.post(path, json={**ORIGIN, 'user_lat': 10 ** 1000})
    assert response.status_code == 400


@pytest.mark.parametrize('path', ['/suggest/tags', '/recommend/spot', '/recommend/course'])
def test_malformed_oversized_and_nonobject_bodies_are_json_errors(client, path):
    for raw, status in [('{bad', 400), ('[]', 400), ('{"user_text":"' + 'x' * 17000 + '"}', 413)]:
        response = client.post(path, data=raw, content_type='application/json')
        assert response.status_code == status
        assert response.json['reason'] == 'invalid_request'


def test_internal_database_failure_is_sanitized(client, monkeypatch):
    def fail(*a):
        raise sqlite3.OperationalError('private/path secret')
    monkeypatch.setattr(app, 'get_df', fail)
    response = client.post('/recommend/course', json=ORIGIN)
    assert response.status_code == 500
    assert response.json['reason'] == 'internal_error'
    assert 'secret' not in response.get_data(as_text=True)


def test_parser_preserves_callers_input_and_slot_contract():
    raw = {**ORIGIN, 'user_lat': str(ORIGIN['user_lat']), 'slot_types': SLOTS}
    parsed = parse_recommendation(raw, course=True)
    assert isinstance(raw['user_lat'], str)
    assert parsed['spot_count'] == 3
    assert parsed['count'] == 3
    assert parsed['seed'] == 0


def test_readonly_database_does_not_create_missing_file(tmp_path, monkeypatch):
    path = tmp_path / 'missing.db'
    monkeypatch.setattr(app, 'DB_PATH', str(path))
    with pytest.raises(sqlite3.OperationalError):
        app.get_df()
    assert not path.exists()


def test_real_database_read_leaves_bytes_unchanged(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'Flask_server/places.db'
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(app, 'DB_PATH', str(path))
    df = app.get_df()
    assert len(df) > 0
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    # Legacy quarantined evidence is always cleared in memory, never reactivated.
    unverified = df['blog_tag_status'].ne('verified')
    assert df.loc[unverified, 'blog_tags'].eq('{}').all()


@pytest.mark.parametrize('text', ['음식점 또는 카페', '음식점이나 카페', '음식점/카페',
    '음식점 또는 조용한 카페', '음식점이나 가까운 카페'])
def test_explicit_category_alternatives_preserve_generic_food(text):
    filters = app.extract_spot_category(text)
    assert '한식' in filters and '카페' in filters


def test_alternative_transport_does_not_broaden_specific_food():
    assert app.extract_spot_category('차 또는 대중교통으로 닭갈비 음식점') == ['닭갈비']


def test_explicit_search_fallback_cannot_supply_actual_category(places):
    p = ensure_ids(places.head(3))
    p['카테고리'] = ['카페', '', '카페']
    p['search_category'] = '카페'
    p['category_source'] = ['search_fallback', 'search_fallback', 'legacy_unknown']
    assert app.filter_keywords(p, ['카페'], [])['place_id'].tolist() == [p.iloc[2]['place_id']]
    assert app.filter_keywords(p.drop(columns='category_source'), ['카페'], [])['place_id'].tolist() == p['place_id'].tolist()



def test_modified_food_keeps_specific_purpose_when_another_alternative_exists():
    assert set(app.extract_spot_category('닭갈비 음식점 또는 카페')) == {'닭갈비', '카페'}


@pytest.mark.parametrize('text', ['음식점 한식', '음식점한식', '한식 음식점'])
def test_adjacent_specific_food_modifier_keeps_narrow_scope_in_either_order(text):
    assert app.extract_spot_category(text) == ['한식']


@pytest.mark.parametrize('text,expected', [
    ('닭갈비 맛집이나 카페', {'닭갈비','카페'}),
    ('맛집이든 카페든', set(app.FOOD_CATS) | {'카페'}),
    ('맛집이든지 카페', set(app.FOOD_CATS) | {'카페'}),
    ('식당이랑 카페', set(app.FOOD_CATS) | {'카페'}),
])
def test_alternative_connectors_do_not_need_an_exhaustive_allowlist(text, expected):
    assert set(app.extract_spot_category(text)) == expected
