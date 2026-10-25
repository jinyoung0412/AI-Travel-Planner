"""Full-review fixes: synthetic transport, real local files and process locks."""
import csv
import json
import multiprocessing
from pathlib import Path
import runpy
import sys
from contextlib import contextmanager
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

from blog_evidence import post_url_key
from place_identity import ensure_ids
from Preprocess.RunPreprocess import blog_tag_pilot as pilot
from Preprocess.RunPreprocess import collect_blog_tags as collector
from Preprocess.crawler import saver, crawler_core
from Preprocess.crawler.storage import exclusive_output, OutputInUseError

URL = 'https://blog.naver.com/review_fixture/1'
GOOD = 'https://blog.naver.com/review_fixture/2'


def place(number='00123'):
    return ensure_ids(pd.DataFrame([{'가게명': '수집검토카페', '주소': '충남 천안시 중앙로 10',
        'provider': 'naver', 'provider_place_id': str(number), '카테고리': '카페',
        'latitude': 36.8, 'longitude': 127.1}])).iloc[0].to_dict()


def post(p, url):
    return {'url': url, 'name_excerpt': p['가게명'], 'address_excerpt': p['주소'],
            'tags': ['조용한'], 'tag_parser': 'gsTagName'}


@pytest.fixture
def offline_collection(monkeypatch):
    monkeypatch.setenv('NAVER_API_ID', 'offline-fixture')
    monkeypatch.setenv('NAVER_API_SECRET', 'offline-fixture')
    monkeypatch.setattr(collector.time, 'sleep', lambda _: None)


@pytest.fixture
def collected_pilot(tmp_path, monkeypatch, offline_collection):
    targets = [place(str(i)) for i in range(5)]
    manifest = {'pilot_id': 'review-fixture', 'collection_authorized_now': True}
    monkeypatch.setattr(pilot, 'checked_targets', lambda *a: (manifest, targets))
    state = {'recovering': False, 'fetches': []}

    def search(p, **kwargs):
        return ([URL, GOOD] if p['place_id'] == targets[0]['place_id'] else []), 'fixture query'

    def fetch(url, p, query, trace):
        state['fetches'].append(url)
        trace.append({'kind': 'page', 'attempt': 1})
        if url == URL and not state['recovering']:
            raise requests.Timeout('offline fixture')
        return post(p, url)

    monkeypatch.setattr(collector, 'search_blog_urls', search)
    monkeypatch.setattr(collector, 'fetch_post', fetch)
    output = tmp_path / 'pilot'
    pilot.collect(output=output)
    review = json.loads((output / 'review.json').read_text())
    for entry in review['entries']:
        entry.update(identity_match=True, approved_taste_tags=['조용한'], notes='preserve this human decision')
    pilot.save_json(output / 'review.json', review)
    assert pilot.export_reviewed(output=output)['precision_denominator'] == 1
    return output, targets, state, review


