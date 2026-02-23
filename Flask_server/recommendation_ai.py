import pandas as pd
from geopy.distance import geodesic

def calculate_score(v, b):
    return v + (b * 0.3)

def calculate_eff_dist(d_real, transport):
    # 비선형 가중치 (프로토타입용)
    if transport == '대중교통/도보':
        if d_real > 10.0:
            return d_real * 3.0  # 10km 넘으면 패널티 3배
        return d_real * 1.0
    elif transport == '승용차':
        return d_real * 0.5
    return d_real * 1.0

def get_best_route(df, transport):
    # 1. 여행지 평점(S) 일괄 계산
    df['S'] = df.apply(lambda row: calculate_score(row['V'], row['B']), axis=1)

    # =================================================================
    # [수정됨] 프로토타입에서는 데이터가 적으므로 군집 필터링을 건너뜁니다.
    # 2. 우수 군집 선택 로직 -> 잠시 비활성화 (전체 데이터 경쟁)
    # =================================================================
    # cluster_scores = df.groupby('Cluster')['S'].mean()
    # best_cluster = cluster_scores.idxmax()
    # best_df = df[df['Cluster'] == best_cluster].copy()
    
    best_df = df.copy() # 모든 데이터를 후보로 사용
    # =================================================================

    # 3. 기준점(천안아산역) 설정
    start_point = (36.7944, 127.1044) 
    rankings = []
    
    # 4. 평점과 유효거리를 활용하여 랭킹 점수(R) 부여
    for _, row in best_df.iterrows():
        d_real = geodesic(start_point, (row['Lat'], row['Lng'])).kilometers
        d_eff = calculate_eff_dist(d_real, transport)
        safe_d_eff = d_eff if d_eff > 0 else 0.1 
        
        r_score = row['S'] / safe_d_eff
        
        # 디버깅용 로그 출력 (Flask 콘솔에서 확인 가능)
        print(f"🚩 [{transport}] {row['Name']} -> 거리:{d_real:.1f}km, 점수:{r_score:.1f}")

        row_dict = row.to_dict()
        row_dict['R'] = r_score
        rankings.append(row_dict)
    
    # 5. 상위 3개 선정
    top_places = pd.DataFrame(rankings).sort_values(by='R', ascending=False).head(3)
    
    # 6. TSP 동선 최적화
    final_route = []
    current_loc = start_point
    unvisited = top_places.to_dict('records')

    while unvisited:
        next_place = min(unvisited, key=lambda x: geodesic(current_loc, (x['Lat'], x['Lng'])).kilometers)
        final_route.append(next_place)
        unvisited.remove(next_place)
        current_loc = (next_place['Lat'], next_place['Lng']) 

    return final_route


# ==========================================
# 알고리즘 단독 테스트 영역
# ==========================================
if __name__ == "__main__":
    import os
    from clustering_ai import perform_clustering
    
    print("="*50)
    print("🧠 추천 로직 단독 테스트 (프로토타입용)")
    print("="*50)
    
    if os.path.exists('dummy_data.csv'):
        sample_df = pd.read_csv('dummy_data.csv')
        clustered_df = perform_clustering(sample_df, num_clusters=2)
        
        print("\n🚌 [대중교통/도보] 최종 추천 동선:")
        route_public = get_best_route(clustered_df, transport='대중교통/도보')
        for i, place in enumerate(route_public, 1):
            print(f"{i}번: {place['Name']} (S:{place['S']:.1f}, R:{place['R']:.1f})")

        print("\n🚗 [승용차] 최종 추천 동선:")
        route_car = get_best_route(clustered_df, transport='승용차')
        for i, place in enumerate(route_car, 1):
            print(f"{i}번: {place['Name']} (S:{place['S']:.1f}, R:{place['R']:.1f})")
    else:
        print("테스트를 위한 dummy_data.csv 파일이 없습니다.")