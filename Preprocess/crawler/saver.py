import csv
import os
import shutil
import hashlib
import json
from Preprocess.crawler.storage import atomic_output
from pathlib import Path

from place_identity import place_id, identity_key

DATA_DIR = Path(os.getenv('TRAVEL_DATA_DIR', Path(__file__).resolve().parents[1] / 'data/chungnam_data'))
FIELDS = ['페이지', '순위', '가게명', '카테고리', '주소', '검색어', '방문자수', '블로그수', '영업시간',
          'place_id', 'identity_key', 'provider', 'provider_place_id',
          'search_region', 'search_category', 'category_source']


def get_csv_path(region, category):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return str(DATA_DIR / f'충남_{region.replace(" ", "_")}_{category.replace(" ", "_")}.csv')


def get_done_path(region, category):
    return str(Path(get_csv_path(region, category)).with_suffix('.done'))


def is_task_completed(region, category):
    """Legacy DONE markers cannot prove that search/pagination succeeded."""
    try:
        marker = json.loads(Path(get_done_path(region, category)).read_text(encoding='utf-8'))
        source = Path(get_csv_path(region, category))
        return (marker.get('version') == 2 and marker.get('status') == 'completed' and
                marker.get('region') == region and marker.get('category') == category and
                marker.get('csv_sha256') == hashlib.sha256(source.read_bytes()).hexdigest())
    except (OSError, ValueError, AttributeError):
        return False


def mark_task_completed(region, category):
    source = Path(get_csv_path(region, category))
    marker = {'version': 2, 'status': 'completed', 'region': region, 'category': category,
              'csv_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    with atomic_output(get_done_path(region, category)) as stream:
        json.dump(marker, stream, ensure_ascii=False)


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
        backup = Path(str(path) + '.legacy.bak')
        if not backup.exists():
            shutil.copy2(path, backup)
        for row in rows:
            try:
                row.update(place_id=place_id(row), identity_key=identity_key(row))
            except ValueError:
                pass  # retain incomplete legacy records, never suppress by name
    with atomic_output(path, encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


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
    for field in ('search_region', 'search_category', 'category_source'):
        row[field] = data.get(field, '')
    row['provider'] = data.get('provider', '')
    row['provider_place_id'] = data.get('provider_place_id', '')
    row['identity_key'] = identity_key(row)
    row['place_id'] = place_id(row)
    touch_init_file(filepath)
    with open(filepath, encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    with atomic_output(filepath, encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        writer.writerow(row)
    return row['place_id']
