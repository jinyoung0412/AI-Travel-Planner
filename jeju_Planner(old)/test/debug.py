import pandas as pd
import requests

# ==========================================
KAKAO_API_KEY = "8db1f70978458de7073f21441ce2c60a"
# ==========================================

def test_geocoding():
    # 1. 데이터 확인
    print("📂 데이터 파일 로딩 중...")
    try:
        df = pd.read_csv("jeju_places_total.csv", encoding='utf-8-sig')
    except:
        print("❌ 파일을 찾을 수 없습니다.")
        return

    # 2. 주소 데이터 눈으로 확인하기 (상위 5개)
    print("\n🔍 [데이터 확인] 주소 컬럼의 실제 모습:")
    print("-" * 30)
    print(df['address'].head(5))
    print("-" * 30)

    # 3. 실제 API 테스트 (첫 번째 주소로 시도)
    if len(df) > 0:
        sample_address = df['address'].iloc[0]
        print(f"\n🚀 [API 테스트] 검색할 주소: '{sample_address}'")
        
        url = "https://dapi.kakao.com/v2/local/search/address.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
        params = {"query": sample_address}

        response = requests.get(url, headers=headers, params=params)
        
        print(f"📡 응답 상태 코드: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"📄 응답 결과(개수): {data['meta']['total_count']}개")
            print(f"📄 응답 내용: {data}")
        else:
            print("⚠️ API 호출 실패! 키가 잘못되었거나 권한이 없습니다.")
    else:
        print("❌ 데이터가 비어있습니다.")

if __name__ == "__main__":
    test_geocoding()