import sys
import os
import multiprocessing
import time
import datetime
import gc  # 메모리 관리 모듈 추가
from contextlib import redirect_stdout

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir)
project_dir = os.path.dirname(src_dir)
sys.path.append(project_dir)

from Preprocess.crawler.crawler_core import ChungnamCrawler

from Preprocess.crawler.region_list import REGIONS
from Preprocess.crawler.categories import CATEGORIES

def run_worker_silent(args):
    region, categories, q = args
    completed_in_worker = [0]
    
    class QueueWrapper:
        def put(self, item):
            completed_in_worker[0] += 1
            q.put(item)
            
    # 크롤러 실행 전 메모리 정리
    gc.collect()
    
    crawler = ChungnamCrawler()
    try:
        with open(os.devnull, 'w', encoding='utf-8') as fnull:
            with redirect_stdout(fnull):
                # 지역 하나가 끝나면 브라우저가 확실히 종료되도록 설계됨
                crawler.crawl_region_all_categories(region, categories, QueueWrapper())
    except Exception:
        pass
    finally:
        while completed_in_worker[0] < len(categories):
            q.put(1)
            completed_in_worker[0] += 1
        
        if crawler.driver: 
            try:
                crawler.driver.quit()
            except:
                pass
        # 작업 종료 후 명시적 메모리 해제
        del crawler
        gc.collect()

if __name__ == "__main__":
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError: 
        pass

    total_subtasks = len(REGIONS) * len(CATEGORIES)
    
    core=5 #크롤링을 돌릴 코어 수 (본인 램 용량이나 CPU 사양에 따라 코어 수 조절.)
    print(f"\n크롤링 작업을 시작합니다.(코어 갯수:{core})")
    print(f"총 {total_subtasks}개의 세부 작업을 진행합니다.")
    print("-" * 60)

    manager = multiprocessing.Manager()
    q = manager.Queue()
    
    pool = multiprocessing.Pool(processes=core, maxtasksperchild=1)
    
    tasks = [(region, CATEGORIES, q) for region in REGIONS]

    for t in tasks:
        pool.apply_async(run_worker_silent, (t,))
    
    pool.close()

    def format_eta(seconds):
        if seconds < 0:
            return "--:--:--"
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def print_progress(completed, total, start_time):
        bar_length = 30
        filled = int(bar_length * completed // total)
        bar = '=' * filled + '-' * (bar_length - filled)
        percent = completed / total * 100

        elapsed = time.time() - start_time
        if completed > 0:
            eta = elapsed / completed * (total - completed)
            eta_str = format_eta(eta)
        else:
            eta_str = "--:--:--"

        elapsed_str = format_eta(elapsed)
        sys.stdout.write(
            f"\r진행률: [{bar}] {percent:5.1f}%  "
            f"({completed}/{total})  "
            f"경과: {elapsed_str}  남은시간: {eta_str}   "
        )
        sys.stdout.flush()

    start_time = time.time()
    # 시작 즉시 0% 상태 출력
    print_progress(0, total_subtasks, start_time)

    completed_subtasks = 0
    while completed_subtasks < total_subtasks:
        q.get()
        completed_subtasks += 1
        print_progress(completed_subtasks, total_subtasks, start_time)

    pool.join()
    total_elapsed = format_eta(time.time() - start_time)
    print(f"\n\n모든 작업이 완료되었습니다. (총 소요시간: {total_elapsed})")