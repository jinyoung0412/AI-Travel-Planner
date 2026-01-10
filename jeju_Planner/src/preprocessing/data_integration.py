# src/preprocessing/data_integration.py

import pandas as pd
import glob
import os
import sys

def integrate_data():
    print("=" * 50)
    print("🔄 데이터 통합(Integration) 작업 시작")
    print("=" * 50)

    # -----------------------------------------------------------
    # [1. 경로 설정] 프로젝트 루트를 기준으로 경로 자동 탐색
    # -----------------------------------------------------------
    current_file_path = os.path.abspath(__file__)
    preprocessing_dir = os.path.dirname(current_file_path) # src/preprocessing
    src_dir = os.path.dirname(preprocessing_dir)           # src
    project_root = os.path.dirname(src_dir)                # JEJU-TRAVEL-AI (ROOT)

    # 입력 경로: data/raw/output/jeju_data (크롤링된 수천 개의 파일)
    input_base_path = os.path.join(project_root, "data", "raw", "output", "jeju_data")
    
    # 출력 경로: data/processed (하나로 합친 파일 저장)
    output_dir = os.path.join(project_root, "data", "processed")
    os.makedirs(output_dir, exist_ok=True) # 폴더 없으면 생성

    print(f"📂 Project Root: {project_root}")
    print(f"📂 Input Path:   {input_base_path}")
    print(f"📂 Output Path:  {output_dir}")
    print("-" * 50)

    # -----------------------------------------------------------
    # [2. 파일 리스트 가져오기 및 병합 루프]
    # -----------------------------------------------------------
    # jeju_data/**/*.csv (하위 폴더 포함 모든 csv 검색)
    search_pattern = os.path.join(input_base_path, "**", "*.csv")
    file_list = glob.glob(search_pattern, recursive=True)

    print(f"🔍 검색된 CSV 파일 수: {len(file_list)}개")

    if len(file_list) == 0:
        print("❌ 병합할 데이터가 없습니다. 크롤링이 완료되었는지 확인해주세요.")
        return

    all_data = []
    empty_file_count = 0
    
    for file_path in file_list:
        try:
            # CSV 파일 읽기
            df = pd.read_csv(file_path, encoding='utf-8-sig')
            
            # [중요] 빈 파일(검색 결과 없음)인 경우 건너뛰기
            if df.empty:
                empty_file_count += 1
                continue

            # 파일 경로에서 메타데이터 추출 (폴더명=지역명)
            # 예: .../jeju_data/제주_가시리/제주_가시리_맛집.csv
            path_parts = file_path.split(os.sep) 
            
            # 폴더명 (예: 제주_가시리)
            region_name = path_parts[-2]
            
            # 파일명 (예: 제주_가시리_맛집.csv)
            file_name = path_parts[-1]
            
            # 파일명에서 카테고리 추출
            # (파일명 규칙에 따라 '_' 기준으로 뒤에서 첫 번째가 카테고리)
            if "_" in file_name:
                category_name = file_name.rsplit("_", 1)[1].replace(".csv", "")
            else:
                category_name = "기타"

            # 데이터프레임에 지역, 카테고리 컬럼 추가
            df['eup_myeon_dong'] = region_name  
            df['search_category'] = category_name 
            
            all_data.append(df)

        except Exception as e:
            # 읽기 실패한 파일은 로그만 남기고 계속 진행
            print(f"⚠️ 파일 읽기 실패 ({os.path.basename(file_path)}): {e}")

    # -----------------------------------------------------------
    # [3. 데이터 병합 및 중복 제거]
    # -----------------------------------------------------------
    print(f"ℹ️  빈 파일(결과 없음) 제외됨: {empty_file_count}개")

    if all_data:
        # 하나로 합치기
        merged_df = pd.concat(all_data, ignore_index=True)
        print(f"🧩 1차 병합 완료: 총 {len(merged_df)}행")
        
        # 중복 제거 (이름과 주소가 같으면 중복으로 간주)
        if 'name' in merged_df.columns and 'address' in merged_df.columns:
            initial_len = len(merged_df)
            merged_df.drop_duplicates(subset=['name', 'address'], inplace=True)
            removed_count = initial_len - len(merged_df)
            print(f"🧹 중복 데이터 제거: {removed_count}행 삭제됨")

        # 최종 저장
        output_filename = "jeju_places_total.csv"
        save_path = os.path.join(output_dir, output_filename)
        
        merged_df.to_csv(save_path, index=False, encoding="utf-8-sig")
        
        print("=" * 50)
        print(f"✅ 통합 완료! 파일 저장됨: {save_path}")
        print(f"📊 최종 데이터 개수: {len(merged_df)}행")
        print(f"📂 수집된 컬럼: {list(merged_df.columns)}")
        print("=" * 50)
        
    else:
        print("❌ 유효한 데이터가 하나도 없습니다. (모든 파일이 비어있거나 에러)")

if __name__ == "__main__":
    integrate_data()