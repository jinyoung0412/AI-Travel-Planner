"""Beer intent and model aliases must resolve to supported beer venues only."""
import hashlib
from pathlib import Path

import pandas as pd
import pytest

import app
from place_identity import ensure_ids


TEXT = '연인과 시원한 맥주를 마시고 싶어요.'
ORIGIN = {'region': '천안', 'transport': '대중교통', 'user_lat': 36.8082,
          'user_lng': 127.1506, 'count': 5, 'persona_tags': ['연인과', '맛집 탐방']}


@pytest.mark.parametrize('term', ['맥주', '맥주집', '맥줏집', '맥주전문점', '맥주 전문점', '호프집', '펍'])
def test_drink_aliases_use_the_same_validated_beer_categories(term, monkeypatch):
    assert app.extract_spot_category(term) == ['맥주', '호프']
    # The observed model output "맥주집" must be accepted on the model path too.
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': [term]})
    assert app.extract_spot_category('한잔할 곳 추천해줘') == ['맥주', '호프']


def test_original_sentence_is_supported_without_an_extra_model_call(monkeypatch):
    monkeypatch.setattr(app, '_call_claude', lambda *a: pytest.fail('Known drink intent is offline'))
    assert app.extract_spot_category(TEXT) == ['맥주', '호프']
    assert app.extract_spot_category('연인과 맥주 박물관을 보고 싶어요') == ['박물관']


@pytest.mark.parametrize('text,model,expected,banned', [
    ('맥주 말고 카페', ['맥주집', '카페'], ['카페'], ['맥주', '호프']),
    ('카페 말고 맥주', ['맥주집'], ['맥주', '호프'], ['카페']),
    ('맥주집 말고 공원', ['공원'], ['공원'], ['맥주', '호프']),
    ('맥주 말고는 가지 않을래요', ['맥주집'], ['맥주', '호프'], []),
])
def test_negation_and_qualified_negation_keep_their_scope(monkeypatch, text, model, expected, banned):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': model})
    assert app.excluded_categories(text) == banned
    assert app.extract_spot_category(text) == expected


def test_original_intent_overrides_food_persona_and_never_broadens_to_restaurants(monkeypatch):
    frame = ensure_ids(pd.DataFrame([{
        '가게명': f'장소{i}', '주소': f'충남 천안시 테스트로 {i+1}',
        '카테고리': kind, 'latitude': 36.8083, 'longitude': 127.1506,
        '방문자수': 10000-i, '블로그수': 0, 'blog_tags': '{}',
    } for i, kind in enumerate(['한식', '와인', '카페', '바(BAR)', '맥주,호프', '호프'])]))
    monkeypatch.setattr(app, 'get_df', lambda _: frame)
    response = app.app.test_client().post('/recommend/spot', json={**ORIGIN, 'user_text': TEXT})
    assert response.status_code == 200
    assert {p['category'] for p in response.json['places']} == {'맥주,호프', '호프'}
    assert response.json['metadata']['category_filters'] == ['맥주', '호프']
    assert response.json['metadata']['reason'] == 'insufficient_candidates'
    assert response.json['metadata']['constraints_relaxed'] == []
    assert response.json['metadata']['preference_evidence'] == 'unavailable'


def test_unrecognized_model_category_still_requires_clarification(monkeypatch):
    monkeypatch.setattr(app, '_call_claude', lambda *a: {'category_filters': ['미지원장소']})
    response = app.app.test_client().post('/recommend/spot', json={**ORIGIN, 'user_text': '데이트할 곳'})
    assert response.status_code == 422
    assert response.json['reason'] == 'category_required'


def test_real_database_beer_recommendation_preserves_db_and_evidence(monkeypatch):
    path = Path(app.__file__).with_name('places.db')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(app, 'DB_PATH', str(path))
    client = app.app.test_client()
    first = client.post('/recommend/spot', json={**ORIGIN, 'user_text': TEXT})
    second = client.post('/recommend/spot', json={**ORIGIN, 'user_text': TEXT})
    assert first.status_code == second.status_code == 200
    assert first.json == second.json
    places = first.json['places']
    assert len(places) == len({p['place_id'] for p in places}) == 5
    assert all(app.category_matches(p['category'], ['맥주', '호프']) for p in places)
    assert first.json['metadata']['verified_tag_candidate_count'] == 0
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
