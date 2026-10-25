"""Offline regressions for identities, evidence and publication failures."""
import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from blog_evidence import tags_from_posts, verify_post
from place_identity import ensure_ids, quarantine_legacy
from Preprocess.RunPreprocess.build_database import build, merge_verified_tags, read_database, write_database


def proof(place, url='https://blog.naver.com/reviewer/123', tags=None):
    return {'url': url, 'name_excerpt': place['가게명'] + ' 후기',
            'address_excerpt': place['주소'], 'tags': tags or ['valid']}


def verified(place, posts):
    return {'place_id': place['place_id'], 'blog_tag_status': 'verified',
            'verified_posts': json.dumps(posts, ensure_ascii=False)}


def moved_provider(places):
    local = ensure_ids(places.head(1))
    incoming = local.assign(provider='naver', provider_place_id='123')
    promoted, _ = merge_verified_tags(incoming, pd.DataFrame(), existing=local)
    moved = promoted.assign(주소='충남 천안시 새로운길 20')
    current, _ = merge_verified_tags(moved, pd.DataFrame(), existing=promoted, metadata_mode='update')
    return local, current


@pytest.mark.parametrize('replace_all', [False, True])
def test_old_catalog_alias_does_not_resurrect_a_second_place(tmp_path, places, replace_all):
    local, current = moved_provider(places)
    db = tmp_path / 'places.db'
    write_database(current, db)
    local.to_csv(tmp_path / 'old.csv', index=False)
    late = verified(local.iloc[0], [proof(current.iloc[0])])
    pd.DataFrame([late]).to_csv(tmp_path / 'late.csv', index=False)
    stats = build(tmp_path / 'old.csv', tmp_path / 'late.csv', db, replace_all=replace_all)
    actual = read_database(db)
    assert len(actual) == 1
    assert actual.iloc[0]['place_id'] == 'naver:123'
    assert actual.iloc[0]['주소'] == current.iloc[0]['주소']
    assert json.loads(actual.iloc[0]['blog_tags']) == {'valid': 1}
    assert stats['removed_place_ids'] == []


def test_ambiguous_persisted_alias_cannot_promote_metadata(places):
    local, current = moved_provider(places)
    other = current.assign(place_id='kakao:9', provider='kakao', provider_place_id='9')
    result, _ = merge_verified_tags(local, pd.DataFrame(), existing=pd.concat([current, other]))
    assert set(result['place_id']) == {local.iloc[0]['place_id'], 'naver:123', 'kakao:9'}


def test_memory_loader_revalidates_verified_status_and_rebuilds_counts(places):
    source = ensure_ids(places.head(3))
    valid = proof(source.iloc[0])
    source['blog_tag_status'] = 'verified'
    source['blog_tags'] = '{"untrusted": 99}'
    source['verified_posts'] = [json.dumps([valid]), '[]', '{"bad":"shape"}']
    result = quarantine_legacy(source)
    assert json.loads(result.iloc[0]['blog_tags']) == {'valid': 1}
    assert result.iloc[0]['blog_tag_status'] == 'verified'
    assert result.iloc[1:]['blog_tags'].eq('{}').all()
    assert result.iloc[1:]['blog_tag_status'].ne('verified').all()
    assert source['blog_tags'].eq('{"untrusted": 99}').all()


@pytest.mark.parametrize('url', ['https://[broken', 'ftp://blog.naver.com/reviewer/123',
                                 'https://blog.naver.com:bad/reviewer/123',
                                 'https://blog.naver.com/reviewer',
                                 'https://blog.naver.com/PostList.naver?blogId=reviewer'])
def test_malformed_or_non_http_post_urls_fail_closed(places, url):
    p = places.iloc[0]
    assert not verify_post(p, proof(p, url))
    assert tags_from_posts(p, [proof(p, url)]) == ({}, [])


def test_provider_fallback_cannot_mix_provider_namespaces():
    p = {'가게명': '아지트', 'provider': 'kakao', 'provider_place_id': '123'}
    post = {'url': 'https://blog.naver.com/reviewer/123', 'name_excerpt': '아지트 후기',
            'provider_url': 'https://m.place.naver.com/restaurant/123/home', 'tags': ['wrong']}
    assert not verify_post(p, post)


