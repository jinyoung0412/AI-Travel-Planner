import pandas as pd

def remove_duplicate_places():
    file_path = r'C:\AI-Travel-Planner\Preprocess\data\processed\chungnam_places_filtered.csv'
    
    df = pd.read_csv(file_path)
    initial_count = len(df)
    
    df_dedup = df.drop_duplicates(subset=['가게명'], keep='first')
    final_count = len(df_dedup)
    
    df_dedup.to_csv(file_path, index=False, encoding='utf-8-sig')
    
    print(f"중복 제거 완료: 기존 {initial_count}개 -> 변경 {final_count}개")

if __name__ == "__main__":
    remove_duplicate_places()