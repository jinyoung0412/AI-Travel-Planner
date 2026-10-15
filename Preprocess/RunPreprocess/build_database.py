"""Rebuild SQLite using place IDs and independently checked blog evidence."""
import argparse
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from place_identity import ensure_ids, identity_key, alias_conflicts, local_aliases, text
from blog_evidence import post_url_key, tags_from_posts, validated_posts

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


BLOG_COLUMNS = ('blog_tags', 'verified_posts', 'blog_tag_status')
ALIAS_COLUMN = 'identity_aliases'
CONFLICT_COLUMN = 'identity_alias_conflicts'
PROVIDER_COLUMNS = ('provider', 'provider_place_id')


def _audit_frame(records):
    return pd.DataFrame([{'source_record': json.dumps(r, ensure_ascii=False, sort_keys=True, default=str),
                           'quarantine_reason': r['quarantine_reason']}
                          for r in records.to_dict('records')], columns=['source_record', 'quarantine_reason'])


def _combine_metadata(previous, places):
    # Build from records instead of concat to keep empty/all-null CSV columns
    # stable across pandas versions; the original row boundary is preserved.
    columns = list(dict.fromkeys([*previous.columns, *places.columns]))
    return pd.DataFrame([*previous.to_dict('records'), *places.to_dict('records')], columns=columns)


def _identity_rows(previous, places):
    raw = _combine_metadata(previous, places)
    combined = ensure_ids(raw)
    rows = combined.to_dict('records')
    aliases = {}
    for original, row in zip(raw.to_dict('records'), rows):
        candidates = local_aliases(original) | local_aliases(row)
        aliases.setdefault(row['place_id'], set()).update(candidates)
    return combined, rows[:len(previous)], rows[len(previous):], aliases


def _merge_metadata(old_rows, input_rows, replace_all, metadata_mode):
    input_ids = {row['place_id'] for row in input_rows}
    metadata = {}
    for rows, incoming in ((old_rows, False), (input_rows, True)):
        for row in rows:
            pid = row['place_id']
            if replace_all and pid not in input_ids:
                continue
            target = metadata.setdefault(pid, {})
            for key, value in row.items():
                if key in BLOG_COLUMNS or key in (ALIAS_COLUMN, CONFLICT_COLUMN, *PROVIDER_COLUMNS) or pd.isna(value) or value == '':
                    continue
                if not incoming or metadata_mode == 'update' or key not in target:
                    target[key] = value
            pair = {key: text(row.get(key)) for key in PROVIDER_COLUMNS}
            current_complete = all(text(target.get(key)) for key in PROVIDER_COLUMNS)
            # Never assemble a provider identity out of two incomplete rows.
            if (not any(text(target.get(key)) for key in PROVIDER_COLUMNS) or
                    (not current_complete and (all(pair.values()) or metadata_mode == 'update'))):
                for key, value in pair.items():
                    if value:
                        target[key] = value
                    else:
                        target.pop(key, None)
    return metadata


def _alias_candidates(metadata, aliases, rows):
    for pid, place in metadata.items():
        # A stale snapshot must not replace the alias of current metadata.
        place['identity_key'] = identity_key(place)
        aliases.setdefault(pid, set()).update(local_aliases(place))
    candidates = {}
    # Include removed providers as ambiguity witnesses: replace_all must not
    # make their previously shared local aliases uniquely prove another ID.
    for pid, values in aliases.items():
        for alias in values:
            candidates.setdefault(alias, set()).add(pid)
    for row in rows:
        for alias, owners in alias_conflicts(row).items():
            candidates.setdefault(alias, set()).update(owners)
    return candidates


def _merge_evidence(metadata, alias_candidates, sources):
    hints, collected, quarantined = {}, {}, []
    for raw, tag_input in sources:
        row = dict(raw)
        raw_pid = text(row.get('place_id'))
        matches = alias_candidates.get(raw_pid, set())
        # Canonical IDs win; only a unique historical local alias redirects.
        pid = raw_pid if raw_pid in metadata else next(iter(matches)) if len(matches) == 1 else raw_pid
        row['place_id'] = pid
        place = metadata.get(pid)
        if place is None and not tag_input:
            continue
        status = text(row.get('blog_tag_status'))
        if place and status and status != 'verified':
            hints[pid] = status
        posts, rejected = validated_posts(place, row.get('verified_posts')) if place else ([], [])
        if status == 'verified' and posts:
            by_url = collected.setdefault(pid, {})
            by_url.update((post_url_key(post['url']), post) for post in posts)
            if rejected:
                quarantined.append({**row, 'quarantine_reason': 'partially_invalid_post_evidence'})
        else:
            has_tags = text(row.get('blog_tags')) not in ('', '{}', 'null')
            has_posts = text(row.get('verified_posts')) not in ('', '[]', 'null')
            if has_tags or has_posts or tag_input:
                reason = ('ambiguous_identity_alias' if len(matches) > 1 and raw_pid not in metadata
                          else 'unproven_or_unknown_identity')
                quarantined.append({**row, 'quarantine_reason': reason})
    return hints, collected, pd.DataFrame(quarantined)


