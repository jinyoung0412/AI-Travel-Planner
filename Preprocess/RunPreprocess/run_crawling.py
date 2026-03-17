import sys
import os
import multiprocessing
import time
import datetime
from contextlib import redirect_stdout

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir)
project_dir = os.path.dirname(src_dir)
sys.path.append(project_dir)

from Preprocess.crawler.crawler_core import ChungnamCrawler

try:
    from region_list import REGIONS
except ImportError:
    print("region_list.py 파일을 찾을 수 없습니다.")
    sys.exit(1)

try:
    from categories import CATEGORIES
except ImportError:
    print("categories.py 파일을 찾을 수 없습니다.")
    sys.exit(1)

def run_worker_silent(args):
    region, categories, q = args
    completed_in_worker = [0]
    
    class QueueWrapper:
        def put(self, item):
            completed_in_worker[0] += 1
            q.put(item)
            
    crawler = ChungnamCrawler()
    try:
        with open(os.devnull, 'w', encoding='utf-8') as fnull:
            with redirect_stdout(fnull):
                crawler.crawl_region_all_categories(region, categories, QueueWrapper())
    except Exception:
        pass
    finally:
        while completed_in_worker[0] < len(categories):
            q.put(1)
            completed_in_worker[0] += 1
        if crawler.driver: 
            try: crawler.driver.quit()
            except: pass

if __name__ == "__main__":
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError: 
        pass

    total_subtasks = len(REGIONS) * len(CATEGORIES)
    
    print("\n크롤링 작업을 시작합니다.")
    print(f"총 {total_subtasks}개의 세부 작업(지역x카테고리)을 실시간으로 추적합니다.")
    print("-" * 60)

    manager = multiprocessing.Manager()
    q = manager.Queue()
    
    tasks = [(region, CATEGORIES, q) for region in REGIONS]

    start_total_time = time.time()
    completed_subtasks = 0

    pool = multiprocessing.Pool(processes=5)
    for t in tasks:
        pool.apply_async(run_worker_silent, (t,))
    
    pool.close()

    while completed_subtasks < total_subtasks:
        q.get()
        completed_subtasks += 1
        
        percent = (completed_subtasks / total_subtasks) * 100
        bar_length = 30
        filled_length = int(bar_length * completed_subtasks // total_subtasks)
        bar = '=' * filled_length + '-' * (bar_length - filled_length)
        
        sys.stdout.write(f"\r진행률: [{bar}] {percent:6.2f}% ({completed_subtasks}/{total_subtasks})          ")
        sys.stdout.flush()

    pool.join()

    elapsed = time.time() - start_total_time
    print(f"\n\n모든 크롤링 작업이 완료되었습니다. (총 소요 시간: {elapsed/60:.1f}분)")