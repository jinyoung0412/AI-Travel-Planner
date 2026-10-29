"""Synthetic-only provenance and status preservation regressions."""
import sqlite3

import pandas as pd
import pytest

from Preprocess.RunPreprocess.build_database import merge_verified_tags, read_database
from Preprocess.RunPreprocess.data_pipeline import read_sources
from Preprocess.RunPreprocess.migrate_place_ids import migrate


def place(**extra):
    return {'가게명': '공원카페', '주소': '충남 천안시 중앙로 10',
            'provider': 'naver', 'provider_place_id': '123', **extra}


def test_fallback_query_stays_as_provenance_not_category(tmp_path):
    pd.DataFrame([place(카테고리='공원', search_category='공원', category_source='search_fallback')]).to_csv(
        tmp_path / '충남_천안시_공원.csv', index=False)
    result = read_sources(tmp_path)
    assert result.iloc[0]['카테고리'] == ''
    assert result.iloc[0]['search_category'] == '공원'
    merged, _ = merge_verified_tags(result, pd.DataFrame())
    assert merged.iloc[0]['카테고리'] == ''
    assert len(merged) == 1  # Unknown classification does not delete the place.


@pytest.mark.parametrize('mode', ['snapshot', 'update'])
def test_category_and_source_are_atomic_and_fallback_never_overrides_provider(mode):
    known = pd.DataFrame([place(카테고리='카페', category_source='provider')])
    fallback = pd.DataFrame([place(카테고리='공원', category_source='search_fallback')])
    merged, _ = merge_verified_tags(fallback, pd.DataFrame(), existing=known, metadata_mode=mode)
    assert merged.iloc[0]['카테고리'] == '카페'
    assert merged.iloc[0]['category_source'] == 'provider'
    legacy, _ = merge_verified_tags(pd.DataFrame([place(카테고리='카페')]), pd.DataFrame())
    assert legacy.iloc[0]['카테고리'] == '카페'
    assert legacy.iloc[0]['category_source'] == 'legacy_unknown'


def test_migration_preserves_collection_failure_review_and_legacy_states(tmp_path):
    statuses = ['fetch_error', 'interrupted', 'parse_unavailable', 'needs_review',
                'no_verified_posts', 'needs_collection', 'ambiguous_legacy', 'legacy_unverified', '']
    rows = [place(provider_place_id=str(i), 주소=f'충남 천안시 중앙로 {i + 1}',
                  blog_tag_status=status, blog_tags='{}', verified_posts='[]')
            for i, status in enumerate(statuses)]
    db = tmp_path / 'fixture.db'
    with sqlite3.connect(db) as conn:
        pd.DataFrame(rows).to_sql('places', conn, index=False)
    migrate(db, tmp_path / 'migration', apply=True)
    actual = read_database(db).set_index('provider_place_id')['blog_tag_status']
    for i, status in enumerate(statuses[:-1]):
        assert actual[str(i)] == status
    # All rows share a name, so only the previously unlabeled row is marked ambiguous.
    assert actual[str(len(statuses) - 1)] == 'ambiguous_legacy'