def test_mobile_fragment_and_query_variants_are_one_post_with_latest_priority(places):
    p = ensure_ids(places.head(1)).iloc[0]
    old = proof(p, tags=['old'])
    variant = proof(p, 'https://m.blog.naver.com/reviewer/123?tracking=1#body', ['new'])
    tags, posts = tags_from_posts(p, [old, variant])
    assert len(posts) == 1 and sum(tags.values()) == 1
    current, _ = merge_verified_tags(pd.DataFrame([p]), pd.DataFrame([verified(p, [old])]))
    updated, quarantine = merge_verified_tags(pd.DataFrame([p]), pd.DataFrame([verified(p, [variant])]), existing=current)
    assert json.loads(updated.iloc[0]['blog_tags']) == {'new': 1}
    assert json.loads(updated.iloc[0]['verified_posts']) == [variant]
    assert quarantine.empty


@pytest.mark.parametrize('address', ['천안시 테스트로 1.5', '천안시 테스트로 1/2',
                                     '천안시 테스트로 1－2', '천안시 테스트로 1 - x',
                                     '천안시 테스트로 1／2', '천안시 테스트로 1−2'])
def test_unsupported_building_number_never_matches_a_prefix(places, address):
    p = places.iloc[0]
    assert not verify_post(p, {**proof(p), 'address_excerpt': address})


def test_replace_failure_cleans_stage_and_retains_backup(tmp_path, places, monkeypatch):
    import Preprocess.RunPreprocess.build_database as database
    db = tmp_path / 'places.db'
    source, _ = merge_verified_tags(places.head(1), pd.DataFrame())
    write_database(source, db)
    before = db.read_bytes()
    def fail(*args):
        raise OSError('simulated replacement failure')
    monkeypatch.setattr(database.os, 'replace', fail)
    with pytest.raises(OSError, match='replacement failure'):
        write_database(source, db, preserve=True)
    assert db.read_bytes() == before
    assert len(list(tmp_path.glob('places.db.backup-*'))) == 1
    assert not list(tmp_path.glob('*.tmp'))


def test_wal_database_is_not_replaced_under_an_active_reader(tmp_path, places):
    db = tmp_path / 'places.db'
    source, _ = merge_verified_tags(places.head(1), pd.DataFrame())
    write_database(source, db)
    with sqlite3.connect(db) as live:
        live.execute('PRAGMA journal_mode=WAL')
        live.execute('CREATE TABLE live_metadata (value TEXT)')
        live.commit()
        before = db.read_bytes()
        with pytest.raises(ValueError, match='WAL'):
            write_database(source, db, preserve=True)
        assert db.read_bytes() == before
        assert live.execute('SELECT count(*) FROM places').fetchone()[0] == 1


def test_postview_and_path_urls_share_a_single_post_identity(places):
    p = places.iloc[0]
    posts = [proof(p), proof(p, 'https://blog.naver.com/PostView.naver?blogId=reviewer&logNo=123')]
    assert tags_from_posts(p, posts) == ({'valid': 1}, [posts[0]])


def test_replace_all_does_not_resolve_a_shared_alias_by_deleting_its_other_owner(places):
    local = ensure_ids(places.head(1))
    providers = pd.concat([local, local], ignore_index=True).assign(provider='naver', provider_place_id=['1', '2'])
    canonical, _ = merge_verified_tags(providers, pd.DataFrame())
    late = verified(local.iloc[0], [proof(local.iloc[0])])
    result, quarantine = merge_verified_tags(canonical.head(1), pd.DataFrame([late]), existing=canonical, replace_all=True)
    assert len(result) == 1
    assert result.iloc[0]['blog_tags'] == '{}'
    assert quarantine['quarantine_reason'].tolist() == ['ambiguous_identity_alias']


