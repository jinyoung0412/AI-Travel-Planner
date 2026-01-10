# src/crawler/run_crawling.py

import sys
import os
import multiprocessing
import time
import datetime
from contextlib import redirect_stdout

# 1. 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir)
project_dir = os.path.dirname(src_dir)
sys.path.append(project_dir)

from src.crawler.crawler_core import ChungnamCrawler

# 2. 리스트 불러오기
try:
    from region_list import REGIONS
except ImportError:
    print("❌ 'region_list.py'가 없습니다.")
    sys.exit(1)

try:
    from categories import CATEGORIES
except ImportError:
    print("❌ 'categories.py'가 없습니다.")
    sys.exit(1)

# ==========================================
# 에러 기록 함수
# ==========================================
def log_error(region, category, error_msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("error_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {region} - {category} : {error_msg}\n")

# ==========================================
# 조용한 일꾼 (로그 숨김)
# ==========================================
def run_worker_silent(args):
    region, category = args
    crawler = ChungnamCrawler()
    
    # 작업 시작 시간
    start_time = time.time()
    
    try:
        # [핵심] 화면에 출력되는 잡다한 로그를 os.devnull로 날려버림 (조용하게)
        with open(os.devnull, 'w') as fnull:
            with redirect_stdout(fnull):
                crawler.crawl_region_category(region, category)
        return (True, region, category, None)
        
    except Exception as e:
        # 에러 나면 메시지 반환
        return (False, region, category, str(e))
        
    finally:
        if crawler.driver: 
            try: crawler.driver.quit()
            except: pass

# ==========================================
# 메인 실행부 (진행바 표시)
# ==========================================
if __name__ == "__main__":
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError: pass

    # 작업 리스트 생성
    tasks = []
    for region in REGIONS:
        for category in CATEGORIES:
            tasks.append((region, category))
    
    total_tasks = len(tasks)
    
    print(f"\n🚀 [3코어 / 저소음 모드] 총 {total_tasks}개 작업을 시작합니다.")
    print(f"📄 로그는 숨기고 진행률만 표시합니다. 에러는 'error_log.txt'에 저장됩니다.\n")
    print("-" * 60)

    # 결과 수집용
    completed_count = 0
    start_total_time = time.time()

    # 3코어로 실행 (processes=3)
    with multiprocessing.Pool(processes=3) as pool:
        # imap_unordered: 끝나는 대로 즉시 결과 받음
        for result in pool.imap_unordered(run_worker_silent, tasks):
            success, region, cat, err = result
            completed_count += 1
            
            # 진행률 계산
            percent = (completed_count / total_tasks) * 100
            bar_length = 30
            filled_length = int(bar_length * completed_count // total_tasks)
            bar = '■' * filled_length + '□' * (bar_length - filled_length)
            
            # 한 줄에 갱신하며 출력 (carriage return \r 사용)
            sys.stdout.write(f"\r[{bar}] {percent:6.2f}% ({completed_count}/{total_tasks}) - 완료: {region} {cat}          ")
            sys.stdout.flush()

            # 에러 발생 시 기록
            if not success:
                log_error(region, cat, err)

    elapsed = time.time() - start_total_time
    print(f"\n\n🏁 모든 작업 완료! (소요 시간: {elapsed/60:.1f}분)")
    print(f"📁 데이터는 data 폴더에, 에러는 error_log.txt에 저장되었습니다.")