import pandas as pd
import glob
import os
import requests
import time
from tqdm import tqdm
from dotenv import load_dotenv

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


def run_pipeline():
    print("=" * 50)
    print("데이터 전처리 파이프라인 시작")
    print("=" * 50)

    current_file_path = os.path.abspath(__file__)
    preprocessing_dir = os.path.dirname(current_file_path)
    src_dir = os.path.dirname(preprocessing_dir)
    project_root = os.path.dirname(src_dir)

    env_path = os.path.join(project_root, ".env")
    load_dotenv(env_path)
    KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")

    if not KAKAO_API_KEY:
        print("KAKAO_API_KEY가 존재하지 않습니다.")
        return

    input_base_path = os.path.join(project_root, "Preprocess", "data", "chungnam_data")
    output_dir = os.path.join(project_root, "Preprocess", "data", "processed")
    os.makedirs(output_dir, exist_ok=True)
    
    final_output_file = os.path.join(output_dir, "chungnam_places_filtered.csv")

    # ── 1. 원본 CSV 파일 전체 탐색 ────────────────────────────────
    # 크롤링 단계에서 [지역 × 카테고리] 조합별로 분산 저장된 수십 개의 CSV를
    # 하위 폴더 재귀 탐색(**)으로 한 번에 수집한다.
    search_pattern = os.path.join(input_base_path, "**", "*.csv")
    file_list = glob.glob(search_pattern, recursive=True)

    if not file_list:
        print("크롤링된 원본 CSV 파일이 없습니다.")
        return

    # ── 2. 파일별로 읽어 메타데이터 부착 후 리스트에 누적 ────────
    # 각 CSV의 폴더명·파일명에서 지역·카테고리 정보를 역추출해
    # 별도 컬럼(eup_myeon_dong, search_category)으로 추가한다.
    # → 병합 후에도 출처 정보를 잃지 않고 후속 필터·검색에 활용 가능.
    all_data = []
    for file_path in file_list:
        try:
            df = pd.read_csv(file_path, encoding="utf-8-sig")
            if df.empty:
                continue

            region_name = file_path.split(os.sep)[-2]
            file_name = os.path.basename(file_path)

            if "_" in file_name:
                category_name = file_name.rsplit("_", 1)[1].replace(".csv", "")
            else:
                category_name = "기타"

            df["eup_myeon_dong"] = region_name
            df["search_category"] = category_name
            all_data.append(df)
        except Exception as e:
            print(f"파일 읽기 실패: {file_path}: {e}")

    if not all_data:
        print("유효한 데이터가 없습니다.")
        return

    # ── 3. 단일 DataFrame으로 통합 ────────────────────────────────
    # pd.concat으로 모든 파일을 하나의 테이블로 결합. ignore_index=True로
    # 인덱스를 새로 부여해 행 단위 처리(이터레이션·dropna 등)를 단순화한다.
    merged_df = pd.concat(all_data, ignore_index=True)
    print(f"병합 완료: 총 {len(merged_df)}행")

    # ── 4. 중복 행 제거 ───────────────────────────────────────────
    # 동일 장소가 여러 검색어(카테고리)로 중복 크롤링된 경우를 제거.
    # 가게명·주소 두 컬럼 조합을 키로 사용해, 가게명만 같은 별개 지점은 보존한다.
    if "가게명" in merged_df.columns and "주소" in merged_df.columns:
        before = len(merged_df)
        merged_df.drop_duplicates(subset=["가게명", "주소"], keep="first", inplace=True)
        removed = before - len(merged_df)
        print(f"중복 제거: {removed}개 제거됨")

    if "카테고리" in merged_df.columns:
        before = len(merged_df)
        merged_df = merged_df[~merged_df['카테고리'].isin(EXCLUDE_CATEGORIES)].reset_index(drop=True)
        print(f"카테고리 필터: {before - len(merged_df)}개 제거됨")
    
    # ── 6. 지오코딩 (주소 → 위도·경도 좌표 변환) ─────────────────
    # 카카오 로컬 API의 주소 검색 엔드포인트를 활용해, 각 장소의 주소 문자열을
    # 위도(y)·경도(x) 좌표로 변환한다. 좌표 정보는 이후 추천 알고리즘에서
    # 사용자 위치와의 거리 계산·반경 필터링·군집화의 핵심 입력값이 된다.
    merged_df["latitude"] = None
    merged_df["longitude"] = None

    def get_coords(addr):
        """카카오 로컬 API를 호출해 주소 1건에 대한 좌표 튜플을 반환."""
        url = "https://dapi.kakao.com/v2/local/search/address.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
        params = {"query": addr}
        try:
            r = requests.get(url, headers=headers, params=params)
            if r.status_code == 200:
                data = r.json()
                # documents[0] 의 x=경도, y=위도. 응답이 비어있는 경우는 변환 실패로 간주.
                if data["documents"]:
                    return (float(data["documents"][0]["y"]), float(data["documents"][0]["x"]))
        except:
            pass
        # 네트워크 오류·매칭 실패 모두 (None, None)으로 통일 처리 → 후속 dropna 단계에서 일괄 제거
        return (None, None)

    targets = merged_df.index
    print("지오코딩 연산 시작")
    for idx in tqdm(targets):
        addr = merged_df.loc[idx, "주소"]
        if pd.isna(addr) or str(addr).strip() == "":
            continue

        lat, lon = get_coords(str(addr))
        merged_df.loc[idx, "latitude"] = lat
        merged_df.loc[idx, "longitude"] = lon
        # 카카오 API 호출 한도(초당 호출 제한) 대응 + 서버 부하 분산을 위한 짧은 지연
        time.sleep(0.02)

    # ── 7. 좌표 변환 실패 항목 제거 ───────────────────────────────
    # 주소 표기 오류·구주소 미지원 등으로 좌표 매칭에 실패한 행은
    # 추천 알고리즘에서 사용 불가능하므로 데이터셋에서 일괄 제거한다.
    initial_count = len(merged_df)
    merged_df.dropna(subset=['latitude', 'longitude'], inplace=True)
    geocoded_count = len(merged_df)
    print(f"지오코딩 실패 데이터 제거: {initial_count - geocoded_count}개")

    merged_df['방문자수'] = merged_df['방문자수'].fillna(0).astype(float)
    merged_df['블로그수'] = merged_df['블로그수'].fillna(0).astype(float)
    merged_df['평점'] = merged_df['방문자수'] + (merged_df['블로그수'] * 0.3)
    merged_df['평점'] = merged_df['평점'].round(1)

    merged_df.to_csv(final_output_file, index=False, encoding="utf-8-sig")

    print("=" * 50)
    print(f"최종 데이터 처리 및 저장 완료: {final_output_file} (총 {len(merged_df)}행)")
    print("=" * 50)

if __name__ == "__main__":
    run_pipeline()