"""
전처리 결과 CSV 두 개를 병합하여 SQLite 데이터베이스(places.db)에 적재한다.

데이터 흐름:
  chungnam_places_filtered.csv  (장소 메타데이터: 가게명·주소·좌표 등)
  blog_tags.csv                 (장소별 블로그 해시태그)
      │
      ▼  가게명 기준 left join
  places.db (Flask 서버에서 실시간 조회)

크롤링 → 정제 → 지오코딩 → 블로그 태그 수집 단계가 모두 완료된 후
최종 산출물을 추천 엔진이 사용할 형태로 변환하는 마지막 단계.
"""
import os
import sqlite3
import pandas as pd


# ── 경로 설정 ─────────────────────────────────────────────────
_ROOT         = os.path.join(os.path.dirname(__file__), '..', '..')
PLACES_CSV    = os.path.join(_ROOT, 'Preprocess', 'data', 'processed', 'chungnam_places_filtered.csv')
BLOG_TAGS_CSV = os.path.join(_ROOT, 'Preprocess', 'data', 'processed', 'blog_tags.csv')
DB_PATH       = os.path.join(_ROOT, 'Flask_server', 'places.db')


def extract_region(address) -> str:
    """주소 문자열에서 광역 지역명(천안/아산/기타)을 추출.

    Flask 추천 서버에서 사용자 선택 지역과 매칭하기 위한 색인용 컬럼으로 사용된다.
    """
    if pd.isna(address):
        return '기타'
    addr = str(address)
    if '천안시' in addr:
        return '천안'
    if '아산시' in addr:
        return '아산'
    return '기타'


def _read_csv(path):
    """다양한 인코딩으로 저장됐을 가능성이 있는 CSV를 안전하게 읽어온다.

    크롤러는 utf-8-sig로 저장하지만, 외부에서 편집된 파일이 cp949·euc-kr 등
    다른 인코딩으로 변환됐을 수 있어 네 가지 후보를 순차 시도한다.
    """
    for enc in ('utf-8-sig', 'utf-8', 'cp949', 'euc-kr'):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, ValueError):
            continue
    raise ValueError(f'인코딩 감지 실패: {path}')


def build():
    print('CSV 로드 중...')
    places    = _read_csv(PLACES_CSV)
    blog_tags = _read_csv(BLOG_TAGS_CSV)[['가게명', 'blog_tags']]

    # ── 1. 두 CSV를 단일 테이블로 병합 ────────────────────────────
    # 장소 메타데이터(좌표·방문자수 등)에 블로그 태그를 가게명 기준으로 left join.
    # 블로그 태그가 없는 장소도 보존되며, 해당 컬럼은 NaN으로 채워진다.
    df = places.merge(blog_tags, on='가게명', how='left')

    # ── 2. 크롤링 결함 데이터 제거 ────────────────────────────────
    # 일부 장소는 네이버 지도의 카테고리명 표기 이슈로 인해 동일 명칭이
    # 중복 부착된 형태(예: "박물관박물관")로 수집되는 경우가 있어 후처리로 제거.
    dup_patterns = [
        '박물관박물관', '미술관미술관', '기념관기념관', '전시관전시관',
    ]
    before = len(df)
    for pat in dup_patterns:
        df = df[~df['가게명'].str.contains(pat, na=False)]
    removed = before - len(df)
    if removed:
        print(f'중복명 제거: {removed}개')

    # ── 3. 지역 색인 컬럼 추가 ────────────────────────────────────
    # 주소 문자열에서 광역 지역(천안/아산)을 추출하여 별도 컬럼으로 저장.
    # 추천 단계에서 사용자가 선택한 지역으로 빠르게 필터링하기 위한 색인용 컬럼.
    df['지역'] = df['주소'].apply(extract_region)

    cheonan = (df['지역'] == '천안').sum()
    asan    = (df['지역'] == '아산').sum()
    other   = (df['지역'] == '기타').sum()
    print(f'총 {len(df)}개 → 천안 {cheonan}, 아산 {asan}, 기타 {other}')

    # ── 4. SQLite DB로 적재 + 인덱스 생성 ─────────────────────────
    # if_exists='replace': 기존 places 테이블을 새 데이터로 교체.
    # 자주 조회되는 컬럼(지역·카테고리)에 인덱스를 생성하여 실시간 추천 쿼리 성능 확보.
    print(f'DB 저장 중: {DB_PATH}')
    conn = sqlite3.connect(DB_PATH)
    df.to_sql('places', conn, if_exists='replace', index=False)

    conn.execute('CREATE INDEX IF NOT EXISTS idx_region   ON places(지역)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_category ON places(카테고리)')
    conn.commit()
    conn.close()

    print('완료.')


if __name__ == '__main__':
    build()
