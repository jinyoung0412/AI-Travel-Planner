# check_failed.py (임시 생성 후 실행)
import pandas as pd
import os

# 파일 경로 (본인 경로에 맞게 수정)
file_path = r"c:\Jeju-Travel-AI\data\processed\jeju_places_with_coords_safe.csv"

df = pd.read_csv(file_path, encoding='utf-8-sig')

# 좌표가 없는 녀석들만 추출
failed_df = df[df['latitude'].isnull()]

print(f"🔥 실패한 데이터: 총 {len(failed_df)}개")
print("="*50)
# 주소와 이름만 10개 찍어보기
print(failed_df[['name', 'address']].head(10))
print("="*50)