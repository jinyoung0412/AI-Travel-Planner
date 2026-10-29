"""Full-review regressions: identity-bound coordinates and proof publication."""
import copy
import hashlib
import itertools
import json
from blog_evidence import reviewed_tags_post
from types import SimpleNamespace

import pandas as pd
import pytest

from blog_evidence import post_url_key, tags_from_posts
from place_identity import ensure_ids, identity_key, quarantine_legacy
from place_quality import coordinate_pair, coordinate_quality, geocode_address_matches
from Preprocess.RunPreprocess import data_pipeline as pipeline
from Preprocess.RunPreprocess.build_database import merge_verified_tags, build, read_database, write_database


def place(address='충남 천안시 중앙로 10', **extra):
    return {'가게명': '검토카페', '주소': address, '카테고리': '카페',
            'provider': 'naver', 'provider_place_id': '00123',
            'latitude': 36.8, 'longitude': 127.1, **extra}


def post(row, number='123'):
    value = {'url': f'https://blog.naver.com/reviewer/{number}',
            'name_excerpt': row['가게명'], 'address_excerpt': row['주소'], 'tags': ['quiet']}
    return reviewed_tags_post(row, value, value['tags'])


@pytest.mark.parametrize('partial', [{}, {'latitude': 36.9}, {'longitude': 127.2},
                                     {'latitude': None, 'longitude': None}])
def test_address_change_never_keeps_or_assembles_the_old_pair(partial):
    old = ensure_ids(pd.DataFrame([place()]))
    update = {'가게명': '검토카페', '주소': '충남 아산시 배방로 99', '카테고리': '카페',
              'provider': 'naver', 'provider_place_id': '00123', **partial}
    result, _ = merge_verified_tags(pd.DataFrame([update]), pd.DataFrame(), existing=old, metadata_mode='update')
    row = result.iloc[0]
    assert row['주소'] == update['주소'] and row['지역'] == '아산'
    assert coordinate_pair(row) is None
    assert not coordinate_quality(row)['recommendation_eligible']
    assert row['coordinate_identity_key'] == identity_key(row)


@pytest.mark.parametrize('partial', [{}, {'latitude': 36.9}, {'longitude': 127.2},
                                     {'latitude': None, 'longitude': None}])
def test_same_address_partial_update_preserves_one_complete_old_pair(partial):
    old = ensure_ids(pd.DataFrame([place(coordinate_source='original')]))
    update = {k: v for k, v in place(**partial).items() if k not in ('latitude', 'longitude') or k in partial}
    update['coordinate_source'] = 'partial_must_not_relabel_old_pair'
    result, _ = merge_verified_tags(pd.DataFrame([update]), pd.DataFrame(), existing=old, metadata_mode='update')
    assert coordinate_pair(result.iloc[0]) == (36.8, 127.1)
    assert result.iloc[0]['coordinate_source'] == 'original'


def test_new_complete_pair_is_bound_and_stale_snapshot_cannot_undo_it(tmp_path):
    old, _ = merge_verified_tags(pd.DataFrame([place()]), pd.DataFrame())
    fresh = pd.DataFrame([place('충남 아산시 배방로 99', latitude=36.7, longitude=127.0,
                                coordinate_source='current')])
    current, _ = merge_verified_tags(fresh, pd.DataFrame(), existing=old, metadata_mode='update')
    db = tmp_path / 'copy.db'
    write_database(current, db)
    old.to_csv(tmp_path / 'stale.csv', index=False)
    for _ in range(3):
        build(tmp_path / 'stale.csv', tmp_path / 'absent.csv', db)
        row = read_database(db).iloc[0]
        assert row['주소'] == fresh.iloc[0]['주소']
        assert coordinate_pair(row) == (36.7, 127.0)
        assert row['coordinate_identity_key'] == identity_key(row)
        assert row['coordinate_source'] == 'current'


