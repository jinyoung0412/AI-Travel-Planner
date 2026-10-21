"""Review regression: a recollection queue is never a complete place catalog."""
import json
import sqlite3
from pathlib import Path

import pandas as pd

from place_identity import ensure_ids
from Preprocess.RunPreprocess.build_database import build, merge_verified_tags, write_database
from Preprocess.RunPreprocess.migrate_place_ids import migrate


def sample_post(place, suffix='old'):
    log_no = {'old': 1, 'new': 2, 'fresh': 3, 'late': 4, 'current': 5, 'stale': 6}[suffix]
    return {'url': f'https://blog.naver.com/reviewer/{log_no}',
            'name_excerpt': f"{place['가게명']} 후기", 'address_excerpt': place['주소'],
            'tags': [f'{suffix}-tag']}


def read_places(path):
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as conn:
        return pd.read_sql('select * from places order by place_id', conn)


def test_partial_recollection_rebuild_preserves_verified_place(tmp_path, places):
    db = tmp_path / 'places.db'
    source = ensure_ids(places.head(2))
    first = source.iloc[0].to_dict()
    proof = sample_post(first)
    tags = pd.DataFrame([{'place_id': first['place_id'], 'blog_tag_status': 'verified',
                          'verified_posts': json.dumps([proof], ensure_ascii=False)}])
    initial, _ = merge_verified_tags(source, tags)
    write_database(initial, db)
    tags_path = tmp_path / 'tags.csv'
    tags.to_csv(tags_path, index=False)
    migrate(db, tmp_path / 'export', apply=True)
    queue = tmp_path / 'export/recollect_places.csv'
    assert len(pd.read_csv(queue)) == 1  # correctly excludes completed place
    build(queue, tags_path, db)  # former README path: must be non-destructive
    actual = read_places(db)
    assert len(actual) == 2
    assert set(actual['place_id']) == set(source['place_id'])
    kept = actual.set_index('place_id').loc[first['place_id']]
    assert kept['blog_tag_status'] == 'verified'
    assert json.loads(kept['verified_posts']) == [proof]
    assert json.loads(kept['blog_tags']) == {'old-tag': 1}


def test_full_catalog_and_partial_tag_updates_survive_repeated_migration(tmp_path, places):
    db = tmp_path / 'places.db'
    source = ensure_ids(places.head(3))
    first, second = source.iloc[0].to_dict(), source.iloc[1].to_dict()
    old_proof = sample_post(first)
    initial, _ = merge_verified_tags(source, pd.DataFrame([{
        'place_id': first['place_id'], 'blog_tag_status': 'verified',
        'verified_posts': json.dumps([old_proof], ensure_ascii=False)}]))
    audit = pd.DataFrame([{'source_record': '{"original":"legacy tag"}', 'quarantine_reason': 'legacy'}])
    write_database(initial, db, audit)
    # Current source may contain arbitrary other tables; rebuild must preserve them.
    with sqlite3.connect(db) as conn:
        conn.execute('create table retained_metadata (value text)')
        conn.execute('insert into retained_metadata values ("keep")')
    partial = pd.DataFrame([{'place_id': second['place_id'], 'blog_tag_status': 'verified',
                             'verified_posts': json.dumps([sample_post(second, 'new')], ensure_ascii=False)}])
    tags = tmp_path / 'partial_tags.csv'
    partial.to_csv(tags, index=False)
    export = tmp_path / 'export'
    for cycle in range(3):
        stats = migrate(db, export, apply=True)
        catalog = pd.read_csv(export / 'places_catalog.csv')
        assert len(catalog) == 3
        assert len(pd.read_csv(export / 'recollect_places.csv')) == (2 if cycle == 0 else 1)
        assert catalog.set_index('place_id').loc[first['place_id'], 'verified_posts'] == json.dumps([old_proof], ensure_ascii=False)
        built = build(export / 'places_catalog.csv', tags, db)
        assert built['mode'] == 'upsert' and built['removed_place_ids'] == []
        actual = read_places(db)
        assert set(actual['place_id']) == set(source['place_id'])
        assert actual['blog_tag_status'].eq('verified').sum() == 2
        assert json.loads(actual.set_index('place_id').loc[first['place_id'], 'verified_posts']) == [old_proof]
        assert Path(stats['backup']).is_file() and Path(built['backup']).is_file()
        with sqlite3.connect(db) as conn:
            assert conn.execute('select count(*) from blog_tags_quarantine').fetchone()[0] == 1
            assert conn.execute('select value from retained_metadata').fetchone()[0] == 'keep'
        if cycle:
            pd.testing.assert_frame_equal(actual, previous)
        previous = actual


