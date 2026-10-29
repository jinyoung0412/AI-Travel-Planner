"""Offline, reversible migration. Default is dry-run; --apply writes a backup."""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from place_identity import ensure_ids, normalize
from Preprocess.RunPreprocess.build_database import write_database, read_database, merge_verified_tags, _audit_frame, _database_version


def migrate(db_path, output_dir, apply=False):
    source_version = _database_version(db_path)
    old = read_database(db_path)
    places = ensure_ids(old)
    names = places['가게명'].map(normalize)
    counts = names.value_counts()
    ambiguous = names.map(counts).gt(1)
    verified = places.get('blog_tag_status', pd.Series('', index=places.index)).eq('verified')
    unproven = ~verified
    has_tags = places.get('blog_tags', pd.Series('{}', index=places.index)).fillna('{}').map(lambda s: s not in ('', '{}', 'null'))
    quarantine = places.loc[unproven & has_tags].copy()
    quarantine['quarantine_reason'] = ['ambiguous_legacy_name' if a else 'legacy_without_post_evidence'
                                        for a in ambiguous[unproven & has_tags]]
    audit = _audit_frame(quarantine)
    places.loc[unproven, 'blog_tags'] = '{}'
    # Migration must not turn modern retry/review states into legacy labels.
    # Only genuinely unlabeled historical rows receive a legacy status.
    missing_status = places.get('blog_tag_status', pd.Series('', index=places.index)).fillna('').map(normalize).eq('')
    places.loc[unproven & missing_status, 'blog_tag_status'] = 'legacy_unverified'
    places.loc[unproven & missing_status & ambiguous, 'blog_tag_status'] = 'ambiguous_legacy'
    places['verified_posts'] = places.get('verified_posts', '[]')
    # Retained verified rows must still satisfy the current identity rules.
    # Revalidation also preserves valid posts from mixed valid/invalid evidence.
    deduped, invalid_proof = merge_verified_tags(places, pd.DataFrame())
    audit = pd.concat([audit, _audit_frame(invalid_proof)], ignore_index=True)
    recollect = deduped[deduped['blog_tag_status'].ne('verified')].drop(columns=['blog_tags', 'verified_posts'])
    stats = {'input_places': len(old), 'output_places': len(deduped),
             'duplicate_identity_rows_removed': len(old) - len(deduped),
             'ambiguous_name_groups': int(counts.gt(1).sum()),
             'ambiguous_places': int(ambiguous.sum()),
             'quarantined_tag_records': len(audit),
             'ambiguous_quarantined_tag_records': int((unproven & has_tags & ambiguous).sum()),
             'recollect_places': len(recollect), 'applied': apply}
    if apply:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        backup = write_database(deduped, db_path, audit, preserve=True, _expected_version=source_version)
        stats['backup'] = str(backup)
        # The full catalog includes completed places and their evidence. The
        # queue is only for collection, never the authoritative full dataset.
        deduped.to_csv(output / 'places_catalog.csv', index=False, encoding='utf-8-sig')
        stats['catalog_places'] = len(deduped)
        recollect.to_csv(output / 'recollect_places.csv', index=False, encoding='utf-8-sig')
        (output / 'migration_stats.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2))
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT / 'Flask_server/places.db')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'local_artifacts/migration')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    migrate(args.db, args.output_dir, args.apply)