def test_stale_explicit_coordinate_binding_is_not_reassigned_by_ensure_ids():
    old = ensure_ids(pd.DataFrame([place()]))
    stale = old.assign(주소='충남 아산시 배방로 99')
    rebound = ensure_ids(stale)
    assert rebound.iloc[0]['coordinate_identity_key'] == old.iloc[0]['identity_key']
    assert not coordinate_quality(rebound.iloc[0])['recommendation_eligible']
    assert 'coordinate_identity_mismatch' in coordinate_quality(rebound.iloc[0])['reason_codes']
    result, _ = merge_verified_tags(stale, pd.DataFrame(), existing=old, metadata_mode='update')
    assert coordinate_pair(result.iloc[0]) is None


@pytest.mark.parametrize('split_pair', [False, True])
def test_pipeline_regeocodes_moved_or_split_pair_and_reuses_only_new_identity(tmp_path, monkeypatch, split_pair):
    source, output = tmp_path / 'source', tmp_path / 'output'
    source.mkdir()
    first = place(category_source='provider')
    last = place('충남 아산시 배방로 99', latitude=None, longitude=None, category_source='provider')
    if split_pair:
        first = place(latitude=36.8, longitude=None, category_source='provider')
        last = place(latitude=None, longitude=127.2, category_source='provider')
    pd.DataFrame([first, last]).to_csv(source / '충남_천안시_카페.csv', index=False)
    calls = []
    monkeypatch.setattr(pipeline, 'get_coords', lambda address, _: calls.append(address) or (36.7, 127.0))
    monkeypatch.setattr(pipeline.time, 'sleep', lambda _: None)
    result = pipeline.run_pipeline(source, output, 'synthetic')
    assert calls == [last['주소']]
    assert result.iloc[0]['place_id'] == 'naver:00123'
    assert coordinate_pair(result.iloc[0]) == (36.7, 127.0)
    assert result.iloc[0]['coordinate_identity_key'] == identity_key(last)
    again = pipeline.run_pipeline(source, output, 'synthetic')
    assert calls == [last['주소']]
    assert coordinate_pair(again.iloc[0]) == (36.7, 127.0)


@pytest.mark.parametrize('cache_kind', ['final', 'checkpoint', 'journal'])
def test_pipeline_rejects_cache_with_wrong_binding_even_if_identity_key_matches(tmp_path, monkeypatch, cache_kind):
    source, output = tmp_path / 'source', tmp_path / 'output'
    source.mkdir(); output.mkdir()
    raw = place(latitude=None, longitude=None)
    pd.DataFrame([raw]).to_csv(source / '충남_천안시_카페.csv', index=False)
    cached = ensure_ids(pd.DataFrame([place()])).iloc[0].to_dict()
    cached['coordinate_identity_key'] = identity_key(place('충남 아산시 배방로 99'))
    if cache_kind == 'journal':
        journal = output / 'geocoding_checkpoint'; journal.mkdir()
        (journal / (hashlib.sha256(cached['place_id'].encode()).hexdigest() + '.json')).write_text(json.dumps(cached))
    else:
        filename = 'chungnam_places_filtered.csv' if cache_kind == 'final' else 'geocoding_checkpoint.csv'
        pd.DataFrame([cached]).to_csv(output / filename, index=False)
    calls = []
    monkeypatch.setattr(pipeline, 'get_coords', lambda address, _: calls.append(address) or (36.9, 127.2))
    monkeypatch.setattr(pipeline.time, 'sleep', lambda _: None)
    result = pipeline.run_pipeline(source, output, 'synthetic')
    assert calls == [raw['주소']]
    assert coordinate_pair(result.iloc[0]) == (36.9, 127.2)


def alias_bridge():
    raw = {k: v for k, v in place().items() if k not in ('provider', 'provider_place_id')}
    local = ensure_ids(pd.DataFrame([raw]))
    moved, _ = merge_verified_tags(local.assign(주소='충남 천안시 중앙로 20'), pd.DataFrame(),
                                    existing=local, metadata_mode='update')
    fresh = ensure_ids(pd.DataFrame([{**raw, '주소': '충남 천안시 중앙로 20'}]))
    return local, moved, fresh


