"""Raw crawler CSVs -> identity-preserving, resumable address geocoding."""
import math
import json
import hashlib
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from place_identity import ensure_ids, text
from Preprocess.RunPreprocess.build_database import merge_verified_tags, _audit_frame, _read_csv
from Preprocess.crawler.categories import CATEGORIES
from Preprocess.crawler.http_client import get as _get
from Preprocess.crawler.storage import atomic_output

EXCLUDE_CATEGORIES = {
    # 골프 (중년층 특화 운동 시설 — 나들이 목적지 아님)
    '스크린골프장', '실내골프연습장', '실외골프연습장',
    '파크골프장', '골프장코스', 'par3골프장', '골프연습장', '골프용품',
    # 격투/무예 도장 (정기 훈련 목적, 여행지 아님)
    '복싱,권투장', '킥복싱', '무예,격투기', '태권도장',
    '검도장', '유도장', '합기도', '가라테,공수도',
    # 일반 운동 시설 (정기 이용 목적)
    '체육관', '실내체육관', '구민체육센터',
    '풋살장', '배드민턴장', '축구장', '종합운동장', '스쿼시장',
    '보조경기장', '야구연습장',
    # 부속/인프라 (독립 장소가 아닌 것)
    '부속시설', '부속건물', '콘도,리조트부속건물', '펜션부속시설',
    '화장실', '고속도로시설', '관리,안내', '예정,공사중',
    # 유흥
    '유흥주점', '단란주점',
    # 볼링장, 스크린야구장, 당구장, 수영장, 스케이트장 계열은 나들이 목적지로 유지
}



def get_coords(address, api_key):
    """Address geocoding only, never a measured travel distance/time."""
    try:
        response = _get('https://dapi.kakao.com/v2/local/search/address.json', kind='geocode',
                        headers={'Authorization': f'KakaoAK {api_key}'}, params={'query': address}, timeout=10)
        docs = response.json().get('documents', [])
        if docs:
            lat, lng = float(docs[0]['y']), float(docs[0]['x'])
            if math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError, IndexError):
        return None, None
    return None, None


def source_metadata(path):
    """Support both saver flat filenames and historical region subdirectories."""
    path = Path(path)
    stem = path.stem.removeprefix('충남_')
    for category in sorted(CATEGORIES, key=len, reverse=True):
        suffix = '_' + category.replace(' ', '_')
        if stem.endswith(suffix):
            return stem[:-len(suffix)].replace('_', ' '), category
    # Unknown historical search categories are still retained.
    region, separator, category = stem.rpartition('_')
    return (region.replace('_', ' ') if separator else path.parent.name.replace('_', ' '),
            category.replace('_', ' ') if separator else '기타')


def read_sources(input_dir):
    frames = []
    for path in sorted(Path(input_dir).rglob('*.csv')):
        if path.name.endswith('.quarantine.csv'):
            continue
        # A malformed file aborts the stage instead of silently publishing a partial dataset.
        frame = pd.read_csv(path, encoding='utf-8-sig', dtype={'provider_place_id': str, 'place_id': str})
        if not {'가게명', '주소'}.issubset(frame.columns):
            raise ValueError(f'원본 CSV 필수 컬럼 누락: {path}')
        if frame.empty:
            continue
        region, category = source_metadata(path)
        for field, default in (('search_region', region), ('search_category', category)):
            existing = frame.get(field, pd.Series('', index=frame.index)).fillna('').astype(str)
            frame[field] = existing.where(existing.str.strip().ne(''), default)
        frame['eup_myeon_dong'] = frame.get('eup_myeon_dong', frame['search_region']).fillna(frame['search_region'])
        frame['source_file'] = str(path.relative_to(input_dir))
        frames.append(frame)
    if not frames:
        raise ValueError('크롤링된 유효한 원본 CSV 파일이 없습니다.')
    return pd.concat(frames, ignore_index=True)


def valid_coords(row):
    try:
        lat, lng = float(row['latitude']), float(row['longitude'])
        return math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180
    except (KeyError, TypeError, ValueError):
        return False


def save_frame(path, frame):
    with atomic_output(path, encoding='utf-8-sig') as stream:
        frame.to_csv(stream, index=False)


