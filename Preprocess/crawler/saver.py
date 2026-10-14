import csv
import os
import shutil
from pathlib import Path

from place_identity import place_id, identity_key

DATA_DIR = Path(os.getenv('TRAVEL_DATA_DIR', Path(__file__).resolve().parents[1] / 'data/chungnam_data'))
FIELDS = ['페이지', '순위', '가게명', '카테고리', '주소', '검색어', '방문자수', '블로그수', '영업시간',
          'place_id', 'identity_key', 'provider', 'provider_place_id']


def get_csv_path(region, category):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return str(DATA_DIR / f'충남_{region.replace(" ", "_")}_{category.replace(" ", "_")}.csv')


def get_done_path(region, category):
    return str(Path(get_csv_path(region, category)).with_suffix('.done'))


def is_task_completed(region, category):
    return os.path.exists(get_done_path(region, category))


def mark_task_completed(region, category):
    Path(get_done_path(region, category)).write_text('DONE', encoding='utf-8')


def touch_init_file(filepath):
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows, fields = [], FIELDS
    if path.exists():
        with path.open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            if all(field in (reader.fieldnames or []) for field in FIELDS):
                return
            fields = list(dict.fromkeys((reader.fieldnames or []) + FIELDS))
            rows = list(reader)
        shutil.copy2(path, str(path) + '.legacy.bak')
        for row in rows:
            try:
                row.update(place_id=place_id(row), identity_key=identity_key(row))
            except ValueError:
                pass  # retain incomplete legacy records, never suppress by name
    temporary = Path(str(path) + '.tmp')
    with temporary.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def load_existing_ids(filepath):
    existing = set()
    if os.path.exists(filepath):
        with open(filepath, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                try:
                    existing.add(place_id(row))
                except ValueError:
                    continue
    return existing


def save_item(filepath, data):
    row = dict(zip(FIELDS[:9], [data.get(k, '') for k in (
        'page', 'rank', 'name', 'category', 'address', 'keyword', 'visitor_review', 'blog_review', 'operating_time')]))
    row['provider'] = data.get('provider', '')
    row['provider_place_id'] = data.get('provider_place_id', '')
    row['identity_key'] = identity_key(row)
    row['place_id'] = place_id(row)
    touch_init_file(filepath)
    with open(filepath, encoding='utf-8-sig') as f:
        fields = next(csv.reader(f))
    with open(filepath, 'a', encoding='utf-8-sig', newline='') as f:
        csv.DictWriter(f, fieldnames=fields).writerow(row)
    return row['place_id']