def test_missing_tag_file_and_failed_collection_cannot_erase_verified_posts(tmp_path, places):
    db = tmp_path / 'places.db'
    source = ensure_ids(places.head(1))
    first = source.iloc[0].to_dict()
    proof = sample_post(first)
    initial, _ = merge_verified_tags(source, pd.DataFrame([{
        'place_id': first['place_id'], 'blog_tag_status': 'verified',
        'verified_posts': json.dumps([proof], ensure_ascii=False)}]))
    write_database(initial, db)
    metadata = tmp_path / 'places.csv'
    source.to_csv(metadata, index=False)
    tags = tmp_path / 'tags.csv'
    build(metadata, tags, db)  # file doesn't exist
    pd.DataFrame([{'place_id': first['place_id'], 'blog_tag_status': 'fetch_error',
                   'blog_tags': '{}', 'verified_posts': '[]'}]).to_csv(tags, index=False)
    for _ in range(2):
        build(metadata, tags, db)
        actual = read_places(db).iloc[0]
        assert json.loads(actual['verified_posts']) == [proof]
        assert actual['blog_tag_status'] == 'verified'
        with sqlite3.connect(db) as conn:
            assert conn.execute('select count(*) from blog_tags_quarantine').fetchone()[0] == 1


def test_new_posts_union_with_old_and_stale_catalog_cannot_undo_update(places):
    source = ensure_ids(places.head(1))
    first = source.iloc[0].to_dict()
    old = sample_post(first)
    stale, _ = merge_verified_tags(source, pd.DataFrame([{
        'place_id': first['place_id'], 'blog_tag_status': 'verified', 'verified_posts': json.dumps([old])}]))
    changed = {**old, 'tags': ['updated-tag']}
    new = sample_post(first, 'new')
    updated, _ = merge_verified_tags(stale, pd.DataFrame([{
        'place_id': first['place_id'], 'blog_tag_status': 'verified',
        'verified_posts': json.dumps([changed, new])}]), existing=stale)
    again, _ = merge_verified_tags(stale, pd.DataFrame(), existing=updated)
    assert json.loads(again.iloc[0]['verified_posts']) == [changed, new]
    assert json.loads(again.iloc[0]['blog_tags']) == {'new-tag': 1, 'updated-tag': 1}


def test_provider_upgrade_keeps_existing_proof_and_metadata(places):
    source = ensure_ids(places.head(1))
    first = source.iloc[0].to_dict()
    old, _ = merge_verified_tags(source, pd.DataFrame([{
        'place_id': first['place_id'], 'blog_tag_status': 'verified',
        'verified_posts': json.dumps([sample_post(first)])}]))
    newer = source.copy()
    newer['provider'], newer['provider_place_id'] = 'naver', '12345'
    newer = newer[['가게명', '주소', 'provider', 'provider_place_id']]
    result, quarantine = merge_verified_tags(newer, pd.DataFrame(), existing=old)
    assert len(result) == 1 and result.iloc[0]['place_id'] == 'naver:12345'
    assert result.iloc[0]['identity_key'] == first['identity_key']
    assert result.iloc[0]['latitude'] == first['latitude']
    assert result.iloc[0]['blog_tag_status'] == 'verified' and quarantine.empty


def test_explicit_full_replacement_removes_only_when_requested_and_backs_up(tmp_path, places):
    db = tmp_path / 'places.db'
    source = ensure_ids(places.head(2))
    first, second = source.iloc[0].to_dict(), source.iloc[1].to_dict()
    initial, _ = merge_verified_tags(source, pd.DataFrame([{
        'place_id': second['place_id'], 'blog_tag_status': 'verified',
        'verified_posts': json.dumps([sample_post(second)])}]))
    audit = pd.DataFrame([{'source_record': '{"legacy":1}', 'quarantine_reason': 'legacy'}])
    write_database(initial, db, audit)
    metadata, tags = tmp_path / 'subset.csv', tmp_path / 'no_tags.csv'
    source.head(1).to_csv(metadata, index=False)
    assert build(metadata, tags, db)['places'] == 2
    removed = build(metadata, tags, db, replace_all=True)
    assert removed['removed_place_ids'] == [second['place_id']]
    assert read_places(db)['place_id'].tolist() == [first['place_id']]
    backup = read_places(removed['backup'])
    assert len(backup) == 2
    assert backup.set_index('place_id').loc[second['place_id'], 'blog_tag_status'] == 'verified'
    with sqlite3.connect(db) as conn:
        assert conn.execute('select count(*) from blog_tags_quarantine').fetchone()[0] == 1
    assert build(metadata, tags, db, replace_all=True)['removed_place_ids'] == []
    # Removing every place is also explicit, never a side effect of an empty queue.
    source.head(0).to_csv(metadata, index=False)
    assert build(metadata, tags, db)['places'] == 1
    assert build(metadata, tags, db, replace_all=True)['places'] == 0


