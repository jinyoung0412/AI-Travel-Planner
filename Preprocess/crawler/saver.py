import csv
import os

def get_csv_path(region, category):
    folder = r"C:\AI-Travel-Planner\Preprocess\data\chungnam_data"
    if not os.path.exists(folder):
        os.makedirs(folder)
    clean_reg = region.replace(" ", "_")
    clean_cat = category.replace(" ", "_")
    return f"{folder}/충남_{clean_reg}_{clean_cat}.csv"

def get_done_path(region, category):
    folder = r"C:\AI-Travel-Planner\Preprocess\data\chungnam_data"
    clean_reg = region.replace(" ", "_")
    clean_cat = category.replace(" ", "_")
    return f"{folder}/충남_{clean_reg}_{clean_cat}.done"

def is_task_completed(region, category):
    return os.path.exists(get_done_path(region, category))

def mark_task_completed(region, category):
    with open(get_done_path(region, category), "w", encoding="utf-8") as f:
        f.write("DONE")

def touch_init_file(filepath):
    if not os.path.exists(filepath):
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "페이지", "순위", "가게명", "카테고리", 
                "주소", "검색어", "방문자수", "블로그수", "영업시간"
            ])

def load_existing_names(filepath):
    existing = set()
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "가게명" in row:
                    existing.add(row["가게명"])
    return existing

def save_item(filepath, data):
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