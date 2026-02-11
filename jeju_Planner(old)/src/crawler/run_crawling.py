# src/crawler/run_crawling.py

from multiprocessing import Pool, freeze_support
from webdriver_manager.chrome import ChromeDriverManager 
import random
import time
import os
from tqdm import tqdm 
import sys

# -----------------------------------------------------------
# [경로 수정] 프로젝트 루트(JEJU-TRAVEL-AI)를 찾아 시스템 경로에 추가
# -----------------------------------------------------------
current_file_path = os.path.abspath(__file__) # .../src/crawler/run_crawling.py
crawler_dir = os.path.dirname(current_file_path) # .../src/crawler
src_dir = os.path.dirname(crawler_dir) # .../src
project_root = os.path.dirname(src_dir) # .../JEJU-TRAVEL-AI (ROOT)

if project_root not in sys.path:
    sys.path.append(project_root)

# [중요] 프로젝트 루트를 작업 디렉토리로 설정
os.chdir(project_root)
# -----------------------------------------------------------

from src.crawler.crawler_core import JejuCrawler
from src.crawler.categories import CATEGORIES
from src.crawler.region_list import REGIONS
from src.crawler.saver import get_csv_path, load_existing_names

def worker_task(args):
    """
    개별 프로세스가 수행할 작업
    """
    region, category = args
    try:
        # 각 프로세스마다 크롤러 인스턴스 생성
        crawler = JejuCrawler() 
        crawler.crawl_region_category(region, category)
        if crawler.driver:
            crawler.driver.quit()
    except Exception:
        pass

def main():
    start_time = time.time()

    print("\n" + "="*50)
    print("🚗 멀티 프로세스 크롤러 시동 (이어하기 모드)")
    print(f"📂 Project Root: {project_root}")
    print("="*50)
    
    # 크롬 드라이버 설치 확인
    try:
        ChromeDriverManager().install()
    except: pass

    # 모든 작업 조합 생성 (지역 x 카테고리)
    all_tasks = [(r, c) for r in REGIONS for c in CATEGORIES]
    
    # --- 이어하기 로직 ---
    tasks_todo = []
    skipped_count = 0
    
    print(f"📂 기존 데이터 확인 중...", end="", flush=True)
    
    for r, c in all_tasks:
        csv_path = get_csv_path(r, c)
        
        # [수정] 데이터 개수가 아니라 '파일 존재 여부'로 체크
        # (결과가 0개여도 파일이 존재하면 이미 수행한 것으로 간주)
        if os.path.exists(csv_path):
            skipped_count += 1
        else:
            tasks_todo.append((r, c))
            
    print(" 완료!")
    print(f"♻️  완료된 작업(스킵): {skipped_count}개")
    print(f"🔥  진행할 작업: {len(tasks_todo)}개")
    print("="*50 + "\n")

    # 작업 순서를 섞어서 특정 지역/카테고리에 몰리지 않게 함
    random.shuffle(tasks_todo) 

    process_count = 4  # 7500F CPU를 위해 4개 권장
    print(f"🚀 크롤러 {process_count}대 동시 가동 시작!")
    
    # 멀티 프로세싱 실행
    if tasks_todo:
        with Pool(processes=process_count) as pool:
            # tqdm으로 진행률 표시
            list(tqdm(
                pool.imap_unordered(worker_task, tasks_todo), 
                total=len(tasks_todo), 
                unit="task",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [경과: {elapsed} < 남음: {remaining}]"
            ))
    else:
        print("✅ 모든 작업이 이미 완료되어 있습니다.")

    end_time = time.time()
    total_min = (end_time - start_time) / 60
    print(f"\n🎉 크롤링 전체 종료! (총 소요 시간: {total_min:.1f}분)")

if __name__ == "__main__":
    freeze_support() # 윈도우 환경 필수
    main()