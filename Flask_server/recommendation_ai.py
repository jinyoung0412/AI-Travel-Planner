import pandas as pd
from geopy.distance import geodesic

def calculate_score(v, b):
    return v + (b * 0.3)

def calculate_eff_dist(d_real, transport):
    if transport == '대중교통/도보':
        if d_real > 10.0:
            return d_real * 3.0
        return d_real * 1.0
    elif transport == '승용차':
        return d_real * 0.5
    return d_real * 1.0

def get_best_route(df, transport, region="충남 전체"):
    print(f"\n--- [{region}] 경로 추천 연산 시작 ---") #지역별로 경로 추천함
    
    df['S'] = df.apply(lambda row: calculate_score(row['방문자수'], row['블로그수']), axis=1)

    if 'Cluster' in df.columns and len(df['Cluster'].unique()) > 1:
        cluster_counts = df['Cluster'].value_counts()
        valid_clusters = cluster_counts[cluster_counts >= 3].index
        
        if len(valid_clusters) > 0:
            valid_df = df[df['Cluster'].isin(valid_clusters)]
            cluster_scores = valid_df.groupby('Cluster')['S'].mean()
            best_cluster = cluster_scores.idxmax()
            best_df = df[df['Cluster'] == best_cluster].copy()
            print(f"[추천 모듈] 선택된 최적 군집: {best_cluster}번 (장소 {len(best_df)}개)")
        else:
            best_df = df.copy()
            print("[추천 모듈] 모든 군집의 장소가 3개 미만이므로 전체 데이터를 사용합니다.")
    else:
        best_df = df.copy()

    start_point = (best_df['latitude'].mean(), best_df['longitude'].mean())
    print(f"[추천 모듈] 탐색 시작 기준점 (동적 계산): {start_point}")

    best_df['Dist'] = best_df.apply(lambda row: calculate_eff_dist(geodesic(start_point, (row['latitude'], row['longitude'])).kilometers, transport), axis=1)
    
    best_df['R'] = best_df['S'] / (best_df['Dist'] + 1)
    
    top_places = best_df.nlargest(3, 'R')
    
    print("\n[추천 모듈] 상위 3개 장소 선정 결과 (순위 로그):")
    for idx, row in top_places.iterrows():
        print(f"- {row['가게명']} | 방문자:{row['방문자수']}, 블로그:{row['블로그수']} | 기본점수:{row['S']:.1f} | 거리:{row['Dist']:.1f}km | 최종점수:{row['R']:.1f}")
    
    final_route = []
    current_loc = start_point
    unvisited = top_places.to_dict('records')

    while unvisited:
        next_place = min(unvisited, key=lambda x: geodesic(current_loc, (x['latitude'], x['longitude'])).kilometers)
        final_route.append(next_place)
        unvisited.remove(next_place)
        current_loc = (next_place['latitude'], next_place['longitude']) 

    return final_route

if __name__ == "__main__":
    import os
    from clustering_ai import perform_clustering
    
    if os.path.exists('chungnam_places_filtered.csv'):
        sample_df = pd.read_csv('chungnam_places_filtered.csv')
        clustered_df = perform_clustering(sample_df, transport='대중교통/도보')
        get_best_route(clustered_df, transport='대중교통/도보') 