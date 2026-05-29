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
    """
    CSV 파일이 없을 경우에만 헤더 행을 포함한 빈 파일을 생성한다.
    이미 파일이 존재하면 아무 동작도 하지 않아, 기존 데이터를 보존한다.
    - utf-8-sig: BOM 포함 인코딩으로 Excel에서 한글이 깨지지 않도록 처리
    - newline="": Windows 환경에서 빈 줄이 한 줄씩 추가되는 현상 방지
    """
    if not os.path.exists(filepath):
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "페이지", "순위", "가게명", "카테고리",
                "주소", "검색어", "방문자수", "블로그수", "영업시간"
            ])

def load_existing_names(filepath):
    """
    기존 CSV에 이미 저장된 가게명 목록을 읽어와 집합(set)으로 반환한다.
    크롤링 도중 중단 후 재시작 시, 중복 수집을 방지하기 위한 용도.
    """
    existing = set()
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "가게명" in row:
                    existing.add(row["가게명"])
    return existing

def save_item(filepath, data):
    """
    장소 한 건을 CSV 파일 끝에 즉시 추가(append)한다.
    여러 건을 메모리에 모았다가 한 번에 저장하는 방식이 아니라,
    한 건이 수집될 때마다 곧바로 디스크에 기록함으로써,
    크롤링이 중간에 비정상 종료되더라도 그 시점까지의 데이터가 안전하게 보존된다.
    """
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