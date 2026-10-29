"""Synthetic-only regressions for stale completion, targeted retry and review history."""
import copy
import hashlib
import json
from blog_evidence import reviewed_tags_post

import pandas as pd
import pytest
import requests

from place_identity import ensure_ids
from Preprocess.RunPreprocess import collect_blog_tags as collector
from Preprocess.RunPreprocess import blog_tag_pilot as pilot

URL = 'https://blog.naver.com/synthetic/1'
GOOD_URL = 'https://blog.naver.com/synthetic/2'


def place(number=123, address='충남 천안시 중앙로 10'):
    return ensure_ids(pd.DataFrame([{'가게명': '테스트카페', '주소': address,
        'provider': 'naver', 'provider_place_id': str(number),
        'latitude': 36.8, 'longitude': 127.1}])).iloc[0].to_dict()


def proof(p, url=URL, tags=None):
    value = {'url': url, 'name_excerpt': p['가게명'] + ' 후기', 'address_excerpt': p['주소'],
            'tags': ['조용한'] if tags is None else tags, 'tag_parser': 'gsTagName'}
    try:
        return reviewed_tags_post(p, value, value['tags'])
    except ValueError:
        return value  # Deliberately malformed evidence fixtures remain unreviewed.


@pytest.fixture
def no_credentials(monkeypatch):
    for module in (collector, pilot):
        monkeypatch.setattr(module, 'load_dotenv', lambda *a, **kw: None)
    monkeypatch.setenv('NAVER_API_ID', 'synthetic')
    monkeypatch.setenv('NAVER_API_SECRET', 'synthetic')
    monkeypatch.setattr(collector.time, 'sleep', lambda _: None)


@pytest.mark.parametrize('posts', ['[]', '{broken', '{}', 'null',
    json.dumps([{'url': URL, 'name_excerpt': '다른카페', 'address_excerpt': '충남 천안시 중앙로 10', 'tags': ['조용한']}]),
    json.dumps([{'url': URL, 'name_excerpt': '테스트카페', 'address_excerpt': '충남 천안시 중앙로 20', 'tags': ['조용한']}]),
    json.dumps([{'url': URL, 'name_excerpt': '테스트카페', 'address_excerpt': '충남 천안시 중앙로 10', 'tags': []}]),
])
def test_verified_flag_and_aggregate_without_current_tagged_proof_are_not_done(posts):
    row = {**place(), 'blog_tag_status': 'verified', 'verified_posts': posts, 'blog_tags': '{"조용한":99}'}
    assert collector._done_ids(pd.DataFrame([row])) == set()


def test_valid_evidence_not_cached_aggregate_decides_completion():
    p = place()
    row = {**p, 'blog_tag_status': 'verified', 'verified_posts': json.dumps([proof(p)]),
           'blog_tags': '{"invented":999}'}
    assert collector._done_ids(pd.DataFrame([row]), True) == {p['place_id']}


def test_targeted_retry_recovers_one_failed_url_and_preserves_transport_history(monkeypatch):
    p = place()
    monkeypatch.setattr(collector, 'search_blog_urls', lambda *a, **kw: ([URL, GOOD_URL], 'fixed query'))
    recovering = False
    calls = []
    def fetch(url, p, query, trace):
        calls.append(url)
        if url == URL and not recovering:
            trace.extend([{'kind': 'page', 'attempt': 1, 'error_type': 'Timeout'},
                          {'kind': 'page', 'attempt': 2, 'error_type': 'Timeout'}])
            raise requests.Timeout('synthetic')
        trace.append({'kind': 'page', 'attempt': 1, 'status_code': 200})
        return proof(p, url)
    monkeypatch.setattr(collector, 'fetch_post', fetch)
    first = collector.collect_with_audit(p, delay=0)
    original = copy.deepcopy(first)
    recovering = True
    resumed = collector.collect_with_audit(p, delay=0, previous=first['audit'], retry_failed=True)
    assert calls == [URL, GOOD_URL, URL]
    assert first == original
    assert resumed['audit']['urls'] == [URL, GOOD_URL]
    assert resumed['audit']['fetch_failure'] == 0
    assert resumed['audit']['identity_accepted'] == 2
    assert len(resumed['audit']['posts']) == 2
    assert resumed['audit']['post_history'][0]['post']['outcome'] == 'fetch_error'
    assert len(resumed['audit']['request_trace']) == 4
    assert resumed['record']['blog_tag_status'] == 'verified'
    collector.collect_with_audit(p, delay=0, previous=resumed['audit'], retry_failed=True)
    assert calls == [URL, GOOD_URL, URL]