@pytest.mark.parametrize('reverse', [False, True])
def test_provider_alias_closure_has_proof_on_first_build_and_is_idempotent(tmp_path, reverse):
    local, moved, fresh = alias_bridge()
    incoming = pd.concat([pd.DataFrame([place()]), fresh], ignore_index=True)
    if reverse:
        incoming = incoming.iloc[::-1]
    proof = post(fresh.iloc[0])
    tags = pd.DataFrame([{'place_id': fresh.iloc[0]['place_id'], 'blog_tag_status': 'verified',
                          'verified_posts': json.dumps([proof])}])
    first, quarantine = merge_verified_tags(incoming, tags, existing=moved)
    assert quarantine.empty and first['place_id'].tolist() == ['naver:00123']
    assert json.loads(first.iloc[0]['blog_tags']) == {'quiet': 1}
    assert quarantine_legacy(first).drop_duplicates('place_id')['blog_tag_status'].tolist() == ['verified']
    current = first
    for _ in range(3):
        again, _ = merge_verified_tags(current, pd.DataFrame(), existing=current)
        pd.testing.assert_frame_equal(current, again)
        current = again
    # Persist through actual CSV/DB build, not merely an in-memory promotion.
    db = tmp_path / 'copy.db'; write_database(first, db)
    incoming.to_csv(tmp_path / 'input.csv', index=False)
    build(tmp_path / 'input.csv', tmp_path / 'absent.csv', db)
    loaded = read_database(db)
    assert loaded['place_id'].tolist() == ['naver:00123']
    assert loaded.iloc[0]['blog_tag_status'] == 'verified'


def test_alias_conflicts_propagate_before_any_promotion_and_survive_removal(tmp_path):
    local, moved, fresh = alias_bridge()
    # The bridge connects provider P at the old address to Q at the new one.
    records = [place(), {**fresh.iloc[0].to_dict(), 'provider': 'kakao', 'provider_place_id': '9'},
               moved.iloc[0].to_dict(), fresh.iloc[0].to_dict()]
    expected = {'naver:00123', 'kakao:9', local.iloc[0]['place_id'], fresh.iloc[0]['place_id']}
    for ordered in itertools.permutations(records):
        result = ensure_ids(pd.DataFrame(ordered))
        assert set(result['place_id']) == expected
        assert all(set(owners) == {'naver:00123', 'kakao:9'}
                   for conflicts in result['identity_alias_conflicts'] for owners in json.loads(conflicts).values())
    canonical, _ = merge_verified_tags(pd.DataFrame(records), pd.DataFrame())
    kept, _ = merge_verified_tags(canonical[canonical['place_id'].eq('naver:00123')], pd.DataFrame(),
                                  existing=canonical, replace_all=True)
    kept.to_csv(tmp_path / 'kept.csv', index=False)
    persisted = pd.read_csv(tmp_path / 'kept.csv', dtype={'provider_place_id': str})
    actual, _ = merge_verified_tags(fresh, pd.DataFrame(), existing=persisted)
    assert set(actual['place_id']) == {'naver:00123', fresh.iloc[0]['place_id']}


def test_runtime_loader_unions_valid_posts_before_canonical_deduplication():
    local, moved, fresh = alias_bridge()
    provider = {**moved.iloc[0].to_dict(), 'place_id': 'naver:00123', 'provider': 'naver',
                'provider_place_id': '00123', 'blog_tag_status': 'needs_collection'}
    proven = {**fresh.iloc[0].to_dict(), 'blog_tag_status': 'verified',
              'verified_posts': json.dumps([post(fresh.iloc[0])]), 'blog_tags': '{}'}
    visible = quarantine_legacy(pd.DataFrame([provider, proven])).drop_duplicates('place_id')
    assert len(visible) == 1 and json.loads(visible.iloc[0]['blog_tags']) == {'quiet': 1}


