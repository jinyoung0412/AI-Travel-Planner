"""Offline review validation; the actual source DB is opened read-only only."""
import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.offline_environment import install
install()
import pandas as pd
import requests
from blog_evidence import address_anchor, reviewed_tags_post
from Preprocess.RunPreprocess.build_database import build, merge_verified_tags, read_database, write_database
from Preprocess.RunPreprocess.migrate_place_ids import migrate


def forbidden(*args, **kwargs):
    raise AssertionError('External calls are forbidden during offline DB validation')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def quarantine_digest(path):
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True) as conn:
        rows = conn.execute('select source_record, quarantine_reason from blog_tags_quarantine order by rowid').fetchall()
    return len(rows), hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


def proof(place, label):
    # Mock source evidence in a temporary copy, not a claim about a real post.
    log_no = {'existing': '101', 'new': '102'}[label]
    value = {'url': f'https://blog.naver.com/offline-review/{log_no}',
            'name_excerpt': f"{place['가게명']} 후기", 'address_excerpt': place['주소'],
            'tags': [f'offline-{label}']}
    return reviewed_tags_post(place, value, value['tags'])


def tag_record(place, label):
    return {'place_id': place['place_id'], 'blog_tag_status': 'verified',
            'verified_posts': json.dumps([proof(place, label)], ensure_ascii=False)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db', type=Path, default=ROOT / 'Flask_server/places.db')
    parser.add_argument('--output', type=Path, default=ROOT / 'local_artifacts/review_fix_validation.json')
    args = parser.parse_args()
    if (args.output.resolve() == args.source_db.resolve() or
            (args.output.exists() and args.source_db.exists() and args.output.samefile(args.source_db))):
        parser.error('Report output must not replace the source database')
    requests.sessions.Session.request = forbidden
    started = time.perf_counter()
    source_hash = digest(args.source_db)
    original = read_database(args.source_db)
    original_ids = set(original['place_id'])
    original_quarantine = quarantine_digest(args.source_db)
    candidates = [row for row in original.to_dict('records') if address_anchor(row)]
    first, second = candidates[:2]
    report = {'offline': True, 'mock_evidence_only': True, 'source_places': len(original),
              'source_unique_ids': len(original_ids), 'source_sha256_before': source_hash,
              'source_quarantine_rows': original_quarantine[0],
              'source_verified_places': int(original['blog_tag_status'].eq('verified').sum()), 'cycles': []}
    with tempfile.TemporaryDirectory(prefix='travel-review-preservation-') as temporary:
        temp = Path(temporary)
        db = temp / 'places.db'
        with sqlite3.connect(args.source_db.resolve().as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(db) as target:
            source.backup(target)
        # Simulate one already completed place and a different partial collection.
        seed_started = time.perf_counter()
        seeded, _ = merge_verified_tags(original, pd.DataFrame([tag_record(first, 'existing')]))
        report['seed_merge_seconds'] = round(time.perf_counter() - seed_started, 3)
        write_database(seeded, db, preserve=True)
        partial_tags = temp / 'partial_tags.csv'
        pd.DataFrame([tag_record(second, 'new')]).to_csv(partial_tags, index=False)
        prior_snapshot = None
        for cycle in range(3):
            migration_started = time.perf_counter()
            migration = migrate(db, temp / 'export', apply=True)
            migration_seconds = time.perf_counter() - migration_started
            catalog = temp / 'export/places_catalog.csv'
            queue = temp / 'export/recollect_places.csv'
            catalog_frame = pd.read_csv(catalog)
            assert len(catalog_frame) == len(original)
            # Cycle 0 deliberately repeats the old README's subset mistake.
            build_started = time.perf_counter()
            stats = build(queue if cycle == 0 else catalog, partial_tags, db)
            build_seconds = time.perf_counter() - build_started
            actual = read_database(db).sort_values('place_id').reset_index(drop=True)
            assert set(actual['place_id']) == original_ids
            assert actual['blog_tag_status'].eq('verified').sum() == 2
            by_id = actual.set_index('place_id')
            assert json.loads(by_id.loc[first['place_id'], 'verified_posts']) == [proof(first, 'existing')]
            assert json.loads(by_id.loc[second['place_id'], 'verified_posts']) == [proof(second, 'new')]
            assert quarantine_digest(db) == original_quarantine
            for backup in (migration['backup'], stats['backup']):
                assert set(read_database(backup)['place_id']) == original_ids
                assert quarantine_digest(backup) == original_quarantine
            if prior_snapshot is not None:
                pd.testing.assert_frame_equal(actual, prior_snapshot)
            prior_snapshot = actual
            report['cycles'].append({'cycle': cycle + 1, 'catalog_places': len(catalog_frame),
                'queue_places': len(pd.read_csv(queue)), 'input_mode': 'queue' if cycle == 0 else 'full_catalog',
                'places': len(actual), 'unique_ids': actual['place_id'].nunique(),
                'verified_places': int(actual['blog_tag_status'].eq('verified').sum()),
                'quarantine_rows': original_quarantine[0], 'backups_verified': 2, 'migration_seconds': round(migration_seconds, 3),
                'build_seconds': round(build_seconds, 3),
                'identical_to_previous_cycle': cycle > 0})
        with sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True) as conn:
            report['temp_db_integrity'] = conn.execute('pragma integrity_check').fetchone()[0]
    report.update(source_sha256_after=digest(args.source_db), temporary_artifacts_removed=True,
                  quarantine_preserved=True, all_ids_preserved=True, no_external_calls=True,
                  elapsed_seconds=round(time.perf_counter() - started, 3))
    assert report['source_sha256_after'] == source_hash
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print('Validation output:', args.output)


if __name__ == '__main__':
    main()
