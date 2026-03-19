import pandas as pd
import requests
import time
import os
import sys
from tqdm import tqdm
from dotenv import load_dotenv

def main():
    print("=" * 50)
    print("🗺️ 지오코딩(충남) 시작")
    print("=" * 50)

    current_path = os.path.abspath(__file__)
    preprocessing_dir = os.path.dirname(current_path)
    src_dir = os.path.dirname(preprocessing_dir)
    project_root = os.path.dirname(src_dir)

    env_path = os.path.join(project_root, ".env")
    load_dotenv(env_path)

    KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")

    if not KAKAO_API_KEY:
        print("❌ KAKAO_API_KEY가 .env에 없습니다.")
        return

    data_dir = os.path.join(project_root, "Preprocess","data", "processed")
    input_file = os.path.join(data_dir, "chungnam_places_total.csv")
    output_file = os.path.join(data_dir, "chungnam_places_with_coords_safe.csv")

    if os.path.exists(output_file):
        df = pd.read_csv(output_file, encoding="utf-8-sig")
        print("💾 기존 파일 감지됨 → 이어서 작업")
    else:
        df = pd.read_csv(input_file, encoding="utf-8-sig")
        df["latitude"] = None
        df["longitude"] = None

    targets = df[df["latitude"].isnull()].index

    print(f"📊 전체 {len(df)}행 | 남은 작업 {len(targets)}행")

    def get_coords(addr):
        url = "https://dapi.kakao.com/v2/local/search/address.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
        params = {"query": addr}

        try:
            r = requests.get(url, headers=headers, params=params)
            if r.status_code == 200:
                data = r.json()
                if data["documents"]:
                    return (float(data["documents"][0]["y"]), float(data["documents"][0]["x"]))
        except:
            pass
        return (None, None)

    count = 0
    for idx in tqdm(targets):
        addr = df.loc[idx, "주소"]
        if pd.isna(addr) or addr.strip() == "":
            continue

        lat, lon = get_coords(addr)
        df.loc[idx, "latitude"] = lat
        df.loc[idx, "longitude"] = lon

        count += 1
        time.sleep(0.02)

        if count % 100 == 0:
            try:
                df.to_csv(output_file, index=False, encoding="utf-8-sig")
            except:
                pass

    df.to_csv(output_file, index=False, encoding="utf-8-sig")

    print("=" * 50)
    print(f"✅ 지오코딩 완료 → {output_file}")
    print("=" * 50)

if __name__ == "__main__":
    main()