def merge_verified_tags(places, blog_tags, existing=None, replace_all=False, metadata_mode='snapshot'):
    """Upsert metadata and revalidated proof; only replace_all removes places.

    Snapshot fills missing metadata; update explicitly overwrites it. Proof for
    a canonical post is prioritized: explicit tag CSV > current DB > snapshot.
    Failed collection never erases valid proof. Ambiguous aliases fail closed.
    """
    if metadata_mode not in ('snapshot', 'update'):
        raise ValueError('metadata_mode는 snapshot 또는 update이어야 합니다.')
    previous = existing if existing is not None else pd.DataFrame()
    combined, old_rows, input_rows, aliases = _identity_rows(previous, places)
    metadata = _merge_metadata(old_rows, input_rows, replace_all, metadata_mode)
    candidates = _alias_candidates(metadata, aliases, [*old_rows, *input_rows])
    sources = ([(row, False) for row in [*input_rows, *old_rows]] +
               [(row, True) for row in blog_tags.to_dict('records')])
    hints, collected, quarantine = _merge_evidence(metadata, candidates, sources)
    columns = list(dict.fromkeys([c for c in combined.columns if c not in BLOG_COLUMNS] +
                                ['place_id', 'identity_key', '가게명', '주소', '카테고리']))
    records = []
    for pid, place in metadata.items():
        tags, posts = tags_from_posts(place, list(collected.get(pid, {}).values()))
        conflicts = {}
        for alias in aliases.get(pid, set()):
            owners = {owner for owner in candidates.get(alias, set()) if not owner.startswith('local:v1:')}
            if len(owners) > 1:
                conflicts[alias] = sorted(owners)
        records.append({**place,
                        CONFLICT_COLUMN: json.dumps(conflicts, ensure_ascii=False, sort_keys=True),
                        ALIAS_COLUMN: json.dumps(sorted(aliases.get(pid, set())), ensure_ascii=False),
                        'blog_tags': json.dumps(tags, ensure_ascii=False),
                        'verified_posts': json.dumps(posts, ensure_ascii=False),
                        'blog_tag_status': 'verified' if posts else hints.get(pid, 'needs_collection')})
    result = pd.DataFrame(records, columns=list(dict.fromkeys([*columns, ALIAS_COLUMN, CONFLICT_COLUMN, *BLOG_COLUMNS])))
    result['지역'] = result['주소'].apply(extract_region)
    return result, quarantine


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


def _database_version(path):
    path = Path(path)
    if not path.exists():
        return None
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


_UNSET = object()


@contextmanager
def _publication_lock(path, expected_version):
    """Reserve the old file against SQLite writers until atomic publication."""
    conn = None
    try:
        if path.exists():
            conn = sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True, timeout=0)
            if conn.execute('PRAGMA journal_mode').fetchone()[0].lower() == 'wal':
                raise ValueError('WAL DB는 교체할 수 없습니다. 연결을 닫고 오프라인 DELETE 모드로 전환하세요.')
            conn.execute('BEGIN IMMEDIATE')
        version = _database_version(path)
        if expected_version is not _UNSET and version != expected_version:
            raise ValueError('읽은 뒤 원본 DB가 변경되었습니다. 다시 읽어 갱신하세요.')
        yield version
    finally:
        if conn is not None:
            conn.rollback()
            conn.close()


def backup_database(path):
    from datetime import datetime, timezone
    path = Path(path)
    backup = Path(f'{path}.backup-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}')
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
    except Exception:
        backup.unlink(missing_ok=True)
        raise
    return backup


def write_database(df, path, quarantine=None, preserve=False, *, _expected_version=_UNSET):
    """Stage and validate before atomic publication; retain a complete backup.

    Rebuilds are offline operations. WAL files require an explicit offline
    checkpoint/mode change, because replacing a DB below live WAL connections
    can attach their old journal to the new file. Rollback-mode writers are
    excluded while staging; build/migrate also check their input snapshot.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _publication_lock(path, _expected_version) as version:
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
            if _database_version(path) != version:
                raise ValueError('교체 중 원본 DB 파일 변경을 감지했습니다. 원본을 교체하지 않았습니다.')
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return backup


def build(places_path=PLACES_CSV, tags_path=BLOG_TAGS_CSV, db_path=DB_PATH, replace_all=False, metadata_mode='snapshot'):
    places = _read_csv(places_path)
    tags = _read_csv(tags_path) if Path(tags_path).exists() else pd.DataFrame()
    source_version = _database_version(db_path)
    previous = read_database(db_path)
    df, quarantine = merge_verified_tags(places, tags, existing=previous, replace_all=replace_all, metadata_mode=metadata_mode)
    # Count true removals after local-to-provider identity promotion.
    combined = ensure_ids(_combine_metadata(previous, places))
    previous_ids = set(combined.iloc[:len(previous)]['place_id'])
    removed = sorted(previous_ids - set(df['place_id']))
    if removed and not replace_all:
        raise ValueError('기본 갱신에서 기존 장소 삭제를 감지했습니다. DB를 변경하지 않았습니다.')
    audit = _audit_frame(quarantine)
    backup = write_database(df, db_path, audit, preserve=True, _expected_version=source_version)
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