def run_pipeline(input_dir=None, output_dir=None, api_key=None):
    input_dir = Path(input_dir or os.getenv('TRAVEL_DATA_DIR', ROOT / 'Preprocess/data/chungnam_data'))
    output_dir = Path(output_dir or ROOT / 'Preprocess/data/processed')
    final_path = output_dir / 'chungnam_places_filtered.csv'
    frame = read_sources(input_dir)
    invalid = frame['가게명'].map(text).eq('') | frame['주소'].map(text).eq('')
    rejected = frame[invalid].copy()
    rejected['preprocess_error'] = 'missing_name_or_address'
    frame = ensure_ids(frame[~invalid])
    # Prefer the provider's category over a search fallback when merging repeated IDs.
    sources = {}
    for pid, group in frame.groupby('place_id', sort=False):
        provenance = group.reindex(columns=['search_region', 'search_category', 'source_file', 'category_source']).fillna('')
        sources[pid] = json.dumps(provenance.drop_duplicates().to_dict('records'), ensure_ascii=False)
    source_type = frame.get('category_source', pd.Series('', index=frame.index))
    quality = source_type.map({'provider': 2, 'search_fallback': 0}).fillna(1)
    frame = frame.assign(_provider_category=quality).sort_values('_provider_category', kind='stable')
    frame, quarantine = merge_verified_tags(frame.drop(columns='_provider_category'),
                                            pd.DataFrame(), metadata_mode='update')
    if not quarantine.empty:
        audit_path = output_dir / 'preprocess_quarantine.csv'
        audit = _audit_frame(quarantine)
        if audit_path.exists():
            audit = pd.concat([_read_csv(audit_path), audit], ignore_index=True)
        save_frame(audit_path, audit.drop_duplicates())
    frame['collection_sources'] = frame['place_id'].map(sources)
    if '카테고리' in frame:
        frame = frame[~frame['카테고리'].isin(EXCLUDE_CATEGORIES)]
    frame = frame.reset_index(drop=True)
    for field in ('latitude', 'longitude'):
        if field not in frame:
            frame[field] = None
    if final_path.exists():
        previous = pd.read_csv(final_path, encoding='utf-8-sig', dtype={'place_id': str, 'provider_place_id': str})
        previous = ensure_ids(previous).drop_duplicates('place_id', keep='last').set_index('place_id')
        for index, row in frame.iterrows():
            if not valid_coords(row) and row['place_id'] in previous.index:
                cached = previous.loc[row['place_id']]
                if cached['identity_key'] == row['identity_key'] and valid_coords(cached):
                    frame.loc[index, ['latitude', 'longitude']] = cached[['latitude', 'longitude']].to_numpy()
    pending = [i for i, row in frame.iterrows() if not valid_coords(row)]
    # Read historical CSV checkpoints; new per-place journals avoid rewriting the dataset per request.
    checkpoint = output_dir / 'geocoding_checkpoint.csv'
    if checkpoint.exists():
        cached_frame = pd.read_csv(checkpoint, encoding='utf-8-sig', dtype={'place_id': str})
        cached_rows = {r['place_id']: r for r in cached_frame.to_dict('records')}
        for index in pending:
            row = frame.loc[index]
            cached = cached_rows.get(row['place_id'], {})
            if cached.get('identity_key') == row['identity_key'] and valid_coords(cached):
                frame.loc[index, ['latitude', 'longitude']] = [cached['latitude'], cached['longitude']]
    journal = output_dir / 'geocoding_checkpoint'
    for index in pending:
        row = frame.loc[index]
        record_path = journal / (hashlib.sha256(row['place_id'].encode()).hexdigest() + '.json')
        if record_path.exists():
            cached = json.loads(record_path.read_text(encoding='utf-8'))
            if cached.get('identity_key') == row['identity_key'] and valid_coords(cached):
                frame.loc[index, ['latitude', 'longitude']] = [cached['latitude'], cached['longitude']]
    pending = [i for i, row in frame.iterrows() if not valid_coords(row)]
    if pending and not api_key:
        load_dotenv(ROOT / '.env')
        api_key = os.getenv('KAKAO_API_KEY')
    if pending and not api_key:
        raise ValueError('KAKAO_API_KEY가 존재하지 않습니다. 외부 호출은 수행하지 않았습니다.')
    for index in tqdm(pending, desc='주소 지오코딩'):
        frame.loc[index, ['latitude', 'longitude']] = get_coords(text(frame.loc[index, '주소']), api_key)
        row = frame.loc[index]
        record_path = journal / (hashlib.sha256(row['place_id'].encode()).hexdigest() + '.json')
        with atomic_output(record_path) as stream:
            json.dump({key: row[key] for key in ('place_id', 'identity_key', 'latitude', 'longitude')}, stream)
        time.sleep(0.02)
    save_frame(checkpoint, frame)
    valid = pd.Series([valid_coords(row) for _, row in frame.iterrows()], index=frame.index, dtype=bool)
    failed = frame[~valid].copy()
    failed['preprocess_error'] = 'geocoding_failed'
    save_frame(output_dir / 'preprocess_rejected.csv', pd.concat([rejected, failed], ignore_index=True))
    frame = frame[valid].copy()
    if frame.empty:
        raise ValueError('사용 가능한 좌표가 없습니다. 기존 최종 CSV를 보존했습니다.')
    for field in ('방문자수', '블로그수'):
        values = frame.get(field, pd.Series(0, index=frame.index)).astype(str).str.replace(',', '', regex=False)
        frame[field] = pd.to_numeric(values, errors='coerce').fillna(0).clip(lower=0)
    frame['평점'] = (frame['방문자수'] + frame['블로그수'] * 0.3).round(1)
    save_frame(final_path, frame)
    print(f'처리 완료: {len(frame)}곳, 보류 {len(rejected) + len(failed)}행 -> {final_path}')
    return frame


if __name__ == '__main__':
    run_pipeline()
