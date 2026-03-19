import pandas as pd

def remove_missing_coordinates(input_path, output_path):
    df = pd.read_csv(input_path, encoding='utf-8-sig')
    
    filtered_df = df.dropna(subset=['latitude', 'longitude'])
    
    filtered_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    
    print(f"원본 데이터 개수: {len(df)}")
    print(f"정제 후 데이터 개수: {len(filtered_df)}")
    print(f"삭제된 데이터 개수: {len(df) - len(filtered_df)}")

if __name__ == "__main__":
    input_file = "C:\AI-Travel-Planner\Preprocess\data\processed\chungnam_places_with_coords_safe.csv"
    output_file = "C:\AI-Travel-Planner\Preprocess\data\processed\chungnam_places_filtered.csv"
    
    remove_missing_coordinates(input_file, output_file)