def test_build_rejects_an_input_snapshot_changed_before_publication(tmp_path, places, monkeypatch):
    import Preprocess.RunPreprocess.build_database as database
    db = tmp_path / 'places.db'
    source, _ = merge_verified_tags(places.head(1), pd.DataFrame())
    write_database(source, db)
    source.to_csv(tmp_path / 'places.csv', index=False)
    merge = database.merge_verified_tags
    def change_after_read(*args, **kwargs):
        result = merge(*args, **kwargs)
        with sqlite3.connect(db) as writer:
            writer.execute('UPDATE places SET 방문자수=987')
        return result
    monkeypatch.setattr(database, 'merge_verified_tags', change_after_read)
    with pytest.raises(ValueError, match='원본 DB가 변경'):
        build(tmp_path / 'places.csv', tmp_path / 'absent.csv', db)
    assert read_database(db).iloc[0]['방문자수'] == 987
    assert not list(tmp_path.glob('*.tmp'))


def test_writer_lock_is_held_through_atomic_publication(tmp_path, places, monkeypatch):
    import Preprocess.RunPreprocess.build_database as database
    db = tmp_path / 'places.db'
    source, _ = merge_verified_tags(places.head(1), pd.DataFrame())
    write_database(source, db)
    replace = database.os.replace
    attempts = []
    def assert_locked(temporary, target):
        with sqlite3.connect(db, timeout=0) as writer:
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                writer.execute('UPDATE places SET 방문자수=123')
        attempts.append(True)
        replace(temporary, target)
    monkeypatch.setattr(database.os, 'replace', assert_locked)
    write_database(source, db, preserve=True)
    assert attempts == [True]
    assert read_database(db).iloc[0]['방문자수'] == 0


def test_duplicate_csv_merges_proof_and_nonempty_metadata(tmp_path, places):
    from Preprocess.RunPreprocess.remove_duplicates import remove_duplicate_places
    source = ensure_ids(places.head(2))
    first = source.iloc[0].to_dict()
    first.update(verified(first, [proof(first)]))
    latest = {**first, 'latitude': None, '방문자수': 999, 'verified_posts': '[]', 'blog_tag_status': 'fetch_error'}
    path = tmp_path / 'places.csv'
    pd.DataFrame([first, latest, source.iloc[1].to_dict()]).to_csv(path, index=False)
    before = path.read_bytes()
    remove_duplicate_places(path)
    result = pd.read_csv(path).set_index('place_id')
    assert len(result) == 2
    assert result.loc[first['place_id'], 'latitude'] == first['latitude']
    assert result.loc[first['place_id'], '방문자수'] == 999
    assert json.loads(result.loc[first['place_id'], 'blog_tags']) == {'valid': 1}
    assert Path(str(path) + '.bak').read_bytes() == before
    remove_duplicate_places(path)
    assert Path(str(path) + '.bak').read_bytes() == before


def test_duplicate_csv_retains_unproven_source_in_audit_sidecar(tmp_path, places):
    from Preprocess.RunPreprocess.remove_duplicates import remove_duplicate_places
    path = tmp_path / 'legacy.csv'
    source = places.head(1).assign(blog_tags='{"unproven":10}')
    pd.concat([source, source]).to_csv(path, index=False)
    remove_duplicate_places(path)
    actual = pd.read_csv(path)
    assert len(actual) == 1 and actual.iloc[0]['blog_tags'] == '{}'
    audit = pd.read_csv(str(path) + '.quarantine.csv')
    assert len(audit) == 1
    assert json.loads(audit.iloc[0]['source_record'])['blog_tags'] == '{"unproven":10}'


