"""Synthetic HTML/HTTP fixtures only; no claim about the current live DOM."""
import json
import pandas as pd
import pytest
import requests

from place_identity import ensure_ids
from Preprocess.RunPreprocess import blog_tag_pilot as pilot
from Preprocess.RunPreprocess import collect_blog_tags as collector
from Preprocess.RunPreprocess.build_database import merge_verified_tags, write_database


@pytest.fixture
def prepared(tmp_path, places):
    # Name the synthetic places before binding their synthetic coordinates.
    source = places.head(5).copy()
    source.loc[:1, '가게명'] = '동명카페'
    source = ensure_ids(source)
    frame, _ = merge_verified_tags(source, pd.DataFrame())
    db = tmp_path / 'places.db'
    write_database(frame, db, pd.DataFrame([{'source_record': '{"legacy":1}', 'quarantine_reason': 'legacy'}]))
    manifest = {'pilot_id': 'synthetic-test', 'max_places': 5, 'max_unique_posts_per_place': 30,
                'baseline_db_sha256': pilot.digest(db), 'baseline_place_count': 5,
                'baseline_quarantine_count': 1, 'collection_authorized_now': False,
                'targets': frame.to_dict('records')}
    path = tmp_path / 'manifest.json'
    pilot.save_json(path, manifest)
    return path, db, tmp_path / 'output', manifest


def test_preparation_is_readonly_and_honest_about_no_evidence(prepared):
    path, db, output, manifest = prepared
    before = db.read_bytes()
    report = pilot.prepare(path, db, output)
    assert report['state'] == 'not_attempted_user_deferred'
    assert report['api_requests'] == report['precision_denominator'] == 0
    assert report['identity_precision'] is None
    assert report['actual_taste_restoration'] is False
    assert len(pd.read_csv(output / 'targets.csv')) == 5
    review = {'pilot_id': manifest['pilot_id'], 'entries': [{'notes': 'preserve manual work'}]}
    pilot.save_json(output / 'review.json', review)
    pilot.prepare(path, db, output)
    assert json.loads((output / 'review.json').read_text()) == review
    assert before == db.read_bytes()
    with pytest.raises(ValueError, match='수집 준비'):
        pilot.collect(path, db, output)


@pytest.mark.parametrize('change', ['count', 'duplicate', 'metadata', 'hash', 'limit'])
def test_frozen_targets_fail_closed(prepared, change):
    path, db, output, manifest = prepared
    if change == 'count': manifest['targets'].pop()
    if change == 'duplicate': manifest['targets'][1] = manifest['targets'][0]
    if change == 'metadata': manifest['targets'][0]['주소'] = '충남 수원시 다른로 1'
    if change == 'hash': manifest['baseline_db_sha256'] = 'wrong'
    if change == 'limit': manifest['max_unique_posts_per_place'] = 31
    pilot.save_json(path, manifest)
    with pytest.raises(ValueError):
        pilot.prepare(path, db, output)
    assert not output.exists()


def test_authorized_fixture_still_requires_credentials_before_requests(prepared, monkeypatch):
    path, db, output, manifest = prepared
    manifest['collection_authorized_now'] = True
    pilot.save_json(path, manifest)
    monkeypatch.delenv('NAVER_API_ID', raising=False)
    monkeypatch.delenv('NAVER_API_SECRET', raising=False)
    with pytest.raises(ValueError, match='외부 요청 0회'):
        pilot.collect(path, db, output)


def collection_fixture(prepared):
    path, db, output, manifest = prepared
    pilot.prepare(path, db, output)
    target = manifest['targets'][0]
    post = {'url': 'https://blog.naver.com/synthetic/1', 'name_excerpt': target['가게명'],
            'address_excerpt': target['주소'], 'tags': ['조용한', '서이추', '천안'],
            'outcome': 'identity_accepted'}
    wrong = {**post, 'url': 'https://blog.naver.com/synthetic/2', 'outcome': 'identity_rejected'}
    pilot.save_json(output / 'collection.json', {'pilot_id': manifest['pilot_id'],
                    'runs': [{'place_id': target['place_id'], 'audit': {'posts': [post, wrong]}}]})
    review = {'pilot_id': manifest['pilot_id'], 'entries': [
        {'place_id': target['place_id'], 'url': post['url'], 'identity_match': True,
         'approved_taste_tags': ['조용한']},
        {'place_id': target['place_id'], 'url': wrong['url'], 'identity_match': True,
         'approved_taste_tags': ['조용한']}]}
    pilot.save_json(output / 'review.json', review)
    return review


