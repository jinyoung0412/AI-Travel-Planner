"""Region workers report finished tasks separately from successful collection."""
import argparse
import multiprocessing
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path
from queue import Empty
import os
import signal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from Preprocess.crawler.crawler_core import ChungnamCrawler
from Preprocess.crawler.region_list import REGIONS
from Preprocess.crawler.categories import CATEGORIES


def run_worker_silent(args):
    region, categories, q = args
    crawler = None
    finished = 0

    class QueueWrapper:
        def put(self, item):
            nonlocal finished
            finished += 1
            q.put({'region': region, 'finished_categories': finished})

    try:
        crawler = ChungnamCrawler()
        with open(os.devnull, 'w', encoding='utf-8') as sink, redirect_stdout(sink):
            return crawler.crawl_region_all_categories(region, categories, QueueWrapper())
    finally:
        try:
            while finished < len(categories):
                q.put({'region': region, 'finished_categories': finished + 1})
                finished += 1
        finally:
            if crawler is not None:
                crawler.stop_driver()


def format_eta(seconds):
    if seconds < 0:
        return '--:--:--'
    hours, rest = divmod(int(seconds), 3600)
    minutes, seconds = divmod(rest, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'


def print_progress(completed, total, start_time):
    elapsed = time.monotonic() - start_time
    eta = format_eta(elapsed / completed * (total - completed)) if completed else '--:--:--'
    fraction = completed / total if total else 1
    filled = int(30 * fraction)
    sys.stdout.write(f'\r진행률: [{"=" * filled}{"-" * (30 - filled)}] {fraction * 100:5.1f}% '
                     f'({completed}/{total}) 경과: {format_eta(elapsed)} 남은시간: {eta}   ')
    sys.stdout.flush()


def _interrupt_worker(signum, frame):
    raise KeyboardInterrupt()


def _run_region(args, reports, region):
    signal.signal(signal.SIGTERM, _interrupt_worker)
    try:
        reports[region] = run_worker_silent(args)
    except (Exception, KeyboardInterrupt) as exc:
        reports[region] = [{'region': region, 'category': category, 'status': 'failed',
                            'error_type': type(exc).__name__} for category in args[1]]


def supervise_regions(context, regions, categories, processes, q, reports, progress):
    """Observe process exits directly, including os._exit/crashes without queue tokens."""
    pending = iter(regions)
    counts = {region: 0 for region in regions}
    active, finished_reports = {}, []
    started_all = False
    try:
        while active or not started_all:
            while len(active) < processes and not started_all:
                region = next(pending, None)
                if region is None:
                    started_all = True
                    break
                worker = context.Process(target=_run_region, args=((region, categories, q), reports, region))
                worker.start()
                active[region] = worker
            try:
                event = q.get(timeout=0.2)
                if isinstance(event, dict) and event.get('region') in counts:
                    region = event['region']
                    counts[region] = max(counts[region], min(len(categories), event['finished_categories']))
                    progress(sum(counts.values()))
            except Empty:
                pass
            for region, worker in list(active.items()):
                if worker.exitcode is None:
                    continue
                worker.join()
                result = reports.get(region)
                if (worker.exitcode != 0 or not isinstance(result, list) or len(result) != len(categories) or
                        {row.get('category') for row in result} != set(categories)):
                    result = [{'region': region, 'category': category, 'status': 'failed',
                               'error_type': 'WorkerExit', 'exitcode': worker.exitcode} for category in categories]
                finished_reports.extend(result)
                counts[region] = len(categories)
                progress(sum(counts.values()))
                worker.close()
                del active[region]
    finally:
        for worker in active.values():
            if worker.is_alive():
                worker.terminate()
            worker.join(timeout=5)
            if worker.is_alive():
                worker.kill()
                worker.join()
            worker.close()
    return finished_reports


def main(processes=5):
    if processes < 1:
        raise ValueError('프로세스 수는 1 이상이어야 합니다.')
    total = len(REGIONS) * len(CATEGORIES)
    context = multiprocessing.get_context('spawn')
    started = time.monotonic()
    with context.Manager() as manager:
        q, reports = manager.Queue(), manager.dict()
        print_progress(0, total, started)
        results = supervise_regions(context, REGIONS, CATEGORIES, processes, q, reports,
                                    lambda n: print_progress(n, total, started))
    failed = [report for report in results if report['status'] not in ('completed', 'skipped')]
    print(f'\n종료: 성공/기존 완료 {len(results) - len(failed)}, 실패 {len(failed)} '
          f'(소요시간: {format_eta(time.monotonic() - started)})')
    return 1 if failed else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--processes', type=int, default=5)
    raise SystemExit(main(parser.parse_args().processes))
