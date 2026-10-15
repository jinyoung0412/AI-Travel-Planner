"""Remove repeated identities; preserve different branches with the same name."""
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from Preprocess.RunPreprocess.build_database import _audit_frame, _read_csv, merge_verified_tags
from Preprocess.RunPreprocess.clean_existing_data import _replace_csv


def remove_duplicate_places(file_path=ROOT / 'Preprocess/data/processed/chungnam_places_filtered.csv'):
    df = _read_csv(file_path)
    # Latest non-empty metadata wins; valid posts from earlier duplicates survive.
    deduped, quarantine = merge_verified_tags(df, df.iloc[:0], metadata_mode='update')
    if not quarantine.empty:
        audit_path = Path(str(file_path) + '.quarantine.csv')
        audit = _audit_frame(quarantine)
        if audit_path.exists():
            audit = pd.concat([_read_csv(audit_path), audit], ignore_index=True)
        audit = audit.drop_duplicates()
        # Publish audit first: failure must never remove the only copy of proof.
        _replace_csv(audit_path, lambda temporary: audit.to_csv(temporary, index=False, encoding='utf-8-sig'))
    _replace_csv(file_path, lambda temporary: deduped.to_csv(temporary, index=False, encoding='utf-8-sig'))
    print(f'장소 ID 중복 제거: {len(df)} → {len(deduped)} (원본 백업 보존)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=ROOT / 'Preprocess/data/processed/chungnam_places_filtered.csv')
    remove_duplicate_places(parser.parse_args().input)
