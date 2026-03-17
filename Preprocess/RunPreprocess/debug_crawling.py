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
    print("오류: region_list.py 파일을 찾을 수 없습니다.")
    sys.exit(1)

try:
    from categories import CATEGORIES
except ImportError:
    print("오류: categories.py 파일을 찾을 수 없습니다.")
    sys.exit(1)

def log_error(region, category, error_msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("error_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {region} - {category} : {error_msg}\n")

def run_worker_silent(args):
    region, category = args
    crawler = ChungnamCrawler()
    
    try:
        crawler.crawl_region_category(region, category)
        return (True, region, category, None)
    except Exception as e:
        return (False, region, category, str(e))
    finally:
        if crawler.driver: 
            try: 
                crawler.driver.quit()
            except: 
                pass

if __name__ == "__main__":
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError: 
        pass

    tasks = []
    for region in REGIONS:
        for category in CATEGORIES:
            tasks.append((region, category))
    
    tasks = [tasks[0]]
    
    total_tasks = len(tasks)
    
    print(f"\n[디버깅 모드] 원인 파악을 위해 1개의 작업만 1코어로 실행합니다.")
    print("-" * 60)

    completed_count = 0
    start_total_time = time.time()

    with multiprocessing.Pool(processes=1) as pool:
        for result in pool.imap_unordered(run_worker_silent, tasks):
            success, region, cat, err = result
            completed_count += 1
            
            if not success:
                log_error(region, cat, err)
                print(f"\n작업 실패: {region} {cat} - {err}")

    elapsed = time.time() - start_total_time
    print(f"\n\n작업 완료. (총 소요 시간: {elapsed:.1f}초)")