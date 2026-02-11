# src/ai_model/clustering.py

import pandas as pd
import folium
from sklearn.cluster import KMeans
import os
import sys
import numpy as np

# ==========================================
# 1. 설정 (Configuration)
# ==========================================
# [핵심] 사용자가 3박 4일을 원하면 3, 2박 3일을 원하면 2...
TRAVEL_DAYS = 3      
TOP_N = 10           

# [밸런스 패치] 위도 가중치 (1.5배)
# 옆으로 길쭉한 제주도 지형 특성을 반영하여 남/북으로 너무 찢어지지 않게 함
LATITUDE_WEIGHT = 1.5

COLORS = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'cadetblue', 'pink', 'gray', 'black']

def main():
    print("=" * 50)
    print("🤖 AI 코스 추천 및 시각화 (Clustering) 시작")
    print("=" * 50)

    # -----------------------------------------------------------
    # [경로 설정] 프로젝트 루트 자동 탐색
    # -----------------------------------------------------------
    current_file_path = os.path.abspath(__file__)
    ai_model_dir = os.path.dirname(current_file_path) # src/ai_model
    src_dir = os.path.dirname(ai_model_dir)           # src
    project_root = os.path.dirname(src_dir)           # JEJU-TRAVEL-AI (ROOT)

    # 입력 파일: 전처리 및 지오코딩이 완료된 데이터
    input_path = os.path.join(project_root, 'data', 'processed', 'jeju_places_with_coords_safe.csv')

    # 출력 폴더: data/results (결과물 저장용 폴더 생성)
    output_dir = os.path.join(project_root, 'data', 'results')
    os.makedirs(output_dir, exist_ok=True)

    # 출력 파일 경로
    output_map_path = os.path.join(output_dir, 'jeju_course_visualization.html')
    output_csv_path = os.path.join(output_dir, 'jeju_course_result.csv')

    print(f"📂 Project Root: {project_root}")
    print(f"📂 Input Data:   {input_path}")
    print(f"📂 Output Map:   {output_map_path}")
    print("-" * 50)

    # -----------------------------------------------------------
    # [Step 1] 데이터 로딩 및 전처리
    # -----------------------------------------------------------
    print("🚀 [Step 1] 데이터 로딩 중...")
    
    if not os.path.exists(input_path):
        print(f"❌ [Error] 입력 파일을 찾을 수 없습니다.\n   -> 경로: {input_path}")
        print("   먼저 'geocoding.py'를 실행하여 좌표 데이터를 생성해주세요.")
        return

    df_raw = pd.read_csv(input_path, encoding='utf-8-sig')
    
    # 1-1. 결측치 제거 (좌표 없는 데이터 제외)
    df = df_raw.dropna(subset=['latitude', 'longitude'])
    
    # 1-2. 중복 제거
    subset_cols = ['latitude', 'longitude']
    if 'name' in df.columns:
        subset_cols.append('name') 
    df = df.drop_duplicates(subset=subset_cols)

    # 1-3. 지역 필터링 (제주 본섬 한정 - 추자도/마라도 등 너무 먼 곳 제외)
    JEJU_LAT_MIN, JEJU_LAT_MAX = 33.15, 33.60
    JEJU_LON_MIN, JEJU_LON_MAX = 126.10, 127.00
    df = df[
        (df['latitude'] >= JEJU_LAT_MIN) & (df['latitude'] <= JEJU_LAT_MAX) &
        (df['longitude'] >= JEJU_LON_MIN) & (df['longitude'] <= JEJU_LON_MAX)
    ]
    
    # 인덱스 초기화
    df = df.reset_index(drop=True)
    print(f"✅ 유효 분석 데이터: {len(df)}개")

    if len(df) < TRAVEL_DAYS:
        print("❌ 데이터가 너무 적어 군집화를 진행할 수 없습니다.")
        return

    # -----------------------------------------------------------
    # [Step 2] K-Means 군집화 (Weighted K-Means)
    # -----------------------------------------------------------
    print(f"🚀 [Step 2] K-Means 군집화 실행 (K={TRAVEL_DAYS}, 가중치={LATITUDE_WEIGHT})...")
    
    # 학습용 데이터 변형 (위도 가중치 적용)
    X = df[['latitude', 'longitude']].values.copy()
    X_scaled = X.copy()
    X_scaled[:, 0] = X_scaled[:, 0] * LATITUDE_WEIGHT 
    
    # 군집화 실행
    kmeans = KMeans(n_clusters=TRAVEL_DAYS, random_state=42, n_init=10)
    kmeans.fit(X_scaled)
    
    df['cluster'] = kmeans.labels_
    
    # 중심점 복구 (시각화를 위해 가중치 제거)
    centers_scaled = kmeans.cluster_centers_
    centers_original = centers_scaled.copy()
    centers_original[:, 0] = centers_original[:, 0] / LATITUDE_WEIGHT

    # -----------------------------------------------------------
    # [Step 3] 장소 선별 (Weighted Distance & Wide Range)
    # -----------------------------------------------------------
    actual_k = kmeans.n_clusters
    print(f"🚀 [Step 3] 구역별 추천 장소 선별 중... (Top {TOP_N})")
    
    final_candidates = pd.DataFrame()

    for i in range(actual_k):
        cluster_data = df[df['cluster'] == i].copy()
        
        # 가중치 적용된 좌표로 거리 계산 (AI의 의도 반영)
        cluster_scaled_coords = cluster_data[['latitude', 'longitude']].values.copy()
        cluster_scaled_coords[:, 0] = cluster_scaled_coords[:, 0] * LATITUDE_WEIGHT
        
        current_center_scaled = centers_scaled[i]
        
        # 중심점과의 거리 계산
        diff = cluster_scaled_coords - current_center_scaled
        dist_sq = np.sum(diff**2, axis=1)
        cluster_data['distance_from_center'] = dist_sq
        
        # [랜덤 샘플링] 너무 중심에만 몰리지 않게 구역 전체에서 랜덤 추출
        if len(cluster_data) < TOP_N:
             selected_places = cluster_data
        else:
             selected_places = cluster_data.sample(n=TOP_N) 

        final_candidates = pd.concat([final_candidates, selected_places])

    # 결과 CSV 저장
    final_candidates.to_csv(output_csv_path, index=False, encoding='utf-8-sig')

    # -----------------------------------------------------------
    # [Step 4] 지도 시각화 (Folium)
    # -----------------------------------------------------------
    print("🚀 [Step 4] 지도 시각화 생성 중...")

    # 지도의 중심 설정
    map_center = [df['latitude'].mean(), df['longitude'].mean()]
    m = folium.Map(location=map_center, zoom_start=10)

    # 1. 추천 장소 마커 찍기
    for idx, row in final_candidates.iterrows():
        cluster_id = int(row['cluster'])
        color = COLORS[cluster_id % len(COLORS)]
        place_name = row.get('name', '이름 없음')
        category = row.get('search_category', '기타')
        
        popup_html = f"""
        <div style="width:150px">
            <b>[{cluster_id+1}일차] {place_name}</b><br>
            <small>{category}</small>
        </div>
        """
        
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            popup=folium.Popup(popup_html, max_width=200),
            icon=folium.Icon(color=color, icon='star')
        ).add_to(m)

    # 2. 중심점(Centroid) 표시 (검은색 원)
    for i, center in enumerate(centers_original):
        folium.CircleMarker(
            location=center,
            radius=20,
            color='black',
            fill=True,
            fill_color=COLORS[i % len(COLORS)],
            fill_opacity=0.4,
            popup=f"<b>Day {i+1} 중심 구역</b>"
        ).add_to(m)

    # 지도 파일 저장
    m.save(output_map_path)
    
    print("=" * 50)
    print(f"✅ 모든 분석 완료!")
    print(f"📄 결과 데이터: {output_csv_path}")
    print(f"🗺️  결과 지도:   {output_map_path}")
    print("=" * 50)

if __name__ == "__main__":
    main()