def test_review_export_separates_identity_from_taste_and_never_applies(prepared):
    path, db, output, manifest = prepared
    collection_fixture(prepared)
    before = db.read_bytes()
    report = pilot.export_reviewed(path, db, output)
    assert report['identity_precision'] == 1 and report['precision_denominator'] == 1
    assert report['potential_false_negatives'] == 1  # cannot force rejected post into DB
    assert report['places_with_reviewed_taste'] == 1 and not report['db_applied']
    rows = pd.read_csv(output / 'reviewed_tags.csv')
    proof = json.loads(rows.iloc[0]['verified_posts'])
    assert len(proof) == 1 and proof[0]['tags'] == ['조용한']
    pilot.export_reviewed(path, db, output)
    assert db.read_bytes() == before
    with pytest.raises(ValueError, match='미실행 보고서'):
        pilot.prepare(path, db, output)


def test_reviewed_export_only_changes_target_tags_in_temporary_database(prepared):
    from Preprocess.RunPreprocess.build_database import build, read_database
    path, db, output, manifest = prepared
    collection_fixture(prepared)
    pilot.export_reviewed(path, db, output)
    before = read_database(db).set_index('place_id').sort_index()
    selected = manifest['targets'][0]['place_id']
    # This DB is a synthetic pytest fixture, never the operational source.
    build(output / 'targets.csv', output / 'reviewed_tags.csv', db)
    after = read_database(db).set_index('place_id').sort_index()
    assert set(before.index) == set(after.index)
    pd.testing.assert_frame_equal(before.drop(selected), after.drop(selected), check_like=True)
    assert json.loads(after.loc[selected, 'blog_tags']) == {'조용한': 1}
    assert after.loc[manifest['targets'][1]['place_id'], 'blog_tags'] == '{}'
    build(output / 'targets.csv', output / 'reviewed_tags.csv', db)
    pd.testing.assert_frame_equal(after, read_database(db).set_index('place_id').sort_index())


def test_human_rejection_leaves_no_taste_export(prepared):
    path, db, output, _ = prepared
    review = collection_fixture(prepared)
    review['entries'][0]['identity_match'] = False
    pilot.save_json(output / 'review.json', review)
    metrics = pilot.export_reviewed(path, db, output)
    assert metrics['identity_precision'] == 0 and metrics['precision_denominator'] == 1
    assert metrics['places_with_reviewed_taste'] == 0
    assert pd.read_csv(output / 'reviewed_tags.csv').empty


def test_pilot_auth_failure_stops_without_collecting_remaining_targets(prepared, monkeypatch):
    path, db, output, manifest = prepared
    manifest['collection_authorized_now'] = True
    pilot.save_json(path, manifest)
    monkeypatch.setenv('NAVER_API_ID', 'synthetic')
    monkeypatch.setenv('NAVER_API_SECRET', 'synthetic')
    monkeypatch.setattr(collector.requests, 'get', lambda *a, **kw: Response(status=401))
    result = pilot.collect(path, db, output)
    assert result['collected_places'] == result['api_requests'] == 1
    assert len(json.loads((output / 'collection.json').read_text())['remaining_targets']) == 4
    with pytest.raises(ValueError, match='기존 수집 기록'):
        pilot.collect(path, db, output)


@pytest.mark.parametrize('tags', [['서이추'], ['서이추환영'], ['천안'], ['추출되지않은태그']])
def test_review_cannot_export_engagement_or_invented_tags(prepared, tags):
    path, db, output, _ = prepared
    review = collection_fixture(prepared)
    review['entries'][0]['approved_taste_tags'] = tags
    pilot.save_json(output / 'review.json', review)
    with pytest.raises(ValueError, match='취향 태그'):
        pilot.export_reviewed(path, db, output)
    assert not (output / 'reviewed_tags.csv').exists()


def test_review_requires_explicit_identity_decision(prepared):
    path, db, output, _ = prepared
    review = collection_fixture(prepared)
    review['entries'][0]['identity_match'] = None
    pilot.save_json(output / 'review.json', review)
    with pytest.raises(ValueError, match='수동 신원 판정'):
        pilot.export_reviewed(path, db, output)


class Response:
    def __init__(self, status=200, items=None, html=''):
        self.status_code, self.items, self.text = status, items or [], html
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError('synthetic HTTP failure', response=self)
    def json(self): return {'items': self.items}


