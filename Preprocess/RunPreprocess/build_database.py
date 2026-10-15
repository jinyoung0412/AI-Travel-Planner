"""Rebuild SQLite using place IDs and independently checked blog evidence."""
import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from place_identity import ensure_ids, identity_key, text
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
            return pd.read_csv(path, encoding=encoding, dtype={'provider_place_id': str, 'place_id': str}, float_precision='round_trip')
        except UnicodeDecodeError:
            continue
    raise ValueError(f'인코딩 감지 실패: {path}')


BLOG_COLUMNS = {'blog_tags', 'verified_posts', 'blog_tag_status'}
ALIAS_COLUMN = 'identity_aliases'
_LOCAL_ID = re.compile(r'local:v1:[0-9a-f]{64}\Z')


def _stored_aliases(row):
    value = row.get(ALIAS_COLUMN)
    try:
        value = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return set()
    return {a for a in value if isinstance(a, str) and _LOCAL_ID.fullmatch(a)} if isinstance(value, list) else set()


def _audit_frame(records):
    return pd.DataFrame([{'source_record': json.dumps(r, ensure_ascii=False, sort_keys=True, default=str),
                           'quarantine_reason': r['quarantine_reason']}
                          for r in records.to_dict('records')])


def _combine_metadata(previous, places):
    # Build from records instead of concat to keep empty/all-null CSV columns
    # stable across pandas versions; the original row boundary is preserved.
    columns = list(dict.fromkeys([*previous.columns, *places.columns]))
    return pd.DataFrame([*previous.to_dict('records'), *places.to_dict('records')], columns=columns)


def merge_verified_tags(places, blog_tags, existing=None, replace_all=False, metadata_mode='snapshot'):
    """Upsert metadata, retain omitted identities and union revalidated evidence.

    Full catalog and recollection queue are distinct inputs. Even an accidentally
    supplied queue cannot delete existing rows. Only replace_all removes IDs not
    in the metadata input. Evidence priority for the same URL is explicit tag CSV
    > current DB > catalog snapshot; failed/empty recollections never erase proof.
    Snapshot metadata fills missing cells; explicit update mode changes existing
    metadata. Local identity aliases persist in the catalog's identity_aliases.
    """
    if metadata_mode not in ('snapshot', 'update'):
        raise ValueError('metadata_mode는 snapshot 또는 update이어야 합니다.')
    previous = existing if existing is not None else pd.DataFrame()
    combined = ensure_ids(_combine_metadata(previous, places))
    old_count = len(previous)
    old_rows = combined.iloc[:old_count].to_dict('records')
    input_rows = combined.iloc[old_count:].to_dict('records')
    raw_rows = _combine_metadata(previous, places).to_dict('records')
    # Re-ingestion can upgrade a known local identity to a unique provider ID.
    alias_candidates = {}
    aliases_per_id = {}
    for raw, row in zip(raw_rows, combined.to_dict('records')):
        candidates = _stored_aliases(raw) | {text(raw.get('place_id')), text(row.get('identity_key'))}
        candidates = {a for a in candidates if _LOCAL_ID.fullmatch(a)}
        aliases_per_id.setdefault(row['place_id'], set()).update(candidates)
    # Ambiguous aliases never join two distinct known provider IDs.
    for pid, candidates in aliases_per_id.items():
        for alias in candidates:
            alias_candidates.setdefault(alias, set()).add(pid)
    input_ids = {row['place_id'] for row in input_rows}
    metadata = {}
    for row, incoming in [(r, False) for r in old_rows] + [(r, True) for r in input_rows]:
        pid = row['place_id']
        if replace_all and pid not in input_ids:
            continue
        target = metadata.setdefault(pid, {})
        # Missing CSV cells do not erase richer metadata already in the DB.
        for key, value in row.items():
            if key in BLOG_COLUMNS or key == ALIAS_COLUMN or pd.isna(value) or value == '':
                continue
            # A snapshot fills gaps. Only an explicit authoritative update can
            # change existing metadata and invalidate current address evidence.
            if not incoming or metadata_mode == 'update' or key not in target:
                target[key] = value
    # Recompute the alias of the chosen metadata, not that of a stale snapshot.
    for pid, place in metadata.items():
        alias = identity_key(place)
        place['identity_key'] = alias
        if _LOCAL_ID.fullmatch(alias):
            aliases_per_id.setdefault(pid, set()).add(alias)
            alias_candidates.setdefault(alias, set()).add(pid)

    hints, collected, quarantined = {}, {}, []
    # Catalog may be stale. Existing DB evidence takes precedence over its
    # same-URL copy; newly supplied valid tag records are an explicit update.
    sources = [(row, False) for row in [*input_rows, *old_rows]] + [(row, True) for row in blog_tags.to_dict('records')]
    for raw, tag_input in sources:
        row = dict(raw)
        raw_pid = text(row.get('place_id'))
        # A still-present canonical ID always wins over an alias. An enriched
        # row must not redirect another known provider's existing proof.
        matches = {pid for pid in alias_candidates.get(raw_pid, set()) if pid in metadata}
        pid = raw_pid if raw_pid in metadata else next(iter(matches)) if len(matches) == 1 else raw_pid
        row['place_id'] = pid
        place = metadata.get(pid)
        if place is None and not tag_input:
            continue  # explicitly removed identities are retained in the DB backup
        status = text(row.get('blog_tag_status'))
        if place and status and status != 'verified':
            hints[pid] = status
        tags, posts = tags_from_posts(place, row.get('verified_posts')) if place else ({}, [])
        if status == 'verified' and posts:
            by_url = collected.setdefault(pid, {})
            by_url.update((post['url'], post) for post in posts)
            try:
                supplied = json.loads(row['verified_posts']) if isinstance(row.get('verified_posts'), str) else row.get('verified_posts')
            except (TypeError, ValueError):
                supplied = []
            if any(post not in posts for post in supplied or []):
                quarantined.append({**row, 'quarantine_reason': 'partially_invalid_post_evidence'})
        else:
            has_tags = text(row.get('blog_tags')) not in ('', '{}', 'null')
            has_posts = text(row.get('verified_posts')) not in ('', '[]', 'null')
            # Explicit failed collection records retain their audit trail too.
            if has_tags or has_posts or tag_input:
                quarantined.append({**row, 'quarantine_reason': 'ambiguous_identity_alias' if len(matches) > 1 and raw_pid not in metadata else 'unproven_or_unknown_identity'})
    columns = list(dict.fromkeys([c for c in combined.columns if c not in BLOG_COLUMNS] +
                                ['place_id', 'identity_key', '가게명', '주소', '카테고리']))
    result = pd.DataFrame(list(metadata.values()), columns=columns)
    result[ALIAS_COLUMN] = [json.dumps(sorted(aliases_per_id.get(pid, set())), ensure_ascii=False) for pid in result['place_id']]
    result['blog_tags'], result['verified_posts'] = '{}', '[]'
    result['blog_tag_status'] = [hints.get(pid, 'needs_collection') for pid in result['place_id']]
    for idx, row in result.iterrows():
        if row['place_id'] in collected:
            tags, posts = tags_from_posts(row, list(collected[row['place_id']].values()))
            result.at[idx, 'blog_tags'] = json.dumps(tags, ensure_ascii=False)
            result.at[idx, 'verified_posts'] = json.dumps(posts, ensure_ascii=False)
            result.at[idx, 'blog_tag_status'] = 'verified'
    result['지역'] = result['주소'].apply(extract_region)
    return result, pd.DataFrame(quarantined)


