import pandas as pd
import os

file_path = r"C:\AI-Travel-Planner\Preprocess\data\processed\chungnam_places_with_coords_safe.csv"

df = pd.read_csv(file_path, encoding="utf-8-sig")

failed = df[df["latitude"].isnull()]

print(f"🔥 좌표 실패 데이터: {len(failed)}개")
print("="*50)
print(failed[["가게명","주소"]].head(20))
print("="*50)