def test_search_deduplicates_and_limits_to_30_naver_urls(monkeypatch, places):
    monkeypatch.setenv('NAVER_API_ID', 'synthetic-secret-id')
    monkeypatch.setenv('NAVER_API_SECRET', 'synthetic-secret-key')
    items = [{'link': f'https://blog.naver.com/synthetic/{i}'} for i in range(40)]
    items += [items[0], {'link': 'https://blog.naver.com.evil.example/1'}]
    monkeypatch.setattr(collector.requests, 'get', lambda *a, **kw: Response(items=items))
    urls, query = collector.search_blog_urls(places.iloc[0].to_dict())
    assert len(urls) == len(set(urls)) == 30 and '테스트로 1' in query
    with pytest.raises(ValueError):
        collector.search_blog_urls(places.iloc[0].to_dict(), display=31)


@pytest.mark.parametrize('failure', ['timeout', 'server', 'unauthorized'])
def test_bounded_retry_and_safe_error_audit(monkeypatch, places, failure):
    monkeypatch.setenv('NAVER_API_ID', 'synthetic-secret-id')
    monkeypatch.setenv('NAVER_API_SECRET', 'synthetic-secret-key')
    monkeypatch.setattr(collector.time, 'sleep', lambda _: None)
    calls = []
    def get(*args, **kwargs):
        calls.append(1)
        if failure == 'timeout': raise requests.Timeout('synthetic-secret-key')
        return Response(status=503 if failure == 'server' else 401)
    monkeypatch.setattr(collector.requests, 'get', get)
    result = collector.collect_with_audit(ensure_ids(places.head(1)).iloc[0].to_dict(), delay=0)
    assert result['record']['blog_tag_status'] == 'fetch_error'
    assert len(calls) == (1 if failure == 'unauthorized' else 2)
    assert len(result['audit']['request_trace']) == len(calls)
    assert 'synthetic-secret' not in json.dumps(result)


def test_empty_results_and_unsupported_body_are_distinct(monkeypatch, places):
    monkeypatch.setenv('NAVER_API_ID', 'synthetic')
    monkeypatch.setenv('NAVER_API_SECRET', 'synthetic')
    place = ensure_ids(places.head(1)).iloc[0].to_dict()
    monkeypatch.setattr(collector.requests, 'get', lambda *a, **kw: Response())
    empty = collector.collect_with_audit(place, delay=0)
    assert empty['record']['blog_tag_status'] == 'no_verified_posts'
    assert empty['audit']['search_returned_urls'] == 0
    def get(url, **kwargs):
        return Response(items=[{'link': 'https://blog.naver.com/synthetic/1'}], html='<p>unsupported DOM</p>')
    monkeypatch.setattr(collector.requests, 'get', get)
    unsupported = collector.collect_with_audit(place, delay=0)
    assert unsupported['record']['blog_tag_status'] == 'parse_unavailable'
    assert unsupported['audit']['body_unavailable'] == 1


@pytest.mark.parametrize('selector', ['class="se-main-container"', 'id="postViewArea"'])
def test_synthetic_html_captures_short_proof_not_full_article(places, selector):
    place = ensure_ids(places.head(1)).iloc[0].to_dict()
    html = f'<div {selector}><p>장소0 후기</p><p>충남 천안시 테스트로 1</p><p>PRIVATE ARTICLE</p></div>'
    html += '<script>var gsTagName = "조용한,서이추";</script>'
    post = collector.parse_post_html(html, 'https://blog.naver.com/synthetic/1', place, 'synthetic query')
    assert post['tag_parser'] == 'gsTagName' and post['tags'] == ['조용한', '서이추']
    assert 'PRIVATE ARTICLE' not in json.dumps(post)
    assert collector.parse_post_html('<html>no body</html>', post['url'], place, '') is None


def test_supported_identity_without_tag_payload_remains_retryable(monkeypatch, places):
    place = ensure_ids(places.head(1)).iloc[0].to_dict()
    monkeypatch.setattr(collector, 'search_blog_urls', lambda *a, **kw: (['https://blog.naver.com/test/1'], 'query'))
    monkeypatch.setattr(collector, 'fetch_post', lambda url, *a, **kw: {
        'url': url, 'name_excerpt': place['가게명'], 'address_excerpt': place['주소'],
        'tags': [], 'tag_parser': 'no_supported_tag_payload'})
    result = collector.collect_with_audit(place, delay=0)
    assert result['audit']['identity_accepted'] == 1
    assert result['record']['blog_tag_status'] == 'parse_unavailable'


