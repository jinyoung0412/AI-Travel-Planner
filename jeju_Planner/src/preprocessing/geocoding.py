# src/preprocessing/geocoding.py

import pandas as pd
import requests
import time
import os
import sys
from tqdm import tqdm
from dotenv import load_dotenv # 패키지 불러오기

def main():
    print("=" * 50)
    print("🗺️  지오코딩(좌표 변환) 작업 시작")
    print("=" * 50)

    # -----------------------------------------------------------
    # [1. 경로 설정] 프로젝트 루트 자동 탐색 및 환경변수 로드
    # -----------------------------------------------------------
    current_file_path = os.path.abspath(__file__)
    preprocessing_dir = os.path.dirname(current_file_path)
    src_dir = os.path.dirname(preprocessing_dir)
    project_root = os.path.dirname(src_dir)

    # 1-1. .env 파일 찾아서 로드하기 (금고 열기)
    env_path = os.path.join(project_root, '.env')
    load_dotenv(env_path)

    # 1-2. 환경변수에서 API 키 꺼내기
    KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")

    # [보안 체크] 키가 없으면 실행 중단
    if not KAKAO_API_KEY:
        print("🚨 [Error] .env 파일에서 'KAKAO_API_KEY'를 찾을 수 없습니다!")
        print(f"   -> 확인 경로: {env_path}")
        print("   -> .env 파일에 'KAKAO_API_KEY=본인키' 형식으로 저장했는지 확인하세요.")
        return

    # 데이터 경로 설정
    data_dir = os.path.join(project_root, "data", "processed")
    input_file = os.path.join(data_dir, "jeju_places_total.csv")
    output_file = os.path.join(data_dir, "jeju_places_with_coords_safe.csv")

    print(f"📂 Project Root: {project_root}")
    print(f"🔐 API Key:      {'*' * 5} (보안을 위해 숨김 처리됨)") 
    print(f"📂 Input File:   {input_file}")
    print(f"📂 Output File:  {output_file}")
    print("-" * 50)
    # -----------------------------------------------------------

    # 2. API 호출 함수 (내부 함수로 사용하거나 전역 변수 대신 인자로 전달)
    def get_coordinates(address):
        url = "https://dapi.kakao.com/v2/local/search/address.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
        params = {"query": address}

        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                result = response.json()
                if result['documents']:
                    x = result['documents'][0]['x']
                    y = result['documents'][0]['y']
                    return float(y), float(x)
        except Exception as e:
            # print(f"Error: {e}") # 너무 많은 에러 로그 방지
            pass
        return None, None

    # 3. 데이터 로드 전략 (이어하기 기능)
    if os.path.exists(output_file):
        print(f"💾 기존 작업 파일이 존재합니다. 작업을 이어서 진행합니다!")
        df = pd.read_csv(output_file, encoding='utf-8-sig')
    elif os.path.exists(input_file):
        print("🚀 새로운 작업을 시작합니다.")
        df = pd.read_csv(input_file, encoding='utf-8-sig')
        if 'latitude' not in df.columns:
            df['latitude'] = None
            df['longitude'] = None
    else:
        print(f"❌ 원본 데이터 파일이 없습니다.\n   -> 경로: {input_file}")
        print("   먼저 'data_integration.py'를 실행하여 통합 데이터를 생성해주세요.")
        return

    # 4. 작업해야 할 행(Row) 찾기
    target_indices = df[df['latitude'].isnull()].index
    print(f"📊 전체 데이터: {len(df)}개 | 🔴 남은 작업: {len(target_indices)}개")

    if len(target_indices) == 0:
        print("✅ 모든 데이터의 좌표 변환이 이미 완료되었습니다!")
        return

    # 5. 변환 시작
    save_interval = 100
    count = 0

    print("📡 카카오 API 호출 중...")
    for idx in tqdm(target_indices):
        address = df.loc[idx, 'address']
        
        if pd.isna(address) or str(address).strip() == "":
            continue

        lat, lon = get_coordinates(address)
        
        df.loc[idx, 'latitude'] = lat
        df.loc[idx, 'longitude'] = lon
        
        count += 1
        time.sleep(0.02) 

        if count % save_interval == 0:
            try:
                df.to_csv(output_file, index=False, encoding='utf-8-sig')
            except PermissionError:
                tqdm.write("⚠️ [Warning] 엑셀이 켜져 있어 중간 저장을 건너뜁니다.")
            except Exception as e:
                tqdm.write(f"⚠️ [Error] 저장 중 오류 발생: {e}")

    # 6. 최종 저장
    try:
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print("=" * 50)
        print(f"✅ 모든 작업 완료! '{output_file}' 저장 성공!")
        print("=" * 50)
    except PermissionError:
        print("🔥 [치명적 오류] 엑셀 파일이 열려있어 최종 저장을 못했습니다.")

if __name__ == "__main__":
    main()