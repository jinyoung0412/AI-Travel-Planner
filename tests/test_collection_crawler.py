"""Synthetic WebDriver protocol elements only; no browser or driver download."""
import csv
from queue import Queue
from types import SimpleNamespace

import pytest

from Preprocess.crawler import crawler_core as core, saver, pagination, parser
from Preprocess.RunPreprocess import run_crawling as runner


class Driver:
    def __init__(self):
        self.switch_to = SimpleNamespace(default_content=lambda: None, frame=lambda _: None)
        self.closed = 0
    def quit(self):
        self.closed += 1
    def find_elements(self, *args):
        return [object()]
    def execute_script(self, *args):
        pass


@pytest.fixture
def crawler(tmp_path, monkeypatch):
    monkeypatch.setattr(saver, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(core.time, 'sleep', lambda _: None)
    monkeypatch.setattr(core, 'throttle_click_delay', lambda: None)
    monkeypatch.setattr(core, 'throttle_page_delay', lambda: None)
    monkeypatch.setattr(core, 'create_driver', Driver)
    monkeypatch.setattr(core.ChungnamCrawler, 'open_naver_map', lambda _: None)
    monkeypatch.setattr(core.ChungnamCrawler, 'prepare_list', lambda *a: 'OK')
    monkeypatch.setattr(core.ChungnamCrawler, 'scroll_list', lambda _: True)
    monkeypatch.setattr(core, 'go_next_page', lambda _: False)
    return core.ChungnamCrawler()


@pytest.mark.parametrize('failure', ['search', 'scroll', 'parse', 'pagination', 'start'])
def test_failure_is_retryable_and_never_marks_done(crawler, monkeypatch, failure):
    def fail(*args):
        raise RuntimeError('synthetic')
    monkeypatch.setattr(crawler, 'process_page', lambda *a: 0)
    if failure == 'search': monkeypatch.setattr(crawler, 'prepare_list', lambda *a: 'ERROR')
    if failure == 'scroll': monkeypatch.setattr(crawler, 'scroll_list', lambda: False)
    if failure == 'parse': monkeypatch.setattr(crawler, 'process_page', fail)
    if failure == 'pagination': monkeypatch.setattr(core, 'go_next_page', fail)
    if failure == 'start': monkeypatch.setattr(crawler, 'start_driver', fail)
    q = Queue()
    result = crawler.crawl_region_all_categories('충남 천안시 북면', ['카페'], q)
    assert not saver.is_task_completed('충남 천안시 북면', '카페')
    assert result[0]['status'] == 'failed' and q.qsize() == 1
    assert crawler.driver is None


def test_per_category_resume_retains_provenance_without_duplicate_rows(crawler, monkeypatch):
    region = '충남 천안시 북면'
    def process(region, category, keyword, path, existing, page):
        pid = 'naver:123'
        if pid not in existing:
            saver.save_item(path, {'name': '테스트카페', 'address': '충남 천안시 테스트로 1',
                            'category': '카페,디저트', 'provider': 'naver', 'provider_place_id': '123',
                            'search_region': region, 'search_category': category, 'category_source': 'provider'})
            existing.add(pid)
        return 0
    monkeypatch.setattr(crawler, 'process_page', process)
    assert all(r['status'] == 'completed' for r in crawler.crawl_region_all_categories(region, ['카페', '맛집']))
    # Invalidate one marker and retry it; the existing CSV ID still suppresses duplicate rows.
    from pathlib import Path
    Path(saver.get_done_path(region, '카페')).unlink()
    reports = crawler.crawl_region_all_categories(region, ['카페', '맛집'])
    assert [r['status'] for r in reports] == ['completed', 'skipped']
    for category in ('카페', '맛집'):
        with open(saver.get_csv_path(region, category), encoding='utf-8-sig') as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 1 and rows[0]['search_category'] == category
        assert rows[0]['category_source'] == 'provider'


def test_page_limit_does_not_claim_complete(crawler, monkeypatch):
    pages = []
    monkeypatch.setattr(crawler, 'process_page', lambda *args: pages.append(args[-1]))
    monkeypatch.setattr(core, 'go_next_page', lambda _: True)
    assert crawler.crawl_region_all_categories('지역', ['카페'])[0]['status'] == 'failed'
    assert pages == list(range(1, 11))
    assert not saver.is_task_completed('지역', '카페')


@pytest.mark.parametrize('failure', ['empty', 'save', 'identity'])
def test_partial_page_errors_are_visible(crawler, monkeypatch, failure):
    crawler.driver = Driver()
    monkeypatch.setattr(core, 'wait_for_list_panel', lambda _: True)
    monkeypatch.setattr(core, 'extract_list_items', lambda _: [] if failure == 'empty' else [SimpleNamespace(find_elements=lambda *a: [])])
    monkeypatch.setattr(core, 'extract_name_element', lambda _: (object(), '독립카페'))
    monkeypatch.setattr(crawler, 'check_and_close_popup', lambda: False)
    monkeypatch.setattr(core, 'parse_detail_page', lambda _: ('카페', '' if failure == 'identity' else '주소', 0, 0, '시간없음', ''))
    def fail(*a): raise OSError('synthetic disk failure')
    monkeypatch.setattr(core, 'save_item', fail)
    with pytest.raises(RuntimeError):
        crawler.process_page('지역', '카페', '검색어', '/unused', set(), 1)


def test_marker_requires_matching_csv_and_migrates_legacy_without_losing_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(saver, 'DATA_DIR', tmp_path)
    from pathlib import Path
    path = Path(saver.get_csv_path('지역', '카페'))
    path.write_text('가게명,주소,메모\n독립카페,충남 천안시 테스트로 1,원본\n', encoding='utf-8-sig')
    original = path.read_bytes()
    Path(saver.get_done_path('지역', '카페')).write_text('DONE')
    assert not saver.is_task_completed('지역', '카페')
    saver.touch_init_file(path)
    assert Path(str(path) + '.legacy.bak').read_bytes() == original
    with path.open(encoding='utf-8-sig') as stream:
        row = next(csv.DictReader(stream))
    assert row['메모'] == '원본' and row['place_id'].startswith('local:')
    saver.mark_task_completed('지역', '카페')
    assert saver.is_task_completed('지역', '카페')
    saver.save_item(path, {'name': '다른카페', 'address': '충남 천안시 테스트로 2'})
    assert not saver.is_task_completed('지역', '카페')
    assert Path(str(path) + '.legacy.bak').read_bytes() == original


@pytest.mark.parametrize('url,expected', [
    ('https://pcmap.place.naver.com/restaurant/123/home?x=1', '123'),
    ('https://map.naver.com/p/entry/place/123?c=1', '123'),
    ('https://m.place.naver.com/cafe/00123', '00123'),
    ('https://evil.example/place/123', ''), ('https://map.naver.com.evil/place/123', ''),
    ('https://map.naver.com/?url=/place/123', ''), ('file://map.naver.com/place/123', ''),
    ('https://map.naver.com/place/123abc', '')])
def test_provider_ids_are_parsed_from_trusted_paths(url, expected):
    assert parser.extract_provider_place_id(url) == expected


@pytest.mark.parametrize('state', ['true', 'false', None, 'missing'])
def test_pagination_requires_explicit_state(monkeypatch, state):
    monkeypatch.setattr(pagination.time, 'sleep', lambda _: None)
    driver = Driver()
    button = SimpleNamespace(get_attribute=lambda _: state)
    driver.find_elements = lambda by, value: [object()] if by == 'id' else ([] if state == 'missing' else [button])
    if state in ('true', 'false'):
        assert pagination.go_next_page(driver) is (state == 'false')
    else:
        with pytest.raises(RuntimeError): pagination.go_next_page(driver)


def test_worker_constructor_failure_surfaces_and_fills_only_finished_tokens(monkeypatch):
    def fail(): raise RuntimeError('synthetic')
    monkeypatch.setattr(runner, 'ChungnamCrawler', fail)
    q = Queue()
    with pytest.raises(RuntimeError): runner.run_worker_silent(('지역', ['A', 'B'], q))
    assert q.qsize() == 2


def test_supervisor_detects_worker_crash_without_queue_messages():
    closed = []
    class Worker:
        exitcode = 9
        def __init__(self, **kwargs): pass
        def start(self): pass
        def join(self): pass
        def close(self): closed.append(True)
    reports = runner.supervise_regions(SimpleNamespace(Process=Worker), ['지역'], ['A', 'B'], 1,
                                        Queue(), {}, lambda _: None)
    assert len(reports) == 2 and all(r['error_type'] == 'WorkerExit' for r in reports)
    assert closed == [True]


def test_supervisor_terminates_workers_on_interrupt():
    events = []
    class Worker:
        exitcode = None
        def __init__(self, **kwargs): pass
        def start(self): pass
        def is_alive(self): return not ('terminate' in events)
        def terminate(self): events.append('terminate')
        def join(self, **kwargs): events.append('join')
        def kill(self): events.append('kill')
        def close(self): events.append('close')
    q = SimpleNamespace(get=lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        runner.supervise_regions(SimpleNamespace(Process=Worker), ['지역'], ['A'], 1, q, {}, lambda _: None)
    assert events == ['terminate', 'join', 'close']


def test_newly_opened_place_is_not_silently_excluded():
    item = SimpleNamespace(text='새로 오픈했어요 독립카페 리뷰 1', find_elements=lambda *a: [object()])
    driver = SimpleNamespace(find_elements=lambda *a: [item])
    assert parser.extract_list_items(driver) == [item]


def test_stale_entry_provider_id_is_not_saved(crawler, monkeypatch):
    crawler.driver = Driver()
    monkeypatch.setattr(core, 'wait_for_list_panel', lambda _: True)
    link = SimpleNamespace(get_attribute=lambda _: 'https://map.naver.com/p/entry/place/123')
    item = SimpleNamespace(find_elements=lambda *a: [link])
    monkeypatch.setattr(core, 'extract_list_items', lambda _: [item])
    monkeypatch.setattr(core, 'extract_name_element', lambda _: (object(), '독립카페'))
    monkeypatch.setattr(crawler, 'check_and_close_popup', lambda: False)
    monkeypatch.setattr(core, 'parse_detail_page', lambda _: ('카페', '충남 천안시 테스트로 1', 0, 0, '시간없음', '999'))
    with pytest.raises(RuntimeError, match='Incomplete page'):
        crawler.process_page('지역', '카페', '검색', '/unused', set(), 1)


def _exit_without_report():
    import os
    os._exit(9)


def test_real_spawned_process_crash_is_reported_without_hanging():
    import multiprocessing
    context = multiprocessing.get_context('spawn')
    class CrashContext:
        def Process(self, **kwargs):
            return context.Process(target=_exit_without_report)
    reports = runner.supervise_regions(CrashContext(), ['지역'], ['카페'], 1, Queue(), {}, lambda _: None)
    assert reports == [{'region': '지역', 'category': '카페', 'status': 'failed',
                        'error_type': 'WorkerExit', 'exitcode': 9}]


@pytest.mark.parametrize('platform,modifier', [('darwin', 'COMMAND'), ('linux', 'CONTROL')])
def test_search_replaces_previous_keyword_with_platform_shortcut(monkeypatch, platform, modifier):
    import sys
    import types
    module = types.ModuleType('selenium.webdriver.common.keys')
    module.Keys = SimpleNamespace(COMMAND='COMMAND', CONTROL='CONTROL', ENTER='ENTER')
    monkeypatch.setitem(sys.modules, 'selenium.webdriver.common.keys', module)
    monkeypatch.setattr(core.sys, 'platform', platform)
    monkeypatch.setattr(core.time, 'sleep', lambda _: None)
    sent = []
    box = SimpleNamespace(click=lambda: None, send_keys=sent.append)
    crawler = core.ChungnamCrawler()
    crawler.driver = Driver()
    crawler.driver.find_element = lambda *a: box
    assert crawler.search_keyword('충남 천안시 북면 카페')
    assert sent == [modifier + 'a', '충남 천안시 북면 카페', 'ENTER']
