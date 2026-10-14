"""Remove repeated identities; preserve different branches with the same name."""
import argparse
import shutil
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from place_identity import ensure_ids


def remove_duplicate_places(file_path=ROOT / 'Preprocess/data/processed/chungnam_places_filtered.csv'):
    df = ensure_ids(pd.read_csv(file_path, dtype={'provider_place_id': str, 'place_id': str}))
    deduped = df.drop_duplicates('place_id', keep='last')
    shutil.copy2(file_path, str(file_path) + '.bak')
    deduped.to_csv(file_path, index=False, encoding='utf-8-sig')
    print(f'장소 ID 중복 제거: {len(df)} → {len(deduped)} (원본 .bak 보존)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=ROOT / 'Preprocess/data/processed/chungnam_places_filtered.csv')
    remove_duplicate_places(parser.parse_args().input)