@pytest.mark.parametrize('url', [
    'https://blog.naver.com/reviewer/invalid-post-name',
    'https://blog.naver.com/a.b/123', 'https://blog.naver.com/reviewer/１２３',
    'https://blog.naver.com/PostView.naver?blogId=x&logNo=not-a-number',
    'https://blog.naver.com/PostView.naver?blogId=x&logNo=1&logNo=',
    'https://blog.naver.com/PostView.naver?blogId=x&blogId=&logNo=1',
    'https://blog.naver.com/PostView.naver?blogId=x&logNo=1&logNo=2',
    'https://blog.naver.com/reviewer/123?logNo=2',
    'https://blog.naver.com/reviewer/123?blogId=another',
    'https://blog.naver.com/reviewer/123?logNo=123&logNo=123',
    'https://blog.naver.com/reviewer/123?blogId=reviewer&blogId=',
    'https://blog.naver.com/reviewer/1/more', 'https://blog.naver.com:444/reviewer/1',
])
def test_post_url_ingress_rules_apply_to_merge_and_runtime(url):
    row = ensure_ids(pd.DataFrame([place()])).iloc[0].to_dict()
    invalid = {**post(row), 'url': url}
    evidence = {'blog_tag_status': 'verified', 'verified_posts': json.dumps([invalid])}
    assert post_url_key(url) == '' and tags_from_posts(row, [invalid]) == ({}, [])
    runtime = quarantine_legacy(pd.DataFrame([{**row, **evidence}]))
    merged, quarantine = merge_verified_tags(pd.DataFrame([row]), pd.DataFrame([{'place_id': row['place_id'], **evidence}]))
    assert runtime.iloc[0]['blog_tags'] == merged.iloc[0]['blog_tags'] == '{}'
    assert len(quarantine) == 1


def test_valid_blog_url_variants_share_key_and_preserve_original_evidence():
    row = place()
    urls = ['https://blog.naver.com/reviewer/123', 'http://m.blog.naver.com/reviewer/123?tracking=1#body',
            'https://blog.naver.com/reviewer/123?blogId=reviewer&logNo=123&tracking=1',
            'https://blog.naver.com/PostView.naver?logNo=123&blogId=reviewer&tracking=1']
    assert {post_url_key(url) for url in urls} == {'reviewer/123'}
    original = {**post(row), 'url': urls[1]}
    assert tags_from_posts(row, [original, post(row)]) == ({'quiet': 1}, [original])


def geocode_doc():
    road = {'address_name': '충청남도 천안시 서북구 중앙로 10-2', 'region_1depth_name': '충청남도',
            'region_2depth_name': '천안시 서북구', 'region_3depth_name': '성정동',
            'road_name': '중앙로', 'main_building_no': '10', 'sub_building_no': '2', 'underground_yn': 'N'}
    lot = {'address_name': '충청남도 천안시 서북구 성정동 123-4', 'region_1depth_name': '충청남도',
           'region_2depth_name': '천안시 서북구', 'region_3depth_name': '성정동',
           'main_address_no': '123', 'sub_address_no': '4', 'mountain_yn': 'N'}
    return {'address_type': 'ROAD_ADDR', 'address_name': road['address_name'],
            'road_address': road, 'address': lot, 'y': '36.8', 'x': '127.1'}


@pytest.mark.parametrize('address_query', ['충남 천안시 서북구 중앙로 10-2', '충청남도 천안시 서북구 중앙로 10 - 2',
                                     '천안시 중앙로 10-2', '충남 천안시 서북구 성정동 123-4'])
def test_structured_geocode_accepts_normalization_and_explicit_road_lot_link(monkeypatch, address_query):
    doc = geocode_doc()
    monkeypatch.setattr(pipeline, '_get', lambda *a, **k: SimpleNamespace(json=lambda: {'documents': [doc]}))
    assert geocode_address_matches(address_query, doc)
    # get_coords retains the pre-existing specific-address policy. Its input
    # needs compact ASCII subnumbers, even if the comparison helper is broader.
    assert pipeline.get_coords(address_query.replace('10 - 2', '10-2'), 'synthetic') == (36.8, 127.1)


