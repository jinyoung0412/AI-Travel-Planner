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

try:
    from region_list import REGIONS
except ImportError:
    sys.exit(1)

try:
    from categories import CATEGORIES
except ImportError:
    sys.exit(1)

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
    
    print("\n크롤링 작업을 시작합니다.")
    print(f"총 {total_subtasks}개의 세부 작업을 진행합니다.")
    print("-" * 60)

    manager = multiprocessing.Manager()
    q = manager.Queue()
    
    # 32GB 램이라도 학교 컴퓨터 사양을 고려해 3~4코어 유지를 권장합니다.
    # 학교에서는 processes=2 정도로 낮추는 것이 안전합니다.
    pool = multiprocessing.Pool(processes=2)
    
    tasks = [(region, CATEGORIES, q) for region in REGIONS]

    for t in tasks:
        pool.apply_async(run_worker_silent, (t,))
    
    pool.close()

    completed_subtasks = 0
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
    print(f"\n\n모든 작업이 완료되었습니다.")