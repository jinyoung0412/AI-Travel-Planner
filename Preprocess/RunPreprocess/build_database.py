"""Rebuild SQLite using place IDs and independently checked blog evidence."""
import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from place_identity import ensure_ids
from blog_evidence import tags_from_posts

PLACES_CSV = ROOT / 'Preprocess/data/processed/chungnam_places_filtered.csv'
BLOG_TAGS_CSV = ROOT / 'Preprocess/data/processed/blog_tags.csv'
DB_PATH = ROOT / 'Flask_server/places.db'


def extract_region(address):
    address = str(address)
    return '천안' if '천안시' in address else '아산' if '아산시' in address else '기타'


def _read_csv(path):
    for encoding in ('utf-8-sig', 'utf-8', 'cp949', 'euc-kr'):
        try:
            return pd.read_csv(path, encoding=encoding, dtype={'provider_place_id': str, 'place_id': str})
        except UnicodeDecodeError:
            continue
    raise ValueError(f'인코딩 감지 실패: {path}')


def merge_verified_tags(places, blog_tags):
    places = ensure_ids(places).drop_duplicates('place_id', keep='last').copy()
    places['blog_tags'] = '{}'
    places['verified_posts'] = '[]'
    places['blog_tag_status'] = 'needs_collection'
    by_id = {p['place_id']: p for p in places.to_dict('records')}
    collected, quarantined = {}, []
    for row in blog_tags.to_dict('records'):
        pid = row.get('place_id')
        place = by_id.get(pid)
        tags, posts = tags_from_posts(place, row.get('verified_posts')) if place else ({}, [])
        if row.get('blog_tag_status') == 'verified' and posts:
            # Re-collection replaces the same identity; no one-to-many join.
            collected[pid] = (tags, posts)
        else:
            quarantined.append({**row, 'quarantine_reason': 'unproven_or_unknown_identity'})
    for idx, row in places.iterrows():
        if row['place_id'] in collected:
            tags, posts = collected[row['place_id']]
            places.at[idx, 'blog_tags'] = json.dumps(tags, ensure_ascii=False)
            places.at[idx, 'verified_posts'] = json.dumps(posts, ensure_ascii=False)
            places.at[idx, 'blog_tag_status'] = 'verified'
    places['지역'] = places['주소'].apply(extract_region)
    return places, pd.DataFrame(quarantined)


def backup_database(path):
    from datetime import datetime, timezone
    backup = Path(f'{path}.backup-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}')
    with sqlite3.connect(path) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    return backup


def write_database(df, path, quarantine=None, preserve=False):
    """Stage a complete SQLite DB, then replace it atomically; retain backup."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = backup_database(path) if path.exists() else None
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    os.close(fd)
    try:
        if preserve and backup:
            with sqlite3.connect(backup) as source, sqlite3.connect(temporary) as target:
                source.backup(target)
        with sqlite3.connect(temporary) as conn:
            df.to_sql('places', conn, if_exists='replace', index=False)
            if quarantine is not None and not quarantine.empty:
                quarantine.to_sql('blog_tags_quarantine', conn, if_exists='append', index=False)
            conn.execute('CREATE UNIQUE INDEX idx_place_id ON places(place_id)')
            conn.execute('CREATE INDEX idx_identity_key ON places(identity_key)')
            conn.execute('CREATE INDEX idx_region ON places(지역)')
            conn.execute('CREATE INDEX idx_category ON places(카테고리)')
            conn.execute('PRAGMA user_version = 2')
            conn.commit()
            assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return backup


def build(places_path=PLACES_CSV, tags_path=BLOG_TAGS_CSV, db_path=DB_PATH):
    places = _read_csv(places_path)
    tags = _read_csv(tags_path) if Path(tags_path).exists() else pd.DataFrame()
    df, quarantine = merge_verified_tags(places, tags)
    # Retain arbitrary source columns safely as JSON in a dedicated audit table.
    audit = pd.DataFrame([{'source_record': json.dumps(r, ensure_ascii=False, default=str),
                           'quarantine_reason': 'unproven_or_unknown_identity'}
                          for r in quarantine.to_dict('records')])
    backup = write_database(df, db_path, audit, preserve=True)
    stats = {'places': len(df), 'verified_places': int(df['blog_tag_status'].eq('verified').sum()),
             'quarantined_tag_records': len(audit), 'backup': str(backup) if backup else None}
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--places', type=Path, default=PLACES_CSV)
    parser.add_argument('--tags', type=Path, default=BLOG_TAGS_CSV)
    parser.add_argument('--db', type=Path, default=DB_PATH)
    args = parser.parse_args()
    build(args.places, args.tags, args.db)