def read_database(path):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        return pd.read_sql('SELECT * FROM places', conn)


def _append_quarantine(conn, quarantine):
    """Keep prior audit data and avoid duplicating records on repeated builds."""
    def key(source, reason):
        try:
            source = json.dumps(json.loads(source), ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            pass
        return source, reason
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='blog_tags_quarantine'").fetchone()
    seen = {key(*r) for r in conn.execute('SELECT source_record, quarantine_reason FROM blog_tags_quarantine')} if exists else set()
    additions = []
    for row in quarantine.to_dict('records'):
        identity = key(row['source_record'], row['quarantine_reason'])
        if identity not in seen:
            additions.append(row)
            seen.add(identity)
    if additions:
        pd.DataFrame(additions).to_sql('blog_tags_quarantine', conn, if_exists='append', index=False)


def backup_database(path):
    from datetime import datetime, timezone
    backup = Path(f'{path}.backup-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}')
    with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as target:
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
            with closing(sqlite3.connect(backup)) as source, closing(sqlite3.connect(temporary)) as target:
                source.backup(target)
        with closing(sqlite3.connect(temporary)) as conn:
            df.to_sql('places', conn, if_exists='replace', index=False)
            if quarantine is not None and not quarantine.empty:
                _append_quarantine(conn, quarantine)
            conn.execute('CREATE UNIQUE INDEX idx_place_id ON places(place_id)')
            conn.execute('CREATE INDEX idx_identity_key ON places(identity_key)')
            conn.execute('CREATE INDEX idx_region ON places(지역)')
            conn.execute('CREATE INDEX idx_category ON places(카테고리)')
            conn.execute('PRAGMA user_version = 2')
            conn.commit()
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('임시 DB 무결성 검사 실패: 원본을 교체하지 않았습니다.')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return backup


def build(places_path=PLACES_CSV, tags_path=BLOG_TAGS_CSV, db_path=DB_PATH, replace_all=False, metadata_mode='snapshot'):
    places = _read_csv(places_path)
    tags = _read_csv(tags_path) if Path(tags_path).exists() else pd.DataFrame()
    previous = read_database(db_path)
    df, quarantine = merge_verified_tags(places, tags, existing=previous, replace_all=replace_all, metadata_mode=metadata_mode)
    # Count true removals after local-to-provider identity promotion.
    combined = ensure_ids(_combine_metadata(previous, places))
    previous_ids = set(combined.iloc[:len(previous)]['place_id'])
    removed = sorted(previous_ids - set(df['place_id']))
    if removed and not replace_all:
        raise ValueError('기본 갱신에서 기존 장소 삭제를 감지했습니다. DB를 변경하지 않았습니다.')
    audit = _audit_frame(quarantine)
    backup = write_database(df, db_path, audit, preserve=True)
    stats = {'places': len(df), 'input_places': len(places),
             'verified_places': int(df['blog_tag_status'].eq('verified').sum()),
             'mode': 'replace_all' if replace_all else 'upsert', 'metadata_mode': metadata_mode,
             'removed_place_ids': removed, 'quarantined_tag_records': len(audit),
             'backup': str(backup) if backup else None}
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--places', type=Path, default=PLACES_CSV)
    parser.add_argument('--tags', type=Path, default=BLOG_TAGS_CSV)
    parser.add_argument('--db', type=Path, default=DB_PATH)
    parser.add_argument('--replace-all', action='store_true',
                        help='명시적 전체 교체: --places에 없는 장소를 삭제합니다. 기본값은 기존 장소 보존 갱신입니다.')
    parser.add_argument('--update-metadata', action='store_true', help='명시적 메타데이터 갱신: 기존 주소·이름 등을 덮어씁니다. 기본은 스냅샷 병합입니다.')
    args = parser.parse_args()
    build(args.places, args.tags, args.db, replace_all=args.replace_all,
          metadata_mode='update' if args.update_metadata else 'snapshot')