def test_invalid_old_verified_evidence_is_quarantined_once_under_stricter_rules(tmp_path, places):
    db = tmp_path / 'places.db'
    source = ensure_ids(places.head(1))
    source.loc[0, '주소'] = '충남 천안시 중앙로 10'
    proof = {'url': 'https://blog.naver.com/reviewer/1', 'name_excerpt': '장소0 후기',
             'address_excerpt': '충남 천안시 서부중앙로 10', 'tags': ['wrong']}
    source['blog_tag_status'], source['blog_tags'], source['verified_posts'] = 'verified', '{"wrong":1}', json.dumps([proof], ensure_ascii=False)
    source['지역'] = '천안'
    write_database(source, db)
    for _ in range(2):
        migrate(db, tmp_path / 'export', apply=True)
        actual = read_places(db).iloc[0]
        assert actual['blog_tag_status'] != 'verified'
        assert actual['blog_tags'] == '{}' and actual['verified_posts'] == '[]'
        with sqlite3.connect(db) as conn:
            assert conn.execute('select count(*) from blog_tags_quarantine').fetchone()[0] == 1


def test_failed_staged_write_keeps_original_and_backup(tmp_path, places):
    import pytest
    db = tmp_path / 'places.db'
    initial, _ = merge_verified_tags(places.head(1), pd.DataFrame())
    write_database(initial, db)
    before = db.read_bytes()
    with pytest.raises(sqlite3.IntegrityError):
        write_database(pd.concat([initial, initial]), db, preserve=True)
    assert db.read_bytes() == before
    backups = list(tmp_path.glob('places.db.backup-*'))
    assert len(backups) == 1
    pd.testing.assert_frame_equal(read_places(backups[0]), read_places(db))
    assert not list(tmp_path.glob('*.tmp'))


def test_known_provider_identity_is_not_redirected_by_an_enriched_row(places):
    source = places.head(1).copy()
    source['provider'], source['provider_place_id'] = 'naver', '1'
    source = ensure_ids(source)
    first = source.iloc[0].to_dict()
    old, _ = merge_verified_tags(source, pd.DataFrame([{
        'place_id': 'naver:1', 'blog_tag_status': 'verified',
        'verified_posts': json.dumps([sample_post(first)])}]))
    incoming = source[['place_id', '가게명', '주소', 'provider', 'provider_place_id']].copy()
    incoming['provider_place_id'] = '2'  # enrichment supplies a different known identity
    result, _ = merge_verified_tags(incoming, pd.DataFrame(), existing=old)
    by_id = result.set_index('place_id')
    assert set(by_id.index) == {'naver:1', 'naver:2'}
    assert by_id.loc['naver:1', 'blog_tag_status'] == 'verified'
    assert by_id.loc['naver:2', 'verified_posts'] == '[]'


def test_stale_catalog_does_not_restore_old_address_or_tags(tmp_path, places):
    source = places.head(1).copy()
    source['provider'], source['provider_place_id'] = 'naver', '123'
    source = ensure_ids(source)
    first = source.iloc[0].to_dict()
    stale, _ = merge_verified_tags(source, pd.DataFrame([{
        'place_id': first['place_id'], 'blog_tag_status': 'verified',
        'verified_posts': json.dumps([sample_post(first, 'old')])}]))
    current = stale.copy()
    current['주소'] = '충남 천안시 서부중앙로 20'
    fresh = current.iloc[0].to_dict()
    current['verified_posts'] = json.dumps([sample_post(fresh, 'fresh')], ensure_ascii=False)
    current['blog_tags'] = '{"fresh-tag":1}'
    db = tmp_path / 'places.db'
    write_database(current, db)
    stale.to_csv(tmp_path / 'old_catalog.csv', index=False)
    build(tmp_path / 'old_catalog.csv', tmp_path / 'absent_tags.csv', db)
    actual = read_places(db).iloc[0]
    assert actual['주소'] == fresh['주소']
    assert json.loads(actual['blog_tags']) == {'fresh-tag': 1}
    assert json.loads(actual['verified_posts']) == [sample_post(fresh, 'fresh')]