def test_stale_interrupted_identity_is_archived_without_blocking_batch(tmp_path, monkeypatch, no_credentials):
    old, current, following = place(), place(address='충남 천안시 중앙로 20'), place(456)
    monkeypatch.setattr(collector, 'search_blog_urls', lambda *a, **kw: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(collector.CollectionInterrupted) as caught:
        collector.collect_with_audit(old)
    checkpoint = {**caught.value.result['audit'], 'record': caught.value.result['record'],
                  'place': old, 'collected_at': '2026-10-15T00:00:00+00:00'}
    source, output = tmp_path / 'places.csv', tmp_path / 'tags.csv'
    pd.DataFrame([current, following]).to_csv(source, index=False)
    audit_dir = tmp_path / 'tags.audit'
    audit_dir.mkdir()
    journal = audit_dir / (hashlib.sha256(old['place_id'].encode()).hexdigest() + '.json')
    journal.write_text(json.dumps(checkpoint, ensure_ascii=False))
    before = journal.read_bytes()
    searched = []
    def search(p, **kwargs):
        searched.append((p['place_id'], p['주소']))
        return [], 'new query'
    monkeypatch.setattr(collector, 'search_blog_urls', search)
    collector.main(source, output)
    assert searched == [(current['place_id'], current['주소']), (following['place_id'], following['주소'])]
    assert len(pd.read_csv(output)) == 2
    assert next(audit_dir.glob('*.history-*.json')).read_bytes() == before
    assert json.loads(journal.read_text())['place_identity']['주소'] == current['주소']


@pytest.fixture
def pilot_run(tmp_path, monkeypatch, no_credentials):
    targets = [place(123 + i) for i in range(5)]
    manifest = {'pilot_id': 'synthetic-resume', 'collection_authorized_now': True}
    monkeypatch.setattr(pilot, 'checked_targets', lambda *a: (manifest, targets))
    output = tmp_path / 'pilot'
    return tmp_path / 'manifest.json', tmp_path / 'unused.db', output, targets


def test_pilot_resume_retries_failed_post_only_and_invalidates_changed_review(pilot_run, monkeypatch):
    path, db, output, targets = pilot_run
    target = targets[0]
    recovering = False
    calls = []
    def search(p, **kwargs):
        return ([URL, GOOD_URL] if p['place_id'] == target['place_id'] else []), 'query'
    def fetch(url, p, query, trace):
        calls.append(url)
        trace.append({'kind': 'page', 'attempt': 1})
        if url == URL and not recovering:
            raise requests.Timeout('synthetic')
        return proof(p, url, ['고요한'] if url == URL else ['조용한'])
    monkeypatch.setattr(collector, 'search_blog_urls', search)
    monkeypatch.setattr(collector, 'fetch_post', fetch)
    pilot.collect(path, db, output)
    review = json.loads((output / 'review.json').read_text())
    for entry in review['entries']:
        entry.update(identity_match=True, approved_taste_tags=['조용한'], notes='manual original')
    pilot.save_json(output / 'review.json', review)
    good = next(e for e in review['entries'] if e['url'] == GOOD_URL)
    recovering = True
    pilot.collect(path, db, output, resume=True)
    assert calls == [URL, GOOD_URL, URL]
    updated = json.loads((output / 'review.json').read_text())
    unchanged = next(e for e in updated['entries'] if e['url'] == GOOD_URL)
    assert {k: unchanged[k] for k in good} == good
    changed = next(e for e in updated['entries'] if e['url'] == URL)
    assert changed['automatic_outcome'] == 'identity_accepted'
    assert changed['identity_match'] is None and changed['approved_taste_tags'] == []
    assert changed['history'][-1]['identity_match'] is True
    assert changed['history'][-1]['notes'] == 'manual original'
    with pytest.raises(ValueError, match='수동 신원 판정'):
        pilot.export_reviewed(path, db, output)
    changed.update(identity_match=True, approved_taste_tags=['고요한'])
    pilot.save_json(output / 'review.json', updated)
    metrics = pilot.export_reviewed(path, db, output)
    assert metrics['precision_denominator'] == 2
    assert metrics['identity_confirmed'] == 2
    pilot.collect(path, db, output, resume=True)
    assert calls == [URL, GOOD_URL, URL]


@pytest.mark.parametrize('current', [place(address='충남 천안시 중앙로 20'), place(456),
                                     {**place(), '가게명': '바뀐카페'}])
def test_done_revalidates_against_current_batch_identity(current):
    old = place()
    cached = {**old, 'blog_tag_status': 'verified', 'verified_posts': json.dumps([proof(old)])}
    assert not collector._done_ids(pd.DataFrame([cached]), current_places=pd.DataFrame([current]))


def test_addressless_proof_cannot_follow_another_provider_or_local_promotion():
    p = place(address='주소없음')
    post = {**proof(p), 'provider_url': 'https://m.place.naver.com/cafe/123/home'}
    post = reviewed_tags_post(p, post, post['tags'])
    cached = {**p, 'blog_tag_status': 'verified', 'verified_posts': json.dumps([post])}
    assert collector._done_ids(pd.DataFrame([cached])) == {'naver:123'}
    for update in ({'provider': 'kakao', 'place_id': 'kakao:123'},
                   {'provider_place_id': '456', 'place_id': 'naver:456'}):
        assert not collector._done_ids(pd.DataFrame([{**cached, **update}]))
    local = {key: value for key, value in cached.items() if key not in ('place_id', 'provider', 'provider_place_id')}
    assert not collector._done_ids(ensure_ids(pd.DataFrame([local])))


def test_http_retry_attempts_and_latest_post_counts_remain_separate(monkeypatch, no_credentials):
    p = place()
    monkeypatch.setattr(collector, 'search_blog_urls', lambda *a, **kw: ([URL], 'query'))
    calls = []
    class Response:
        status_code = 200
        text = '<div class="se-main-container"><p>테스트카페 후기</p><p>충남 천안시 중앙로 10</p></div><script>var gsTagName = "조용한";</script>'
        def raise_for_status(self): pass
    def get(*args, **kwargs):
        calls.append(args[0])
        if len(calls) <= 2:
            raise requests.Timeout('synthetic-private-error')
        return Response()
    monkeypatch.setattr(collector.requests, 'get', get)
    first = collector.collect_with_audit(p, delay=0)
    assert len(calls) == len(first['audit']['request_trace']) == 2
    paused = collector.collect_with_audit(p, previous=first['audit'], delay=0)
    assert len(calls) == 2 and paused['record']['blog_tag_status'] == 'fetch_error'
    resumed = collector.collect_with_audit(p, previous=paused['audit'], retry_failed=True, delay=0)
    assert len(calls) == len(resumed['audit']['request_trace']) == 3
    assert resumed['audit']['identity_accepted'] == 1
    assert resumed['audit']['identity_rejected'] == resumed['audit']['fetch_failure'] == 0
    assert resumed['record']['blog_tag_status'] == 'needs_review'
    assert 'synthetic-private-error' not in json.dumps(resumed)


@pytest.mark.parametrize('status,retried', [(404, False), (403, False), (429, True), (501, True), (503, True)])
def test_only_transient_http_failures_are_targeted(monkeypatch, status, retried):
    p = place()
    monkeypatch.setattr(collector, 'search_blog_urls', lambda *a, **kw: ([URL], 'query'))
    def fail(*a, **kw):
        response = type('Response', (), {'status_code': status})()
        raise requests.HTTPError('synthetic', response=response)
    monkeypatch.setattr(collector, 'fetch_post', fail)
    failed = collector.collect_with_audit(p, delay=0)
    calls = []
    monkeypatch.setattr(collector, 'fetch_post', lambda *a, **kw: (calls.append(URL), proof(p))[1])
    resumed = collector.collect_with_audit(p, previous=failed['audit'], retry_failed=True, delay=0)
    assert len(calls) == int(retried)
    assert resumed['record']['blog_tag_status'] == ('verified' if retried else 'fetch_error')


def test_repeated_manual_retry_is_bounded_and_interrupt_keeps_old_failure(monkeypatch):
    p = place()
    monkeypatch.setattr(collector, 'search_blog_urls', lambda *a, **kw: ([URL, GOOD_URL], 'query'))
    calls = []
    mode = 'fail'
    def fetch(url, p, query, trace):
        calls.append(url)
        trace.append({'kind': 'page', 'attempt': 1})
        if url == URL:
            if mode == 'fail': raise requests.Timeout('synthetic')
            if mode == 'interrupt': raise KeyboardInterrupt()
        return proof(p, url)
    monkeypatch.setattr(collector, 'fetch_post', fetch)
    first = collector.collect_with_audit(p, delay=0)
    again = collector.collect_with_audit(p, delay=0, previous=first['audit'], retry_failed=True)
    assert calls == [URL, GOOD_URL, URL]
    assert len(again['audit']['post_history']) == 1
    assert again['audit']['fetch_failure'] == 1
    mode = 'interrupt'
    with pytest.raises(collector.CollectionInterrupted) as caught:
        collector.collect_with_audit(p, delay=0, previous=again['audit'], retry_failed=True)
    assert caught.value.result['audit']['posts'][0]['outcome'] == 'fetch_error'
    assert len(caught.value.result['audit']['post_history']) == 1
    mode = 'recover'
    final = collector.collect_with_audit(p, delay=0, previous=caught.value.result['audit'], retry_failed=True)
    assert calls.count(GOOD_URL) == 1
    assert len(final['audit']['post_history']) == 2
    assert len(final['audit']['request_trace']) == 5
    assert final['audit']['identity_accepted'] == 2


def test_main_targeted_retry_reuses_journal_even_when_some_tags_are_verified(tmp_path, monkeypatch, no_credentials):
    p = place()
    source, output = tmp_path / 'places.csv', tmp_path / 'tags.csv'
    pd.DataFrame([p]).to_csv(source, index=False)
    searches, calls = [], []
    recovering = False
    def search(*a, **kw):
        searches.append(1)
        return [URL, GOOD_URL], 'query'
    def fetch(url, p, query, trace):
        calls.append(url)
        if url == URL and not recovering: raise requests.Timeout('synthetic')
        return proof(p, url)
    monkeypatch.setattr(collector, 'search_blog_urls', search)
    monkeypatch.setattr(collector, 'fetch_post', fetch)
    collector.main(source, output)
    assert pd.read_csv(output).iloc[0]['blog_tag_status'] == 'verified'
    recovering = True
    collector.main(source, output)
    assert calls == [URL, GOOD_URL]
    collector.main(source, output, retry_failed=True)
    assert calls == [URL, GOOD_URL, URL] and len(searches) == 1
    assert len(json.loads(pd.read_csv(output).iloc[0]['verified_posts'])) == 2
    collector.main(source, output, retry_failed=True)
    assert calls == [URL, GOOD_URL, URL]


def test_same_identity_batch_resumes_only_unattempted_url(tmp_path, monkeypatch, no_credentials):
    p = place()
    source, output = tmp_path / 'places.csv', tmp_path / 'tags.csv'
    pd.DataFrame([p]).to_csv(source, index=False)
    searches, calls = [], []
    def search(*a, **kw):
        searches.append(1)
        return [URL, GOOD_URL], 'query'
    def fetch(url, p, query, trace):
        calls.append(url)
        if len(calls) == 2: raise KeyboardInterrupt()
        return proof(p, url)
    monkeypatch.setattr(collector, 'search_blog_urls', search)
    monkeypatch.setattr(collector, 'fetch_post', fetch)
    with pytest.raises(collector.CollectionInterrupted): collector.main(source, output)
    collector.main(source, output)
    assert searches == [1] and calls == [URL, GOOD_URL, GOOD_URL]
    assert len(json.loads(pd.read_csv(output).iloc[0]['verified_posts'])) == 2


def test_body_unavailable_does_not_claim_an_identity_rejection(monkeypatch):
    monkeypatch.setattr(collector, 'search_blog_urls', lambda *a, **kw: ([URL], 'query'))
    monkeypatch.setattr(collector, 'fetch_post', lambda *a, **kw: None)
    audit = collector.collect_with_audit(place(), delay=0)['audit']
    assert audit['body_unavailable'] == audit['fetch_success'] == 1
    assert audit['identity_accepted'] == audit['identity_rejected'] == 0


@pytest.mark.parametrize('invalid', ['too_many', 'duplicate', 'outside_history'])
def test_retry_cannot_expand_frozen_unique_url_space(monkeypatch, invalid):
    p = place()
    monkeypatch.setattr(collector, 'search_blog_urls', lambda *a, **kw: ([URL], 'query'))
    monkeypatch.setattr(collector, 'fetch_post', lambda *a, **kw: proof(p))
    first = collector.collect_with_audit(p, delay=0)
    audit = first['audit']
    if invalid == 'too_many': audit['urls'] = [f'https://blog.naver.com/synthetic/{i}' for i in range(31)]
    if invalid == 'duplicate': audit['urls'] = [URL, URL]
    if invalid == 'outside_history': audit['post_history'] = [{'post': {'url': GOOD_URL}}]
    monkeypatch.setattr(collector, 'fetch_post', lambda *a, **kw: pytest.fail('invalid resume made a request'))
    with pytest.raises(ValueError): collector.collect_with_audit(p, previous=audit, retry_failed=True, delay=0)


def test_pilot_recovery_after_review_write_failure_requires_new_decision(pilot_run, monkeypatch):
    path, db, output, targets = pilot_run
    p = targets[0]
    recovering = False
    calls = []
    monkeypatch.setattr(collector, 'search_blog_urls', lambda target, **kw:
                        ([URL, GOOD_URL] if target['place_id'] == p['place_id'] else [], 'query'))
    def fetch(url, p, query, trace):
        calls.append(url)
        trace.append({'kind': 'page', 'attempt': 1})
        if url == URL and not recovering: raise requests.Timeout('synthetic')
        return proof(p, url)
    monkeypatch.setattr(collector, 'fetch_post', fetch)
    pilot.collect(path, db, output)
    review = json.loads((output / 'review.json').read_text())
    for entry in review['entries']:
        entry.update(identity_match=True, approved_taste_tags=['조용한'], notes='old manual decision')
    pilot.save_json(output / 'review.json', review)
    metrics = pilot.export_reviewed(path, db, output)
    assert metrics['precision_denominator'] == 1
    assert metrics['potential_false_negatives'] == 0
    assert metrics['http_attempts'] == 2 and metrics['latest_fetch_failures'] == 1
    exported_before = (output / 'reviewed_tags.csv').read_bytes()
    real_save = pilot.save_json
    review_writes = 0
    def fail_review(path, data):
        nonlocal review_writes
        if path == output / 'review.json':
            review_writes += 1
            if review_writes == 2: raise OSError('synthetic review publication failure')
        return real_save(path, data)
    recovering = True
    monkeypatch.setattr(pilot, 'save_json', fail_review)
    with pytest.raises(OSError, match='publication failure'): pilot.collect(path, db, output, resume=True)
    assert not (output / 'reviewed_tags.csv').exists()
    assert next(output.glob('reviewed_tags.history-*.csv')).read_bytes() == exported_before
    with pytest.raises(ValueError, match='최신 글 근거'): pilot.export_reviewed(path, db, output)
    monkeypatch.setattr(pilot, 'save_json', real_save)
    pilot.collect(path, db, output, resume=True)
    assert calls == [URL, GOOD_URL, URL]
    updated = json.loads((output / 'review.json').read_text())
    failed_review = next(e for e in updated['entries'] if e['url'] == URL)
    assert failed_review['identity_match'] is None and len(failed_review['history']) == 1
    good_review = next(e for e in updated['entries'] if e['url'] == GOOD_URL)
    assert good_review['identity_match'] is True and good_review['notes'] == 'old manual decision'
    with pytest.raises(ValueError, match='수동 신원 판정'): pilot.export_reviewed(path, db, output)


def test_legacy_review_without_revision_is_preserved_only_for_same_outcome(pilot_run, monkeypatch):
    path, db, output, targets = pilot_run
    p = targets[0]
    recovering = False
    monkeypatch.setattr(collector, 'search_blog_urls', lambda target, **kw:
                        ([URL, GOOD_URL] if target['place_id'] == p['place_id'] else [], 'query'))
    def fetch(url, p, query, trace):
        if url == URL and not recovering: raise requests.Timeout('synthetic')
        return proof(p, url)
    monkeypatch.setattr(collector, 'fetch_post', fetch)
    pilot.collect(path, db, output)
    review = json.loads((output / 'review.json').read_text())
    for entry in review['entries']:
        entry.pop('post_revision')
        entry.update(identity_match=True, approved_taste_tags=['조용한'], notes='legacy manual')
    pilot.save_json(output / 'review.json', review)
    recovering = True
    pilot.collect(path, db, output, resume=True)
    updated = json.loads((output / 'review.json').read_text())
    assert next(e for e in updated['entries'] if e['url'] == GOOD_URL)['identity_match'] is True
    failed = next(e for e in updated['entries'] if e['url'] == URL)
    assert failed['identity_match'] is None and failed['history'][0]['notes'] == 'legacy manual'


@pytest.mark.parametrize('valid', [False, True])
def test_batch_revalidates_completion_before_skipping(tmp_path, monkeypatch, no_credentials, valid):
    p = place()
    source, output = tmp_path / 'places.csv', tmp_path / 'tags.csv'
    pd.DataFrame([p]).to_csv(source, index=False)
    row = {**p, 'blog_tag_status': 'verified', 'blog_tags': '{"forged":99}',
           'verified_posts': json.dumps([proof(p)] if valid else []), 'collected_at': '2026-10-15'}
    pd.DataFrame([row]).to_csv(output, index=False)
    searches = []
    monkeypatch.setattr(collector, 'search_blog_urls', lambda *a, **kw: (searches.append(1) or [], 'query'))
    collector.main(source, output)
    assert len(searches) == int(not valid)
    if not valid:
        assert pd.read_csv(output).iloc[0]['blog_tag_status'] == 'no_verified_posts'


def test_done_loader_preserves_provider_id_leading_zeros(tmp_path):
    p = place('00123', address='지원하지 않는 주소')
    post = {**proof(p), 'provider_url': 'https://m.place.naver.com/cafe/00123/home'}
    post = reviewed_tags_post(p, post, post['tags'])
    row = {**p, 'blog_tag_status': 'verified', 'verified_posts': json.dumps([post])}
    path = tmp_path / 'tags.csv'
    pd.DataFrame([row]).to_csv(path, index=False)
    assert collector.load_done_set(path) == {'naver:00123'}


def test_batch_failure_waits_for_explicit_retry_without_churning_journal(tmp_path, monkeypatch, no_credentials):
    p = place()
    source, output = tmp_path / 'places.csv', tmp_path / 'tags.csv'
    pd.DataFrame([p]).to_csv(source, index=False)
    calls = []
    monkeypatch.setattr(collector, 'search_blog_urls', lambda *a, **kw: ([URL], 'query'))
    def fail(*a, **kw):
        calls.append(1)
        raise requests.Timeout('synthetic')
    monkeypatch.setattr(collector, 'fetch_post', fail)
    collector.main(source, output)
    journal = next((tmp_path / 'tags.audit').glob('*.json'))
    before = journal.read_bytes()
    collector.main(source, output)
    assert len(calls) == 1 and journal.read_bytes() == before
    assert not list(journal.parent.glob('*.history-*.json'))
    collector.main(source, output, retry_failed=True)
    assert len(calls) == 2
    assert next(journal.parent.glob('*.history-*.json')).read_bytes() == before


def test_paused_failure_does_not_consume_limit_for_later_new_place(tmp_path, monkeypatch, no_credentials):
    first, second = place(), place(456)
    source, output = tmp_path / 'places.csv', tmp_path / 'tags.csv'
    pd.DataFrame([first]).to_csv(source, index=False)
    searches = []
    def search(p, **kw):
        searches.append(p['place_id'])
        return ([URL] if p['place_id'] == first['place_id'] else []), 'query'
    monkeypatch.setattr(collector, 'search_blog_urls', search)
    monkeypatch.setattr(collector, 'fetch_post', lambda *a, **kw: (_ for _ in ()).throw(requests.Timeout('synthetic')))
    collector.main(source, output)
    pd.DataFrame([first, second]).to_csv(source, index=False)
    collector.main(source, output, limit=1)
    assert searches == [first['place_id'], second['place_id']]
    assert len(pd.read_csv(output)) == 2


def test_search_auth_repair_preserves_failure_and_attempt_counts(pilot_run, monkeypatch):
    path, db, output, targets = pilot_run
    calls = []
    class Response:
        def __init__(self, status): self.status_code = status
        def raise_for_status(self):
            if self.status_code >= 400: raise requests.HTTPError('synthetic', response=self)
        def json(self): return {'items': []}
    def get(*a, **kw):
        calls.append(1)
        return Response(401 if len(calls) == 1 else 200)
    monkeypatch.setattr(collector.requests, 'get', get)
    first = pilot.collect(path, db, output)
    assert first['api_requests'] == first['collected_places'] == 1
    restored = pilot.collect(path, db, output, resume=True)
    assert restored['collected_places'] == 5 and restored['api_requests'] == len(calls) == 6
    first_audit = json.loads((output / 'collection-1.json').read_text())['audit']
    assert first_audit['search_history'] == [{'error_type': 'HTTPError', 'http_status': 401}]
    assert 'search_error' not in first_audit
    assert first_audit['identity_accepted'] == first_audit['identity_rejected'] == 0
    assert first_audit['status'] == 'no_verified_posts'


def test_history_collision_never_removes_or_overwrites_prior_bytes(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from Preprocess.RunPreprocess import collection_state as state
    monkeypatch.setattr(state, 'datetime', SimpleNamespace(now=lambda tz: datetime(2026, 10, 20, tzinfo=timezone.utc)))
    monkeypatch.setattr(state.uuid, 'uuid4', lambda: SimpleNamespace(hex='a' * 32))
    source = tmp_path / 'journal.json'
    source.write_bytes(b'old original')
    history = state.archive_file(source)
    source.write_bytes(b'new original')
    with pytest.raises(FileExistsError): state.archive_file(source)
    assert source.read_bytes() == b'new original'
    assert history.read_bytes() == b'old original'


@pytest.mark.parametrize('conflict', [{'provider': 'kakao'}, {'provider_place_id': '456'}])
def test_conflicting_provider_columns_cannot_mark_canonical_place_done(conflict):
    p = place()
    row = {**p, **conflict, 'blog_tag_status': 'verified', 'verified_posts': json.dumps([proof(p)])}
    assert not collector._done_ids(pd.DataFrame([row]))