@pytest.mark.parametrize('address_query', ['충남 아산시 서북구 중앙로 10-2', '충북 천안시 서북구 중앙로 10-2',
    '충남 천안시 동남구 중앙로 10-2', '충남 천안시 서북구 서부중앙로 10-2',
    '충남 천안시 서북구 중앙로 10', '충남 천안시 서북구 중앙로 100-2',
    '충남 천안시 서북구 중앙로 10-20', '충남 천안시 서북구 중앙로 10/2',
    '충남 천안시 서북구 중앙로 10.5', '충남 천안시 서북구 성정동 123',
    '충남 천안시 서북구 성정동 산 123-4'])
def test_geocode_rejects_other_region_road_building_and_lot_boundaries(address_query):
    assert not geocode_address_matches(address_query, geocode_doc())


@pytest.mark.parametrize('missing', ['road_address', 'address'])
def test_road_lot_conversion_without_both_structured_forms_is_rejected(missing):
    doc = geocode_doc(); doc.pop(missing)
    assert not geocode_address_matches('충남 천안시 서북구 성정동 123-4', doc)


@pytest.mark.parametrize('field,value', [('road_name', '서부중앙로'), ('main_building_no', '100'),
                                        ('sub_building_no', '20'), ('region_2depth_name', '아산시'),
                                        ('underground_yn', 'Y')])
def test_matching_primary_text_cannot_override_conflicting_structured_road(field, value):
    doc = geocode_doc(); doc['road_address'][field] = value
    assert not geocode_address_matches('충남 천안시 서북구 중앙로 10-2', doc)


def test_land_lot_primary_response_can_prove_requested_road_only_with_explicit_link():
    doc = geocode_doc(); doc['address_type'] = 'REGION_ADDR'; doc['address_name'] = doc['address']['address_name']
    assert geocode_address_matches('충남 천안시 서북구 중앙로 10-2', doc)
    doc['address']['region_2depth_name'] = '아산시'
    assert not geocode_address_matches('충남 천안시 서북구 중앙로 10-2', doc)


@pytest.mark.parametrize('ambiguous', [False, True])
def test_geocoder_selects_only_unique_matching_pair_not_first_result(monkeypatch, ambiguous):
    exact = geocode_doc()
    other = {**exact, 'address_name': '서울 강남구 테헤란로 152', 'address_type': 'ROAD_ADDR', 'y': '37.5'}
    docs = [other, exact]
    if ambiguous: docs.append({**copy.deepcopy(exact), 'y': '36.9'})
    monkeypatch.setattr(pipeline, '_get', lambda *a, **k: SimpleNamespace(json=lambda: {'documents': docs}))
    assert pipeline.get_coords('충남 천안시 서북구 중앙로 10-2', 'synthetic') == ((None, None) if ambiguous else (36.8, 127.1))


def test_mismatched_geocode_response_never_enters_successful_pipeline_checkpoint(tmp_path, monkeypatch):
    source, output = tmp_path / 'source', tmp_path / 'output'; source.mkdir()
    raw = place(latitude=None, longitude=None)
    pd.DataFrame([raw]).to_csv(source / '충남_천안시_카페.csv', index=False)
    wrong = {'address_type': 'ROAD_ADDR', 'address_name': '서울 강남구 테헤란로 152', 'y': '37.5', 'x': '127.0365'}
    calls = []
    monkeypatch.setattr(pipeline, '_get', lambda *a, **k: calls.append(k['params']['query']) or SimpleNamespace(json=lambda: {'documents': [wrong]}))
    monkeypatch.setattr(pipeline.time, 'sleep', lambda _: None)
    for _ in range(2):
        with pytest.raises(ValueError, match='좌표'): pipeline.run_pipeline(source, output, 'synthetic')
    assert len(calls) == 2  # A failed result was not restored as a usable pair.
    assert not (output / 'chungnam_places_filtered.csv').exists()
    assert pd.read_csv(output / 'preprocess_rejected.csv').iloc[0]['preprocess_error'] == 'geocoding_failed'
