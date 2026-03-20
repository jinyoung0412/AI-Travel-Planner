import pandas as pd
import os

def split_data_by_region():
    print("=" * 50)
    print("시/군 단위 데이터 분할 시작")
    print("=" * 50)

    current_file_path = os.path.abspath(__file__)
    preprocessing_dir = os.path.dirname(current_file_path)
    src_dir = os.path.dirname(preprocessing_dir)
    project_root = os.path.dirname(src_dir)

    data_dir = os.path.join(project_root, "Preprocess", "data", "processed")
    input_file = os.path.join(data_dir, "chungnam_places_filtered.csv")
    output_dir = os.path.join(data_dir, "regions")

    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(input_file):
        print("통합 필터링 파일이 존재하지 않습니다.")
        return

    df = pd.read_csv(input_file, encoding="utf-8-sig")

    regions = [
        '천안', '아산', '서산', '태안', '공주', '부여', 
        '보령', '서천', '홍성', '예산', '당진', '논산', 
        '계룡', '청양', '금산'
    ]

    for region in regions:
        region_df = df[df['주소'].str.contains(region, na=False)]
        
        if not region_df.empty:
            output_file = os.path.join(output_dir, f"{region}_places.csv")
            region_df.to_csv(output_file, index=False, encoding="utf-8-sig")
            print(f"{region} 지역 파일 생성 완료: {len(region_df)}행")
        else:
            print(f"{region} 지역 데이터가 없습니다.")

    print("=" * 50)
    print("모든 지역 분할 완료")
    print("=" * 50)

if __name__ == "__main__":
    split_data_by_region()