def test_late_local_id_collection_survives_a_later_provider_id_build(tmp_path, places):
    source = ensure_ids(places.head(1))
    local = source.iloc[0].to_dict()
    old, _ = merge_verified_tags(source, pd.DataFrame([{
        'place_id': local['place_id'], 'blog_tag_status': 'verified',
        'verified_posts': json.dumps([sample_post(local, 'old')])}]))
    enriched = source.copy()
    enriched['provider'], enriched['provider_place_id'] = 'naver', '123'
    promoted, _ = merge_verified_tags(enriched, pd.DataFrame(), existing=old)
    assert promoted.iloc[0]['place_id'] == 'naver:123'
    db = tmp_path / 'places.db'
    write_database(promoted, db)
    promoted.to_csv(tmp_path / 'catalog.csv', index=False)
    pd.DataFrame([{'place_id': local['place_id'], 'blog_tag_status': 'verified',
                   'verified_posts': json.dumps([sample_post(local, 'late')])}]).to_csv(tmp_path / 'late.csv', index=False)
    build(tmp_path / 'catalog.csv', tmp_path / 'late.csv', db)
    actual = read_places(db).iloc[0]
    assert json.loads(actual['blog_tags']) == {'late-tag': 1, 'old-tag': 1}


def test_explicit_metadata_update_invalidates_old_address_proof(places):
    source = places.head(1).copy()
    source['provider'], source['provider_place_id'] = 'naver', '123'
    source = ensure_ids(source)
    first = source.iloc[0].to_dict()
    initial, _ = merge_verified_tags(source, pd.DataFrame([{
        'place_id': first['place_id'], 'blog_tag_status': 'verified',
        'verified_posts': json.dumps([sample_post(first)])}]))
    changed = source.copy()
    changed['주소'] = '충남 천안시 새주소로 20'
    result, quarantine = merge_verified_tags(changed, pd.DataFrame(), existing=initial, metadata_mode='update')
    assert result.iloc[0]['주소'] == changed.iloc[0]['주소']
    assert result.iloc[0]['blog_tags'] == '{}'
    assert len(quarantine) == 1
    assert first['identity_key'] in json.loads(result.iloc[0]['identity_aliases'])


def test_shared_local_alias_never_mixes_two_known_providers(places):
    local = ensure_ids(places.head(1))
    local_place = local.iloc[0].to_dict()
    providers = pd.concat([local, local], ignore_index=True)
    providers['provider'], providers['provider_place_id'] = 'naver', ['1', '2']
    canonical, _ = merge_verified_tags(providers, pd.DataFrame())
    # Round-trip without the original local row: ambiguous aliases stay ambiguous.
    result, quarantine = merge_verified_tags(canonical, pd.DataFrame([{
        'place_id': local_place['place_id'], 'blog_tag_status': 'verified',
        'verified_posts': json.dumps([sample_post(local_place)])}]), existing=canonical)
    assert set(result['place_id']) == {'naver:1', 'naver:2'}
    assert result['blog_tags'].eq('{}').all()
    assert quarantine['quarantine_reason'].tolist() == ['ambiguous_identity_alias']


def test_persisted_alias_survives_address_update_and_migration(tmp_path, places):
    local = ensure_ids(places.head(1))
    old_key = local.iloc[0]['place_id']
    enriched = local.copy()
    enriched['provider'], enriched['provider_place_id'] = 'naver', '123'
    promoted, _ = merge_verified_tags(enriched, pd.DataFrame(), existing=local)
    changed = promoted.copy()
    changed['주소'] = '충남 천안시 새주소로 20'
    updated, _ = merge_verified_tags(changed, pd.DataFrame(), existing=promoted, metadata_mode='update')
    db = tmp_path / 'places.db'
    write_database(updated, db)
    migrate(db, tmp_path / 'export', apply=True)
    persisted = read_places(db)
    current = persisted.iloc[0].to_dict()
    valid = sample_post(current, 'current')
    wrong = sample_post(local.iloc[0].to_dict(), 'stale')
    result, quarantine = merge_verified_tags(persisted, pd.DataFrame([{
        'place_id': old_key, 'blog_tag_status': 'verified',
        'verified_posts': json.dumps([valid, wrong])}]), existing=persisted)
    assert len(result) == 1
    assert json.loads(result.iloc[0]['blog_tags']) == {'current-tag': 1}
    assert json.loads(result.iloc[0]['verified_posts']) == [valid]
    assert quarantine['quarantine_reason'].tolist() == ['partially_invalid_post_evidence']