def test_csv_cleaner_preserves_header_backups_and_source_on_failure(tmp_path, monkeypatch):
    import Preprocess.RunPreprocess.clean_existing_data as cleaner
    path = tmp_path / 'source.csv'
    path.write_text('가게명,카테고리,추가열\n스타벅스,카페,keep-in-backup\n', encoding='utf-8-sig')
    before = path.read_bytes()
    replace = cleaner.os.replace
    def fail(*args):
        raise OSError('csv replacement failure')
    monkeypatch.setattr(cleaner.os, 'replace', fail)
    with pytest.raises(OSError, match='csv replacement'):
        cleaner.clean_existing_csv_files(tmp_path)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob('*.tmp'))
    monkeypatch.setattr(cleaner.os, 'replace', replace)
    cleaner.clean_existing_csv_files(tmp_path)
    assert pd.read_csv(path).empty
    assert pd.read_csv(path).columns.tolist() == ['가게명', '카테고리', '추가열']
    assert Path(str(path) + '.bak').read_bytes() == before


def test_ambiguous_alias_stays_blocked_after_removed_provider_and_csv_roundtrip(tmp_path, places):
    local = ensure_ids(places.head(1))
    providers = pd.concat([local, local], ignore_index=True).assign(provider='naver', provider_place_id=['1', '2'])
    canonical, _ = merge_verified_tags(providers, pd.DataFrame())
    kept, _ = merge_verified_tags(canonical.head(1), pd.DataFrame(), existing=canonical, replace_all=True)
    kept.to_csv(tmp_path / 'kept.csv', index=False)
    persisted = pd.read_csv(tmp_path / 'kept.csv')
    late = verified(local.iloc[0], [proof(local.iloc[0])])
    result, quarantine = merge_verified_tags(persisted, pd.DataFrame([late]), existing=persisted)
    assert result.iloc[0]['blog_tags'] == '{}'
    assert quarantine['quarantine_reason'].tolist() == ['ambiguous_identity_alias']
    reread, _ = merge_verified_tags(local, pd.DataFrame(), existing=result)
    assert set(reread['place_id']) == {'naver:1', local.iloc[0]['place_id']}


def test_nullable_numeric_provider_ids_never_gain_a_decimal_suffix(places):
    first = places.head(1).assign(provider='naver', provider_place_id=123)
    combined = pd.concat([first, places.iloc[1:2]], ignore_index=True)
    result = ensure_ids(combined)
    assert result.iloc[0]['place_id'] == 'naver:123'
    assert result.iloc[0]['provider_place_id'] == '123'
    assert ensure_ids(first.assign(provider_place_id='00123')).iloc[0]['place_id'] == 'naver:00123'


@pytest.mark.parametrize('value', [float(2 ** 53), float('inf'), 123.5])
def test_unsafe_float_provider_ids_cannot_create_a_different_identity(places, value):
    with pytest.raises(ValueError, match='공급자 ID'):
        ensure_ids(places.head(1).assign(provider='naver', provider_place_id=value))


@pytest.mark.parametrize('partial', [{'provider': 'kakao'}, {'provider_place_id': '2'}])
def test_incomplete_provider_update_cannot_corrupt_a_canonical_pair(places, partial):
    source = ensure_ids(places.head(1).assign(provider='naver', provider_place_id='1'))
    incoming = source.drop(columns=['provider', 'provider_place_id']).assign(**partial)
    with pytest.raises(ValueError, match='불완전한 공급자'):
        merge_verified_tags(incoming, pd.DataFrame(), existing=source, metadata_mode='update')


@pytest.mark.parametrize('mode', ['snapshot', 'update'])
def test_two_partial_provider_rows_cannot_fabricate_a_provider_identity(places, mode):
    source = ensure_ids(places.head(1)).assign(provider='naver')
    partial = source.drop(columns='provider').assign(provider_place_id='123')
    result, _ = merge_verified_tags(partial, pd.DataFrame(), existing=source, metadata_mode=mode)
    assert result.iloc[0]['place_id'] == source.iloc[0]['place_id']
    assert ensure_ids(result).iloc[0]['place_id'] == source.iloc[0]['place_id']


def test_alias_promotion_does_not_discard_a_conflicting_partial_provider(places):
    local = ensure_ids(places.head(1))
    canonical = local.assign(provider='naver', provider_place_id='1')
    with pytest.raises(ValueError, match='불완전한 공급자'):
        merge_verified_tags(local.assign(provider='kakao'), pd.DataFrame(), existing=canonical)
