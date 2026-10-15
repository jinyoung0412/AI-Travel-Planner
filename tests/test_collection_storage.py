import json
import pandas as pd
import pytest
import requests

from place_identity import ensure_ids
from Preprocess.crawler.storage import atomic_output
from Preprocess.crawler.http_client import get
from Preprocess.RunPreprocess import collect_blog_tags as collector


def test_atomic_checkpoint_keeps_old_file_on_interrupt(tmp_path):
    path = tmp_path / 'checkpoint.json'
    path.write_text('{"old":true}')
    with pytest.raises(KeyboardInterrupt):
        with atomic_output(path) as stream:
            stream.write('{"partial":')
            raise KeyboardInterrupt()
    assert json.loads(path.read_text()) == {'old': True}
    assert sorted(p.name for p in tmp_path.iterdir()) == ['checkpoint.json']


def test_unvalidated_redirect_is_rejected_at_network_boundary(monkeypatch):
    calls = []
    class Response:
        status_code = 302
    def mocked(*args, **kwargs):
        calls.append(kwargs)
        return Response()
    monkeypatch.setattr(requests, 'get', mocked)
    trace = []
    with pytest.raises(requests.HTTPError): get('https://blog.naver.com/x/1', trace=trace)
    assert calls == [{'allow_redirects': False}]
    assert trace == [{'kind': 'page', 'attempt': 1, 'status_code': 302}]


def test_legacy_blog_header_is_backed_up_and_rows_stay_aligned(tmp_path, places, monkeypatch):
    source, output = tmp_path / 'places.csv', tmp_path / 'blog_tags.csv'
    selected = ensure_ids(places.head(2))
    selected.to_csv(source, index=False)
    # A status without post evidence must not suppress recollection in main().
    pd.DataFrame([{'place_id': selected.iloc[0]['place_id'], 'blog_tag_status': 'verified'}]).to_csv(output, index=False)
    previous = output.read_bytes()
    monkeypatch.setenv('NAVER_API_ID', 'synthetic')
    monkeypatch.setenv('NAVER_API_SECRET', 'synthetic')
    monkeypatch.setattr(collector.time, 'sleep', lambda _: None)
    calls = []
    def collect(place, **kwargs):
        calls.append(place['place_id'])
        return {'record': {'blog_tags': '{}', 'verified_posts': '[]', 'blog_tag_status': 'no_verified_posts'},
                'audit': {'place_id': place['place_id'], 'status': 'no_verified_posts', 'posts': [], 'request_trace': []}}
    monkeypatch.setattr(collector, 'collect_with_audit', collect)
    collector.main(source, output)
    rows = pd.read_csv(output)
    assert len(rows) == 2 and rows['place_id'].nunique() == 2
    assert rows['주소'].tolist() == selected['주소'].tolist()
    assert next(tmp_path.glob('blog_tags.csv.legacy-*.csv')).read_bytes() == previous
    collector.main(source, output)
    assert len(calls) == 2
    assert len(list((tmp_path / 'blog_tags.audit').glob('*.json'))) == 2


def test_retry_upserts_one_row_and_preserves_prior_audit(tmp_path, places, monkeypatch):
    source, output = tmp_path / 'places.csv', tmp_path / 'tags.csv'
    ensure_ids(places.head(1)).to_csv(source, index=False)
    monkeypatch.setenv('NAVER_API_ID', 'synthetic')
    monkeypatch.setenv('NAVER_API_SECRET', 'synthetic')
    monkeypatch.setattr(collector.time, 'sleep', lambda _: None)
    outcomes = iter(['fetch_error', 'no_verified_posts'])
    def collect(place, **kwargs):
        status = next(outcomes)
        return {'record': {'blog_tags': '{}', 'verified_posts': '[]', 'blog_tag_status': status},
                'audit': {'place_id': place['place_id'], 'status': status}}
    monkeypatch.setattr(collector, 'collect_with_audit', collect)
    collector.main(source, output)
    collector.main(source, output)
    rows = pd.read_csv(output)
    assert len(rows) == 1 and rows.iloc[0]['blog_tag_status'] == 'no_verified_posts'
    history = next((tmp_path / 'tags.audit').glob('*.history-*.json'))
    assert json.loads(history.read_text())['status'] == 'fetch_error'


def test_interrupt_during_retry_backoff_counts_only_actual_request(monkeypatch):
    from Preprocess.crawler import http_client
    monkeypatch.setattr(http_client.requests, 'get', lambda *a, **kw: type('Response', (), {'status_code': 503})())
    monkeypatch.setattr(http_client.time, 'sleep', lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
    trace = []
    with pytest.raises(KeyboardInterrupt): http_client.get('https://blog.naver.com/x/1', trace=trace)
    assert trace == [{'kind': 'page', 'attempt': 1, 'status_code': 503}]


def test_journal_recovers_csv_after_snapshot_failure_without_recollecting(tmp_path, places, monkeypatch):
    source, output = tmp_path / 'places.csv', tmp_path / 'tags.csv'
    ensure_ids(places.head(1)).to_csv(source, index=False)
    monkeypatch.setenv('NAVER_API_ID', 'synthetic')
    monkeypatch.setenv('NAVER_API_SECRET', 'synthetic')
    monkeypatch.setattr(collector.time, 'sleep', lambda _: None)
    calls = []
    def collect(place, **kwargs):
        calls.append(place['place_id'])
        return {'record': {'blog_tags': '{}', 'verified_posts': '[]', 'blog_tag_status': 'no_verified_posts'},
                'audit': {'place_id': place['place_id'], 'status': 'no_verified_posts'}}
    monkeypatch.setattr(collector, 'collect_with_audit', collect)
    real_output = collector.atomic_output
    def fail_snapshot(path, **kwargs):
        if path == output: raise OSError('synthetic disk failure')
        return real_output(path, **kwargs)
    monkeypatch.setattr(collector, 'atomic_output', fail_snapshot)
    with pytest.raises(OSError): collector.main(source, output)
    assert not output.exists()
    monkeypatch.setattr(collector, 'atomic_output', real_output)
    collector.main(source, output)
    assert len(calls) == 1 and len(pd.read_csv(output)) == 1
