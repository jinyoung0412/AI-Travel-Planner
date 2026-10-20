import json
import sqlite3
import pandas as pd
import pytest

from place_identity import identity_key, ensure_ids, quarantine_legacy
from blog_evidence import tags_from_posts, verify_post
from Preprocess.RunPreprocess.build_database import merge_verified_tags, write_database
from Preprocess.RunPreprocess.migrate_place_ids import migrate
from Preprocess.RunPreprocess.collect_blog_tags import load_done_set, collect_place_tags
from Preprocess.crawler.saver import touch_init_file, save_item, load_existing_ids


def post(address='충남 천안시 테스트로 1', tags=None):
    return {'url': 'https://blog.naver.com/reviewer/123', 'name_excerpt': '오늘 장소0 방문',
            'address_excerpt': address, 'tags': tags or ['천안맛집']}


def test_names_addresses_normalization_and_recollection(places):
    a = places.iloc[0].to_dict()
    b = {**a, '주소': '충청남도   천안시 테스트로 1'}
    c = {**a, '주소': '충남 천안시 테스트로 2'}
    assert identity_key(a) == identity_key(b)
    assert identity_key(a) != identity_key(c)
    assert len(ensure_ids(pd.DataFrame([a, b, c])).drop_duplicates('place_id')) == 2
    provider = {**a, 'provider': 'naver', 'provider_place_id': '123456'}
    df = ensure_ids(pd.DataFrame([a, provider]))
    assert df['place_id'].tolist() == ['naver:123456', 'naver:123456']
    assert df['identity_key'].nunique() == 1
    assert identity_key(a) == 'local:v1:2f4e6866656d892d2d14e6fa1c033c29be51683bc677fd4e6ae9e5030cc02edc'


def test_coordinates_missing_identity_rejected():
    with pytest.raises(ValueError):
        identity_key({'name': '아지트'})


def test_legacy_wrong_join_never_spreads_tags(places):
    p = places.head(2).copy()
    p['가게명'] = '아지트'
    legacy = pd.DataFrame([{'가게명': '아지트', 'blog_tags': '{"다낭마사지": 10}'}])
    result, quarantine = merge_verified_tags(p, legacy)
    assert len(result) == 2 and result['place_id'].nunique() == 2
    assert result['blog_tags'].eq('{}').all() and len(quarantine) == 1
    # Loading an old DB also fails closed, even before applying migration.
    p['blog_tags'] = legacy.iloc[0]['blog_tags']
    assert quarantine_legacy(p)['blog_tags'].eq('{}').all()


def test_modern_id_join_requires_post_proof_and_deduplicates(places):
    p = ensure_ids(places.head(2))
    p.loc[1, '가게명'] = '장소0'
    p = ensure_ids(p.drop(columns=['place_id', 'identity_key']))
    row = {'place_id': p.iloc[0]['place_id'], 'blog_tag_status': 'verified',
           'blog_tags': '{"untrusted":99}', 'verified_posts': json.dumps([post()], ensure_ascii=False)}
    result, quarantine = merge_verified_tags(p, pd.DataFrame([row, row]))
    assert len(result) == 2 and quarantine.empty
    assert json.loads(result.iloc[0]['blog_tags']) == {'천안맛집': 1}
    assert result.iloc[1]['blog_tags'] == '{}'
    bad = {**row, 'place_id': p.iloc[1]['place_id']}
    result, quarantine = merge_verified_tags(p, pd.DataFrame([bad]))
    assert result['blog_tags'].eq('{}').all() and len(quarantine) == 1


@pytest.mark.parametrize('address', ['다낭 테스트로 1', '수원시 테스트로 1',
                                     '천안시 테스트로 100', '천안시 테스트로 1-2'])
def test_post_address_not_other_city_or_building(places, address):
    assert not verify_post(places.iloc[0].to_dict(), post(address))


def test_evidence_deduplicates_urls_and_rejects_chrome(places):
    valid = post()
    invalid = {**valid, 'name_excerpt': ''}
    tags, evidence = tags_from_posts(places.iloc[0].to_dict(), [invalid, valid, valid])
    assert tags == {'천안맛집': 1} and len(evidence) == 1


def test_resume_identity_and_retry_errors(tmp_path, places):
    path = tmp_path / 'tags.csv'
    pd.DataFrame([{'가게명': '장소0', 'blog_tags': '{}'}]).to_csv(path, index=False)
    assert not load_done_set(path)
    p = ensure_ids(places.head(3))
    data = pd.DataFrame([{'place_id': pid, 'blog_tag_status': status} for pid, status in zip(
        p['place_id'], ['verified', 'fetch_error', 'no_verified_posts'])])
    data.to_csv(path, index=False)
    assert load_done_set(path) == {p.iloc[2]['place_id']}
    assert not load_done_set(path, True)
    # A verified flag now needs actual name/address evidence and tagged posts.
    data = p.assign(blog_tag_status=['verified', 'fetch_error', 'no_verified_posts'])
    post = {'url': 'https://blog.naver.com/reviewer/123', 'name_excerpt': p.iloc[0]['가게명'],
            'address_excerpt': p.iloc[0]['주소'], 'tags': ['조용한']}
    data['verified_posts'] = [json.dumps([post]), '[]', '[]']
    data.to_csv(path, index=False)
    assert load_done_set(path) == {p.iloc[0]['place_id'], p.iloc[2]['place_id']}
    assert load_done_set(path, True) == {p.iloc[0]['place_id']}


