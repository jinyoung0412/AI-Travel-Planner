import pandas as pd
import folium
from sklearn.cluster import KMeans
import numpy as np
import os

TRAVEL_DAYS = 3
TOP_N = 10
LATITUDE_WEIGHT = 1.1

COLORS = [
    "red", "blue", "green", "purple", "orange",
    "darkred", "cadetblue", "pink", "gray", "black"
]

def main():
    print("="*50)
    print("🤖 충남 여행 AI 클러스터링 시작")
    print("="*50)

    curr = os.path.abspath(__file__)
    ai_model_dir = os.path.dirname(curr)
    src_dir = os.path.dirname(ai_model_dir)
    root = os.path.dirname(src_dir)

    input_path = os.path.join(root, "data", "processed", "chungnam_places_with_coords_safe.csv")
    output_dir = os.path.join(root, "data", "results")
    os.makedirs(output_dir, exist_ok=True)

    output_csv = os.path.join(output_dir, "chungnam_course_result.csv")
    output_map = os.path.join(output_dir, "chungnam_course_visualization.html")

    df_raw = pd.read_csv(input_path, encoding="utf-8-sig")
    df = df_raw.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)

    print(f"📌 데이터 개수: {len(df)}개")

    X = df[["latitude", "longitude"]].values
    X_scaled = X.copy()
    X_scaled[:, 0] *= LATITUDE_WEIGHT

    kmeans = KMeans(n_clusters=TRAVEL_DAYS, random_state=42, n_init=10)
    kmeans.fit(X_scaled)

    df["cluster"] = kmeans.labels_

    centers = kmeans.cluster_centers_
    centers_original = centers.copy()
    centers_original[:, 0] /= LATITUDE_WEIGHT

    final = []

    for i in range(TRAVEL_DAYS):
        cluster_points = df[df["cluster"] == i]

        if len(cluster_points) <= TOP_N:
            final.append(cluster_points)
        else:
            final.append(cluster_points.sample(TOP_N))

    result_df = pd.concat(final)
    result_df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    m = folium.Map(location=[df["latitude"].mean(), df["longitude"].mean()], zoom_start=10)

    for _, row in result_df.iterrows():
        cid = int(row["cluster"])
        folium.Marker(
            location=[row["latitude"], row["longitude"]],
            icon=folium.Icon(color=COLORS[cid], icon="star"),
            popup=f"{row.get('name','')}"
        ).add_to(m)

    for i, center in enumerate(centers_original):
        folium.CircleMarker(
            location=center,
            radius=20,
            color="black",
            fill=True,
            fill_color=COLORS[i % len(COLORS)],
            fill_opacity=0.4
        ).add_to(m)

    m.save(output_map)

    print("=" * 50)
    print("📄 결과 CSV:", output_csv)
    print("🗺️ 지도 HTML:", output_map)
    print("=" * 50)

if __name__ == "__main__":
    main()
