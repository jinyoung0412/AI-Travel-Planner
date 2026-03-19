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

def get_best_route(df, transport):
    df['S'] = df.apply(lambda row: calculate_score(row['방문자수'], row['블로그수']), axis=1)

    best_df = df

    start_point = (36.8151, 127.1139)

    best_df['Dist'] = best_df.apply(lambda row: calculate_eff_dist(geodesic(start_point, (row['latitude'], row['longitude'])).kilometers, transport), axis=1)
    
    best_df['R'] = best_df['S'] / (best_df['Dist'] + 1)
    
    top_places = best_df.nlargest(3, 'R')
    
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
    
    print("="*50)
    print("추천 로직 단독 테스트")
    print("="*50)
    
    if os.path.exists('chungnam_places_filtered.csv'):
        sample_df = pd.read_csv('chungnam_places_filtered.csv')
        clustered_df = perform_clustering(sample_df, num_clusters=2)
        
        print("\n[대중교통/도보] 최종 추천 동선:")
        route_public = get_best_route(clustered_df, transport='대중교통/도보')
        for i, place in enumerate(route_public):
            print(f"{i+1}번 방문지: {place['가게명']} (방문자: {place['방문자수']}, 블로그: {place['블로그수']})")
            
        print("\n[승용차] 최종 추천 동선:")
        route_car = get_best_route(clustered_df, transport='승용차')
        for i, place in enumerate(route_car):
            print(f"{i+1}번 방문지: {place['가게명']} (방문자: {place['방문자수']}, 블로그: {place['블로그수']})")