import pandas as pd
import requests

KAKAO_API_KEY = "YOUR_TEST_KEY"

def test():
    df = pd.read_csv("chungnam_places_total.csv", encoding="utf-8-sig")

    print("🔍 주소 샘플:")
    print(df["address"].head(3))

    addr = df["address"].iloc[0]

    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": addr}

    r = requests.get(url, headers=headers, params=params)
    print("응답 코드:", r.status_code)

    if r.status_code == 200:
        print(r.json())

if __name__ == "__main__":
    test()
