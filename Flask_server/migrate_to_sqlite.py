"""
CSV 두 개 → places.db (SQLite) 변환 스크립트.
최초 1회 또는 CSV 데이터 갱신 후 실행.
"""
import os
import sqlite3
import pandas as pd

_ROOT         = os.path.join(os.path.dirname(__file__), '..')
PLACES_CSV    = os.path.join(_ROOT, 'Preprocess', 'data', 'processed', 'chungnam_places_filtered.csv')
BLOG_TAGS_CSV = os.path.join(_ROOT, 'Preprocess', 'data', 'processed', 'blog_tags.csv')
DB_PATH       = os.path.join(os.path.dirname(__file__), 'places.db')


def extract_region(address) -> str:
    if pd.isna(address):
        return '기타'
    addr = str(address)
    if '천안시' in addr:
        return '천안'
    if '아산시' in addr:
        return '아산'
    return '기타'


def _read_csv(path):
    for enc in ('utf-8-sig', 'utf-8', 'cp949', 'euc-kr'):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, ValueError):
            continue
    raise ValueError(f'인코딩 감지 실패: {path}')


def migrate():
    print('CSV 로드 중...')
    places    = _read_csv(PLACES_CSV)
    blog_tags = _read_csv(BLOG_TAGS_CSV)[['가게명', 'blog_tags']]

    df = places.merge(blog_tags, on='가게명', how='left')

    # 크롤링 오류로 카테고리명이 두 번 붙은 장소 제거
    dup_patterns = [
        '박물관박물관', '미술관미술관', '기념관기념관', '전시관전시관',
    ]
    before = len(df)
    for pat in dup_patterns:
        df = df[~df['가게명'].str.contains(pat, na=False)]
    removed = before - len(df)
    if removed:
        print(f'중복명 제거: {removed}개')

    df['지역'] = df['주소'].apply(extract_region)

    cheonan = (df['지역'] == '천안').sum()
    asan    = (df['지역'] == '아산').sum()
    other   = (df['지역'] == '기타').sum()
    print(f'총 {len(df)}개 → 천안 {cheonan}, 아산 {asan}, 기타 {other}')

    print(f'DB 저장 중: {DB_PATH}')
    conn = sqlite3.connect(DB_PATH)
    df.to_sql('places', conn, if_exists='replace', index=False)

    conn.execute('CREATE INDEX IF NOT EXISTS idx_region   ON places(지역)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_category ON places(카테고리)')
    conn.commit()
    conn.close()

    print('완료.')


if __name__ == '__main__':
    migrate()
