"""Contracts shared by independently refactored collection, data and APIs."""
import json

import pandas as pd

from place_identity import ensure_ids
from Preprocess.RunPreprocess import data_pipeline


def test_pipeline_preserves_duplicate_coordinates_and_post_evidence(tmp_path, places, monkeypatch):
    source = tmp_path / 'raw'
    source.mkdir()
    output = tmp_path / 'processed'
    first = ensure_ids(places.head(1)).iloc[0].to_dict()
    post = {'url': 'https://blog.naver.com/reviewer/123', 'name_excerpt': first['가게명'] + ' 후기',
            'address_excerpt': first['주소'], 'tags': ['조용한']}
    first.update(blog_tag_status='verified', verified_posts=json.dumps([post]), category_source='provider')
    latest = {**first, 'latitude': None, 'longitude': None, 'verified_posts': '[]',
              'blog_tag_status': 'fetch_error', '방문자수': 999}
    pd.DataFrame([first, latest]).to_csv(source / '천안_공원.csv', index=False)
    monkeypatch.setattr(data_pipeline, 'get_coords', lambda *a: (_ for _ in ()).throw(AssertionError('unexpected geocoding')))
    result = data_pipeline.run_pipeline(source, output, api_key='')
    assert len(result) == 1
    assert result.iloc[0]['latitude'] == first['latitude']
    assert result.iloc[0]['방문자수'] == 999
    assert json.loads(result.iloc[0]['verified_posts']) == [post]
    assert json.loads(result.iloc[0]['blog_tags']) == {'조용한': 1}


def test_raw_reader_ignores_generated_quarantine_sidecars(tmp_path, places):
    places.head(1).to_csv(tmp_path / '천안_공원.csv', index=False)
    pd.DataFrame([{'source_record': '{}', 'quarantine_reason': 'unproven'}]).to_csv(
        tmp_path / '천안_공원.csv.quarantine.csv', index=False)
    assert len(data_pipeline.read_sources(tmp_path)) == 1


def test_pipeline_preserves_unproven_raw_tags_in_audit(tmp_path, places):
    source = tmp_path / 'raw'
    source.mkdir()
    output = tmp_path / 'processed'
    places.head(1).assign(blog_tags='{"unproven": 10}').to_csv(source / '천안_공원.csv', index=False)
    for _ in range(2):
        result = data_pipeline.run_pipeline(source, output, api_key='')
        assert result.iloc[0]['blog_tags'] == '{}'
        audit = pd.read_csv(output / 'preprocess_quarantine.csv')
        assert len(audit) == 1
        assert json.loads(audit.iloc[0]['source_record'])['blog_tags'] == '{"unproven": 10}'


def test_api_emits_historical_aliases_and_conflict_owners():
    from pathlib import Path
    import app
    cases = json.loads((Path(__file__).parent / 'fixtures/place_alias_cases.json').read_text())
    for name in ('canonical', 'conflicted'):
        place = cases[name]
        record = {'가게명': place['name'], '주소': place['address'], 'latitude': place['lat'],
                  'longitude': place['lng'], '카테고리': '카페', 'place_id': place['place_id'],
                  'identity_key': place['identity_key'],
                  'identity_aliases': json.dumps(place['identity_aliases']),
                  'identity_alias_conflicts': json.dumps(place['identity_alias_conflicts'])}
        response = app._fmt(record)
        assert set(response['identity_aliases']) == set(place['identity_aliases'])
        assert response['identity_alias_conflicts'] == place['identity_alias_conflicts']
