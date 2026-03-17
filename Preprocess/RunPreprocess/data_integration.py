import pandas as pd
import glob
import os
import sys

def integrate_data():
    print("=" * 50)
    print("데이터 통합(Integration) 시작")
    print("=" * 50)

    current_file_path = os.path.abspath(__file__)
    preprocessing_dir = os.path.dirname(current_file_path)
    src_dir = os.path.dirname(preprocessing_dir)
    project_root = os.path.dirname(src_dir)

    input_base_path = os.path.join(project_root, "Preprocess","data", "chungnam_data")
    output_dir = os.path.join(project_root, "Preprocess","data", "processed")
    os.makedirs(output_dir, exist_ok=True)

    print(f"📂 Input Path: {input_base_path}")
    print(f"📂 Output Path: {output_dir}")
    print("-" * 50)

    search_pattern = os.path.join(input_base_path, "**", "*.csv")
    file_list = glob.glob(search_pattern, recursive=True)

    print(f"🔍 감지된 CSV 파일 수: {len(file_list)}개")

    if len(file_list) == 0:
        print("❌ 병합할 파일이 없습니다. 크롤링을 먼저 실행하세요.")
        return

    all_data = []
    empty_count = 0

    for file_path in file_list:
        try:
            df = pd.read_csv(file_path, encoding="utf-8-sig")

            if df.empty:
                empty_count += 1
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
            print(f"⚠️ 파일 읽기 실패: {file_name}: {e}")

    print(f"ℹ️ 빈 파일 제외: {empty_count}개")

    if not all_data:
        print("❌ 모든 파일이 비어 있음.")
        return

    merged_df = pd.concat(all_data, ignore_index=True)
    print(f"🧩 병합 완료: 총 {len(merged_df)}행")

    if "name" in merged_df.columns and "address" in merged_df.columns:
        before = len(merged_df)
        merged_df.drop_duplicates(subset=["name", "address"], inplace=True)
        removed = before - len(merged_df)
        print(f"🧹 중복 제거: {removed}개 제거됨")

    save_path = os.path.join(output_dir, "chungnam_places_total.csv")
    merged_df.to_csv(save_path, index=False, encoding="utf-8-sig")

    print("=" * 50)
    print(f"✅ 저장 완료: {save_path}")
    print("=" * 50)

if __name__ == "__main__":
    integrate_data()