def test_collector_checks_body_evidence_with_mocked_http(monkeypatch, places):
    import Preprocess.RunPreprocess.collect_blog_tags as collector
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'items': [{'link': 'https://blog.naver.com/reviewer/123'}]}
        text = '<div class="se-main-container"><p>장소0 방문</p><p>충남 천안시 테스트로 1</p></div><script>var gsTagName = "천안맛집,후기";</script>'
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()
    monkeypatch.setenv('NAVER_API_ID', 'mock')
    monkeypatch.setenv('NAVER_API_SECRET', 'mock')
    monkeypatch.setattr(collector.requests, 'get', get)
    result = collect_place_tags(ensure_ids(places.head(1)).iloc[0].to_dict(), delay=0)
    assert result['blog_tag_status'] == 'verified'
    assert '천안시 테스트로 1' in calls[0][1]['params']['query']
    evidence = json.loads(result['verified_posts'])[0]
    assert evidence['address_excerpt'] and evidence['name_excerpt'] and evidence['query']


def test_migration_backup_quarantine_idempotence(tmp_path, places):
    path = tmp_path / 'places.db'
    p = places.head(3).copy()
    p.loc[:1, '가게명'] = '아지트'
    p['blog_tags'] = '{"다낭마사지":10}'
    p['지역'] = '천안'
    with sqlite3.connect(path) as conn:
        p.to_sql('places', conn, index=False)
    dry = migrate(path, tmp_path / 'audit')
    assert not dry['applied'] and dry['quarantined_tag_records'] == 3
    stats = migrate(path, tmp_path / 'audit', True)
    with sqlite3.connect(stats['backup']) as conn:
        assert conn.execute('select blog_tags from places').fetchone()[0] == '{"다낭마사지":10}'
    with sqlite3.connect(path) as conn:
        assert conn.execute('select count(distinct place_id) from places').fetchone()[0] == 3
        assert conn.execute('select count(*) from blog_tags_quarantine').fetchone()[0] == 3
        assert conn.execute('select count(*) from places where blog_tags <> "{}"').fetchone()[0] == 0
    again = migrate(path, tmp_path / 'audit', True)
    assert again['quarantined_tag_records'] == 0
    with sqlite3.connect(path) as conn:
        assert conn.execute('select count(*) from blog_tags_quarantine').fetchone()[0] == 3
    assert len(pd.read_csv(tmp_path / 'audit/recollect_places.csv')) == 3


def test_crawler_csv_id_resume_and_provider_preserved(tmp_path):
    path = tmp_path / 'crawl.csv'
    touch_init_file(path)
    a = {'name': '아지트', 'address': '충남 천안시 테스트로 1', 'provider': 'naver', 'provider_place_id': '987'}
    b = {**a, 'address': '충남 아산시 테스트로 2', 'provider_place_id': '988'}
    save_item(path, a)
    save_item(path, b)
    assert load_existing_ids(path) == {'naver:987', 'naver:988'}
    df = pd.read_csv(path, dtype={'provider_place_id': str})
    assert len(df) == 2 and df['provider_place_id'].tolist() == ['987', '988']


def test_other_full_name_cannot_prove_identity(places):
    wrong = {**post(), 'name_excerpt': '다낭장소0스파 후기'}
    assert not verify_post(places.iloc[0].to_dict(), wrong)


def test_provider_evidence_requires_naver_domain():
    place = {'name': '아지트', 'provider': 'naver', 'provider_place_id': '123'}
    p = {'url': 'https://blog.naver.com/x/1', 'name_excerpt': '아지트 후기',
         'provider_url': 'https://evil.example/place/123'}
    assert not verify_post(place, p)
    p['provider_url'] = 'https://m.place.naver.com/restaurant/123/home'
    assert verify_post(place, p)


def test_map_geocoding_mocked_and_fails_safely(monkeypatch):
    from Preprocess.RunPreprocess.data_pipeline import get_coords
    import requests
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'documents': [{'x': '127.1139', 'y': '36.8151'}]}
    def mock_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()
    monkeypatch.setattr(requests, 'get', mock_get)
    assert get_coords('충남 천안시 테스트로 1', 'mock-key') == (36.8151, 127.1139)
    assert calls[0][1]['params']['query'] == '충남 천안시 테스트로 1'
    assert calls[0][1]['timeout'] == 10
    def fail(*args, **kwargs): raise requests.Timeout('mock')
    monkeypatch.setattr(requests, 'get', fail)
    assert get_coords('충남 천안시 테스트로 1', 'mock-key') == (None, None)
