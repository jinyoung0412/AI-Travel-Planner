# src/crawler/saver.py

import csv
import os

def get_csv_path(region, category):
    """저장할 파일 경로 생성 (data/충남_천안_카페.csv)"""
    folder = "data"
    if not os.path.exists(folder):
        os.makedirs(folder)
    # 공백 등을 _로 치환
    clean_reg = region.replace(" ", "_")
    clean_cat = category.replace(" ", "_")
    return f"{folder}/충남_{clean_reg}_{clean_cat}.csv"

def touch_init_file(filepath):
    """파일이 없으면 헤더(제목 줄) 생성"""
    if not os.path.exists(filepath):
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "페이지", "순위", "가게명", "카테고리", 
                "주소", "검색어", "방문자수", "블로그수", "영업시간"
            ])

def load_existing_names(filepath):
    """이미 수집한 가게 이름을 불러와서 중복 방지"""
    existing = set()
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "가게명" in row:
                    existing.add(row["가게명"])
    return existing

def save_item(filepath, data):
    """데이터 한 줄 추가"""
    with open(filepath, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            data.get("page", ""),
            data.get("rank", ""),
            data.get("name", ""),
            data.get("category", ""),
            data.get("address", ""),
            data.get("keyword", ""),
            data.get("visitor_review", 0),
            data.get("blog_review", 0),
            data.get("operating_time", "")
        ])