def test_interrupt_checkpoints_and_resume_does_not_repeat_completed_posts(prepared, monkeypatch):
    path, db, output, manifest = prepared
    manifest['collection_authorized_now'] = True
    pilot.save_json(path, manifest)
    monkeypatch.setenv('NAVER_API_ID', 'synthetic')
    monkeypatch.setenv('NAVER_API_SECRET', 'synthetic')
    monkeypatch.setattr(collector.time, 'sleep', lambda _: None)
    calls = []
    def search(place, **kwargs):
        calls.append(('search', place['place_id']))
        return ['https://blog.naver.com/synthetic/1', 'https://blog.naver.com/synthetic/2'], 'query'
    def fetch(url, place, query, **kwargs):
        calls.append(('fetch', place['place_id'], url))
        if len(calls) == 3: raise KeyboardInterrupt()
        return {'url': url, 'name_excerpt': place['가게명'], 'address_excerpt': place['주소'],
                'tags': ['조용한'], 'tag_parser': 'gsTagName'}
    monkeypatch.setattr(collector, 'search_blog_urls', search)
    monkeypatch.setattr(collector, 'fetch_post', fetch)
    before = db.read_bytes()
    with pytest.raises(collector.CollectionInterrupted): pilot.collect(path, db, output)
    saved = json.loads((output / 'collection.json').read_text())
    assert saved['runs'][0]['audit']['status'] == 'interrupted'
    assert len(saved['runs'][0]['audit']['posts']) == 1 and len(saved['remaining_targets']) == 5
    review = json.loads((output / 'review.json').read_text())
    review['entries'][0].update(identity_match=True, approved_taste_tags=['조용한'], notes='keep manual decision')
    pilot.save_json(output / 'review.json', review)
    result = pilot.collect(path, db, output, resume=True)
    assert result['collected_places'] == 5
    assert len([c for c in calls if c[0] == 'search']) == 5
    assert calls.count(('fetch', manifest['targets'][0]['place_id'], 'https://blog.naver.com/synthetic/1')) == 1
    assert json.loads((output / 'review.json').read_text())['entries'][0] == review['entries'][0]
    assert db.read_bytes() == before
    pilot.collect(path, db, output, resume=True)
    assert len(calls) == 16  # 5 searches + 10 completed fetches + 1 interrupted fetch


@pytest.mark.parametrize('tag', ['#서이추', '서 이 추', '이벤트', '행사안내', '천안시', '', '  '])
def test_extracted_generic_tags_cannot_be_approved(prepared, tag):
    path, db, output, _ = prepared
    review = collection_fixture(prepared)
    collection = json.loads((output / 'collection.json').read_text())
    collection['runs'][0]['audit']['posts'][0]['tags'].append(tag)
    pilot.save_json(output / 'collection.json', collection)
    review['entries'][0]['approved_taste_tags'] = [tag]
    pilot.save_json(output / 'review.json', review)
    with pytest.raises(ValueError, match='취향 태그'): pilot.export_reviewed(path, db, output)


def test_review_from_unknown_post_is_rejected(prepared):
    path, db, output, manifest = prepared
    review = collection_fixture(prepared)
    review['entries'].append({'place_id': manifest['targets'][0]['place_id'], 'url': 'https://blog.naver.com/x/999',
                              'identity_match': True, 'approved_taste_tags': []})
    pilot.save_json(output / 'review.json', review)
    with pytest.raises(ValueError, match='수집 기록 밖'): pilot.export_reviewed(path, db, output)


def test_blog_url_variants_count_as_one_unique_post(monkeypatch, places):
    monkeypatch.setenv('NAVER_API_ID', 'synthetic')
    monkeypatch.setenv('NAVER_API_SECRET', 'synthetic')
    urls = ['https://blog.naver.com/synthetic/1?tracking=true', 'http://m.blog.naver.com/synthetic/1#tag',
            'https://blog.naver.com/PostView.naver?blogId=synthetic&logNo=1',
            'file://blog.naver.com/synthetic/2', 'https://blog.naver.com.evil/synthetic/3']
    monkeypatch.setattr(collector.requests, 'get', lambda *a, **kw: Response(items=[{'link': url} for url in urls]))
    assert collector.search_blog_urls(places.iloc[0].to_dict())[0] == ['https://blog.naver.com/synthetic/1']


def test_resume_rejects_changed_identity_before_request(monkeypatch, places):
    place = ensure_ids(places.head(1)).iloc[0].to_dict()
    monkeypatch.setattr(collector, 'search_blog_urls', lambda *a, **kw: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(collector.CollectionInterrupted) as caught: collector.collect_with_audit(place)
    with pytest.raises(ValueError, match='ID'):
        collector.collect_with_audit({**place, '주소': '다른 주소'}, previous=caught.value.result['audit'])
