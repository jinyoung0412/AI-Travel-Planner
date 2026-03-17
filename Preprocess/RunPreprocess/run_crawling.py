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
        with open(os.devnull, 'w', encoding='utf-8') as fnull:
            with redirect_stdout(fnull):
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
    
    total_tasks = len(tasks)
    
    print(f"\n크롤링 작업을 시작합니다. (총 {total_tasks}개 지역/카테고리)")
    print("작업 진행 상황은 아래와 같습니다. 발생한 오류는 error_log.txt에 기록됩니다.\n")
    print("-" * 60)

    completed_count = 0
    start_total_time = time.time()

    with multiprocessing.Pool(processes=4) as pool:
        for result in pool.imap_unordered(run_worker_silent, tasks):
            success, region, cat, err = result
            completed_count += 1
            
            percent = (completed_count / total_tasks) * 100
            bar_length = 30
            filled_length = int(bar_length * completed_count // total_tasks)
            bar = '=' * filled_length + '-' * (bar_length - filled_length)
            
            sys.stdout.write(f"\r진행률: [{bar}] {percent:6.2f}% ({completed_count}/{total_tasks}) | 최근 완료: {region} {cat}          ")
            sys.stdout.flush()

            if not success:
                log_error(region, cat, err)

    elapsed = time.time() - start_total_time
    print(f"\n\n모든 크롤링 작업이 완료되었습니다. (총 소요 시간: {elapsed/60:.1f}분)")
    print("수집된 데이터는 data 폴더를 확인해 주십시오.")