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

def get_best_start_hub(cluster_center, region):
    transit_hubs = {
        '천안': [
            {'name': '천안역', 'lat': 36.8066, 'lon': 127.1469},
            {'name': '천안아산역', 'lat': 36.7944, 'lon': 127.1044},
            {'name': '천안종합터미널', 'lat': 36.8198, 'lon': 127.1566},
            {'name': '두정역', 'lat': 36.8336, 'lon': 127.1489},
            {'name': '쌍욕역', 'lat': 36.7936, 'lon': 127.1215},
        ],
        '아산': [
            {'name': '온양온천역', 'lat': 36.7805, 'lon': 127.0032},
            {'name': '아산시외버스터미널', 'lat': 36.7842, 'lon': 127.0156},
            {'name': '배방역', 'lat': 36.7776, 'lon': 127.0529},
            {'name': '탕정역', 'lat': 36.7885, 'lon': 127.0847},
            {'name': '신창역', 'lat': 36.7696, 'lon': 126.9515}
        ]
    }
    
    available_hubs = []
    if '천안' in region:
        available_hubs.extend(transit_hubs['천안'])
    if '아산' in region:
        available_hubs.extend(transit_hubs['아산'])
        
    if not available_hubs:
        return cluster_center, "군집 중심"
        
    closest_hub = min(available_hubs, key=lambda hub: geodesic(cluster_center, (hub['lat'], hub['lon'])).kilometers)
    return (closest_hub['lat'], closest_hub['lon']), closest_hub['name']

def get_best_route(df, transport, region="천안/아산"):
    df['S'] = df.apply(lambda row: calculate_score(row['방문자수'], row['블로그수']), axis=1)

    if 'Cluster' in df.columns and len(df['Cluster'].unique()) > 1:
        cluster_counts = df['Cluster'].value_counts()
        valid_clusters = cluster_counts[cluster_counts >= 3].index
        
        if len(valid_clusters) > 0:
            valid_df = df[df['Cluster'].isin(valid_clusters)]
            cluster_scores = valid_df.groupby('Cluster')['S'].mean()
            best_cluster = cluster_scores.idxmax()
            best_df = df[df['Cluster'] == best_cluster].copy()
        else:
            best_df = df.copy()
    else:
        best_df = df.copy()

    cluster_center = (best_df['latitude'].mean(), best_df['longitude'].mean())
    
    start_name = None
    if transport == '대중교통/도보':
        start_point, start_name = get_best_start_hub(cluster_center, region)
    else:
        start_point = cluster_center

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

    return final_route, start_point, start_name