def test_summary_write_failure_blocks_export_then_resume_preserves_human_history(collected_pilot, monkeypatch):
    output, targets, state, old_review = collected_pilot
    original_save = pilot.save_json
    previous_summary = (output / 'collection.json').read_bytes()
    previous_export = (output / 'reviewed_tags.csv').read_bytes()
    previous_review = (output / 'review.json').read_bytes()
    state['recovering'] = True

    def fail_summary(path, data):
        if path == output / 'collection.json' and data['runs'][0]['audit']['fetch_failure'] == 0:
            raise OSError('injected summary publication failure')
        original_save(path, data)

    monkeypatch.setattr(pilot, 'save_json', fail_summary)
    with pytest.raises(OSError):
        pilot.collect(output=output, resume=True)
    assert (output / 'collection.json').read_bytes() == previous_summary
    assert (output / 'review.json').read_bytes() == previous_review
    latest = json.loads((output / 'collection-1.json').read_text())
    assert latest['audit']['identity_accepted'] == 2
    assert next(output.glob('reviewed_tags.history-*.csv')).read_bytes() == previous_export
    files_before = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
    with pytest.raises(ValueError, match='collect --resume'):
        pilot.export_reviewed(output=output)
    assert files_before == {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
    assert not (output / 'reviewed_tags.csv').exists()

    monkeypatch.setattr(pilot, 'save_json', original_save)
    fetches = list(state['fetches'])
    pilot.collect(output=output, resume=True)
    assert state['fetches'] == fetches  # Restore journals, no new collection.
    review = json.loads((output / 'review.json').read_text())
    unchanged = next(e for e in review['entries'] if e['url'] == GOOD)
    assert unchanged == next(e for e in old_review['entries'] if e['url'] == GOOD)
    changed = next(e for e in review['entries'] if e['url'] == URL)
    assert changed['identity_match'] is None and changed['approved_taste_tags'] == []
    assert changed['history'][0]['notes'] == 'preserve this human decision'
    with pytest.raises(ValueError, match='수동 신원 판정'):
        pilot.export_reviewed(output=output)
    changed.update(identity_match=True, approved_taste_tags=['조용한'])
    pilot.save_json(output / 'review.json', review)
    metrics = pilot.export_reviewed(output=output)
    assert metrics['precision_denominator'] == 2 and metrics['latest_fetch_failures'] == 0


def test_journal_only_state_requires_resume_and_does_not_recollect(collected_pilot):
    output, targets, state, _ = collected_pilot
    # A crash can leave durable per-place files without any summary publication.
    (output / 'collection.json').unlink()
    before_review = (output / 'review.json').read_bytes()
    with pytest.raises(ValueError, match='collect --resume'):
        pilot.export_reviewed(output=output)
    assert (output / 'review.json').read_bytes() == before_review
    state['recovering'] = True
    pilot.collect(output=output, resume=True)
    assert state['fetches'].count(GOOD) == 1


@pytest.mark.parametrize('change', ['target', 'identity', 'outside', 'gap'])
def test_checkpoint_identity_and_index_validation_is_non_destructive(collected_pilot, change):
    output, targets, state, _ = collected_pilot
    checkpoint = output / 'collection-1.json'
    run = json.loads(checkpoint.read_text())
    if change == 'target':
        run['place_id'] = targets[1]['place_id']
        pilot.save_json(checkpoint, run)
    elif change == 'identity':
        run['audit']['place_identity']['주소'] = '충남 천안시 중앙로 20'
        pilot.save_json(checkpoint, run)
    elif change == 'outside':
        pilot.save_json(output / 'collection-6.json', run)
    else:
        (output / 'collection.json').unlink()
        checkpoint.unlink()
    before = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
    with pytest.raises(ValueError):
        pilot.export_reviewed(output=output)
    with pytest.raises(ValueError):
        pilot.collect(output=output, resume=True)
    assert before == {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
    assert state['fetches'] == [URL, GOOD]


def test_collection_and_export_have_one_owner(collected_pilot):
    output, _, state, _ = collected_pilot
    with exclusive_output(output / '.pilot'):
        with pytest.raises(OutputInUseError):
            pilot.collect(output=output, resume=True)
        with pytest.raises(OutputInUseError):
            pilot.export_reviewed(output=output)
    assert state['fetches'] == [URL, GOOD]


@pytest.mark.parametrize('payload', [{}, {'unexpected': True}, {'items': None}, {'items': {}},
    {'items': [None]}, {'items': [{}]}, {'items': [{'link': None}]}, [], None])
def test_search_schema_error_is_retryable_and_cannot_mark_place_done(monkeypatch, offline_collection, payload):
    p = place()
    response = SimpleNamespace(json=lambda: payload)
    mocked = []

    def get(*a, **kw):
        mocked.append(1)
        return response

    monkeypatch.setattr(collector, '_get', get)
    result = collector.collect_with_audit(p, delay=0)
    assert result['audit']['search_error']['error_type'] == 'ValueError'
    assert result['record']['blog_tag_status'] == 'fetch_error'
    assert not collector._done_ids(pd.DataFrame([{**p, **result['record']}]))
    collector.collect_with_audit(p, previous=result['audit'], delay=0)
    assert mocked == [1]  # A default rerun still avoids unbounded retries.
    response.json = lambda: {'items': []}
    repaired = collector.collect_with_audit(p, previous=result['audit'], retry_failed=True, delay=0)
    assert mocked == [1, 1]
    assert repaired['record']['blog_tag_status'] == 'no_verified_posts'
    assert 'search_error' not in repaired['audit'] and repaired['audit']['search_history']


def test_legitimate_empty_search_and_non_naver_results_remain_supported(monkeypatch, offline_collection):
    for items in ([], [{'link': 'https://example.com/legitimate_other_blog'}]):
        monkeypatch.setattr(collector, '_get', lambda *a, **kw: SimpleNamespace(json=lambda: {'items': items}))
        result = collector.collect_with_audit(place(), delay=0)
        assert result['record']['blog_tag_status'] == 'no_verified_posts'
        assert 'search_error' not in result['audit']


def _csv_data(number):
    return {'name': '카페', 'address': '충남 천안시 중앙로 10',
            'provider': 'naver', 'provider_place_id': number}


def _held_csv_writer(path, ready, release, results):
    """A real spawned writer pauses inside its read/modify/publish transaction."""
    from Preprocess.crawler import saver as child_saver
    original = child_saver.atomic_output

    @contextmanager
    def held_output(path, **kwargs):
        ready.set()
        if not release.wait(15):
            raise RuntimeError('test release timed out')
        with original(path, **kwargs) as stream:
            yield stream

    child_saver.atomic_output = held_output
    try:
        results.put(('saved', child_saver.save_item(path, _csv_data('00101'))))
    except BaseException as exc:
        results.put(('error', type(exc).__name__))


@pytest.mark.parametrize('second_id', ['00101', '00102'])
def test_process_csv_conflict_explicit_retry_preserves_rows_and_done_hash(tmp_path, monkeypatch, second_id):
    monkeypatch.setattr(saver, 'DATA_DIR', tmp_path)
    path = Path(saver.get_csv_path('지역', '카페'))
    saver.touch_init_file(path)
    original = path.read_bytes()
    context = multiprocessing.get_context('spawn')
    ready, release, results = context.Event(), context.Event(), context.Queue()
    worker = context.Process(target=_held_csv_writer, args=(path, ready, release, results))
    worker.start()
    try:
        assert ready.wait(15)
        with pytest.raises(OutputInUseError):
            saver.save_item(path, _csv_data(second_id))
        with pytest.raises(OutputInUseError):
            saver.mark_task_completed('지역', '카페')
        assert path.read_bytes() == original
        release.set()
        worker.join(timeout=15)
        assert not worker.is_alive() and worker.exitcode == 0
        assert results.get(timeout=2) == ('saved', 'naver:00101')
        saver.mark_task_completed('지역', '카페')
        assert saver.is_task_completed('지역', '카페')
        assert saver.save_item(path, _csv_data(second_id)) == 'naver:' + second_id
        ids = saver.load_existing_ids(path)
        assert ids == {'naver:00101', 'naver:' + second_id}
        with path.open(encoding='utf-8-sig') as stream:
            assert len(list(csv.DictReader(stream))) == len(ids)
        assert saver.is_task_completed('지역', '카페') is (second_id == '00101')
    finally:
        release.set()
        worker.join(timeout=2)
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=5)
        worker.close()
        results.close()
        results.join_thread()


def test_killed_writer_releases_os_lock_without_overwriting_csv(tmp_path):
    path = tmp_path / 'crawl.csv'
    saver.touch_init_file(path)
    original = path.read_bytes()
    context = multiprocessing.get_context('spawn')
    ready, release, results = context.Event(), context.Event(), context.Queue()
    worker = context.Process(target=_held_csv_writer, args=(path, ready, release, results))
    worker.start()
    try:
        assert ready.wait(15)
        worker.terminate()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert path.read_bytes() == original
        assert saver.save_item(path, _csv_data('00102')) == 'naver:00102'
    finally:
        if worker.is_alive():
            worker.kill()
            worker.join(timeout=5)
        worker.close()
        results.close()
        results.join_thread()


def test_legacy_migration_and_keyboard_interrupt_preserve_history_and_release_lock(tmp_path):
    path = tmp_path / 'legacy.csv'
    path.write_text('가게명,주소,메모\n이전카페,충남 천안시 중앙로 20,원본 메모\n', encoding='utf-8-sig')
    original = path.read_bytes()
    with exclusive_output(path):
        with pytest.raises(OutputInUseError):
            saver.touch_init_file(path)
        assert path.read_bytes() == original
    with pytest.raises(KeyboardInterrupt):
        with exclusive_output(path):
            raise KeyboardInterrupt()
    saver.save_item(path, _csv_data('00102'))
    assert Path(str(path) + '.legacy.bak').read_bytes() == original
    with path.open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2 and rows[0]['메모'] == '원본 메모'
    saver.touch_init_file(path)
    assert Path(str(path) + '.legacy.bak').read_bytes() == original


def test_duplicate_crawl_task_is_rejected_before_browser_start(tmp_path, monkeypatch):
    monkeypatch.setattr(saver, 'DATA_DIR', tmp_path)
    crawler = crawler_core.ChungnamCrawler()
    monkeypatch.setattr(crawler, 'start_driver', lambda: pytest.fail('duplicate task opened a browser'))
    path = saver.get_csv_path('지역', '카페')
    with exclusive_output(path + '.task'):
        reports = crawler.crawl_region_all_categories('지역', ['카페'])
    assert reports[0]['status'] == 'failed' and reports[0]['error_type'] == 'OutputInUseError'
    assert not saver.is_task_completed('지역', '카페')


def test_batch_output_conflict_does_not_start_collection(tmp_path, monkeypatch, offline_collection):
    source, output = tmp_path / 'places.csv', tmp_path / 'tags.csv'
    pd.DataFrame([place()]).to_csv(source, index=False)
    monkeypatch.setattr(collector, 'collect_with_audit', lambda *a, **kw: pytest.fail('duplicate collection'))
    with exclusive_output(output):
        with pytest.raises(OutputInUseError):
            collector.main(source, output)
    assert not output.exists() and not output.with_name('tags.audit').exists()


def test_test_flag_help_describes_place_limit_and_http_upper_bound(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['collect_blog_tags.py', '--help'])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(collector.__file__, run_name='__main__')
    assert result.value.code == 0
    help_text = capsys.readouterr().out
    for expected in ('5곳', '30개', '2회', '310회', 'HTTP 5회 제한 아님'):
        assert expected in help_text


def test_test_flag_keeps_five_place_contract_and_counts_http_separately(tmp_path, monkeypatch, offline_collection):
    source, output = tmp_path / 'places.csv', tmp_path / 'tags.csv'
    pd.DataFrame([place(str(i)) for i in range(6)]).to_csv(source, index=False)
    calls = []

    class Response:
        status_code = 200
        text = '<div class="se-main-container"><p>unrelated article</p></div>'
        def json(self):
            return {'items': [{'link': URL}, {'link': GOOD}]}
        def raise_for_status(self):
            pass

    def get(url, **kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr(collector.requests, 'get', get)
    monkeypatch.setattr(sys, 'argv', ['collect_blog_tags.py', '--test', '--input', str(source), '--output', str(output)])
    runpy.run_path(collector.__file__, run_name='__main__')
    frame = pd.read_csv(output)
    assert len(frame) == 5 and len(calls) == 15
    attempts = sum(len(json.loads(path.read_text())['request_trace'])
                   for path in (tmp_path / 'tags.audit').glob('*.json'))
    assert attempts == 15


@pytest.mark.parametrize('url', [None, 123, '', 'file://blog.naver.com/x/1',
    'https://blog.naver.com/x/not-a-log-number',
    'https://blog.naver.com/x/12suffix', 'https://blog.naver.com/x/１２',
    'https://blog.naver.com/invalid%20id/1', 'https://blog.naver.com/x/1?logNo=2',
    'https://blog.naver.com:444/x/1', 'https://u:p@blog.naver.com/x/1',
    'https://blog.naver.com/PostView.naver?blogId=x&logNo=1&logNo=2',
    'https://blog.naver.com/PostView.naver?blogId=x&blogId=y&logNo=1',
    'https://blog.naver.com/PostView.naver?blogId=x&logNo=',
    'https://blog.naver.com.evil.example/x/1'])
def test_canonical_url_reuses_shared_strict_post_parser(url):
    assert post_url_key(url) == ''
    assert collector.canonical_blog_url(url) == ''


@pytest.mark.parametrize('url', ['http://m.blog.naver.com/test_blog-1/00123#tracking',
    'https://blog.naver.com/test_blog-1/00123?tracking=1',
    'https://blog.naver.com/PostView.naver?blogId=test_blog-1&logNo=00123'])
def test_canonical_url_accepted_variants_match_evidence_parser(url):
    assert post_url_key(url) == 'test_blog-1/00123'
    assert collector.canonical_blog_url(url) == 'https://blog.naver.com/test_blog-1/00123'
