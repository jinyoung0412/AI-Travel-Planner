# src/crawler/saver.py
import os
import csv
from datetime import datetime

# -----------------------------------------------------------
# [경로 설정] 프로젝트 루트를 기준으로 '실제 데이터 폴더' 찾기
# -----------------------------------------------------------
# 1. 현재 파일(saver.py) 위치 구하기
current_file_path = os.path.abspath(__file__)
crawler_dir = os.path.dirname(current_file_path) # src/crawler
src_dir = os.path.dirname(crawler_dir)             # src
project_root = os.path.dirname(src_dir)            # JEJU-TRAVEL-AI (ROOT)

# 2. 실제 데이터가 있는 경로: data/raw/output/jeju_data
OUTPUT_DIR = os.path.join(project_root, "data", "raw", "output")
DATA_DIR = os.path.join(OUTPUT_DIR, "jeju_data")
FAILED_LOG = os.path.join(OUTPUT_DIR, "failed_log.csv")
# -----------------------------------------------------------

def ensure_dirs():
    # 상위 폴더가 없으면 에러가 날 수 있으니, DATA_DIR 생성 시 recursive하게 생성
    os.makedirs(DATA_DIR, exist_ok=True)

def log_failed(region, category, page, reason):
    ensure_dirs()
    file_exists = os.path.isfile(FAILED_LOG)
    try:
        with open(FAILED_LOG, "a", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            if not file_exists: 
                w.writerow(["timestamp", "region", "category", "page", "reason"])
            w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), region, category, page, reason])
    except Exception as e:
        print(f"[Log Error] 실패 로그 저장 중 오류: {e}")

def get_csv_path(region, category):
    ensure_dirs()
    # 읍면동별로 폴더를 따로 관리하는 구조 (jeju_data/제주_한림읍/...)
    region_dir = os.path.join(DATA_DIR, region)
    os.makedirs(region_dir, exist_ok=True)
    return os.path.join(region_dir, f"{region}_{category}.csv")

def load_existing_names(csv_path):
    if not os.path.exists(csv_path): 
        return set()
    
    names = set()
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            rd = csv.reader(f)
            next(rd, None) # 헤더 건너뛰기
            for row in rd:
                if len(row) >= 3: # name 컬럼이 있는지 확인
                    names.add(row[2])
    except Exception: 
        # 파일이 깨졌거나 읽을 수 없는 경우 무시하고 빈 set 반환
        pass
    return names

def save_item(csv_path, item):
    # 상위 폴더(region_dir)가 없을 경우를 대비해 한번 더 체크
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    
    file_exists = os.path.isfile(csv_path)
    try:
        with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
            wr = csv.writer(f)
            if not file_exists:
                wr.writerow(["page", "rank", "name", "category", "address", "search_keyword"])
            wr.writerow([item["page"], item["rank"], item["name"], item["category"], item["address"], item["keyword"]])
    except Exception as e:
        print(f"[Save Error] 데이터 저장 실패 ({item['name']}): {e}")

def touch_init_file(csv_path):
    """
    데이터가 없어도 파일은 생성하여 '방문함' 표시를 남김 (무한 반복 방지)
    """
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    if not os.path.exists(csv_path):
        try:
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                wr = csv.writer(f)
                # 헤더만 적어서 저장 (빈 파일 생성)
                wr.writerow(["page", "rank", "name", "category", "address", "search_keyword"])
        except Exception as e:
            print(f"[Init Error] 초기 파일 생성 실패: {e}")