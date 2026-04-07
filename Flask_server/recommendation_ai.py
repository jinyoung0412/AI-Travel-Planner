import pandas as pd
from geopy.distance import geodesic

# ============================================================
# [점수 계산 수식]
#
# 1. Min-Max 정규화
#    normalized = (x - min) / (max - min)
#    → 방문자수, 블로그수를 각각 0~1 범위로 정규화
#    → 두 변수의 스케일 차이(방문자수 최대 ~55,000 vs 블로그수 최대 ~14,000)를
#      제거하여 가중치가 실질적으로 작동하게 만든다.
#
# 2. 인기 점수 S (Popularity Score)
#    S = 0.7 × norm_visitors + 0.3 × norm_blogs
#    → 방문자수에 70%, 블로그 리뷰수에 30% 가중치 부여
#    → 두 값 모두 정규화된 0~1 범위이므로 가중치가 의미를 가짐
#    → S 범위: 0~1
#
# 3. 유효 거리 D_eff (Effective Distance)
#    대중교통/도보: D_eff = norm_dist + 0.5 × penalty
#                  penalty = 1 if 실제거리 > 10km else 0
#    승용차:        D_eff = norm_dist × 0.5
#    → 실제 거리를 정규화(0~1)한 뒤 패널티 적용
#    → 대중교통은 10km 초과 시 0.5 추가 패널티 (정규화 범위 내에서 의미있는 값)
#    → 승용차는 이동 편의성을 반영해 거리 영향을 절반으로 감소
#    → D_eff 범위: 0~1 (대중교통 패널티 포함 시 최대 1.5)
#
# 4. 최종 랭킹 점수 R (Ranking Score)
#    R = S / (D_eff + 0.1)
#    → 인기 점수를 유효 거리로 나눠 가깝고 인기있는 장소를 우선 추천
#    → +0.1은 D_eff가 0에 가까울 때 R이 무한대로 발산하는 것을 방지
#    → S와 D_eff 모두 정규화되어 있으므로 두 요소가 균형있게 반영됨
# ============================================================

def minmax_normalize(series):
    min_val = series.min()
    max_val = series.max()
    if max_val == min_val:
        return series * 0  # 모든 값이 동일하면 0으로 처리
    return (series - min_val) / (max_val - min_val)

def calculate_score(norm_visitors, norm_blogs):
    # S = 0.7 × 정규화된_방문자수 + 0.3 × 정규화된_블로그수
    return 0.7 * norm_visitors + 0.3 * norm_blogs

def calculate_eff_dist(norm_dist, d_real, transport):
    if transport == '대중교통/도보':
        # 10km 초과 시 0.5 추가 패널티 (정규화된 거리 기준에서 의미있는 값)
        penalty = 0.5 if d_real > 10.0 else 0.0
        return norm_dist + penalty
    elif transport == '승용차':
        # 승용차는 이동 편의성 반영해 거리 영향 절반으로 감소
        return norm_dist * 0.5
    return norm_dist

def get_best_start_hub(cluster_center, region):
    transit_hubs = {
        '천안': [
            {'name': '천안역', 'lat': 36.8066, 'lon': 127.1469},
            {'name': '천안아산역', 'lat': 36.7944, 'lon': 127.1044},
            {'name': '천안종합터미널', 'lat': 36.8198, 'lon': 127.1566},
            {'name': '두정역', 'lat': 36.8336, 'lon': 127.1489},
            {'name': '쌍용역', 'lat': 36.7936, 'lon': 127.1215},
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

def get_best_route(df_input, transport, region="천안/아산"):
    df = df_input.copy()

    print(f"\n--- [{region}] 경로 추천 연산 시작 ---")

    # 방문자수, 블로그수 각각 Min-Max 정규화 (0~1)
    df['norm_visitors'] = minmax_normalize(df['방문자수'])
    df['norm_blogs'] = minmax_normalize(df['블로그수'])

    # 인기 점수 S 계산 (정규화된 값 기반)
    df['S'] = df.apply(lambda row: calculate_score(row['norm_visitors'], row['norm_blogs']), axis=1)

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

    cluster_center = (best_df['latitude'].mean(), best_df['longitude'].mean())

    start_name = None
    if transport == '대중교통/도보':
        start_point, start_name = get_best_start_hub(cluster_center, region)
        print(f"[추천 모듈] 대중교통 탐색 시작 기준점: {start_name} {start_point}")
    else:
        start_point = cluster_center
        print(f"[추천 모듈] 자가용 탐색 시작 기준점(군집 중심): {start_point}")

    # 실제 거리 계산 후 정규화
    best_df['d_real'] = best_df.apply(
        lambda row: geodesic(start_point, (row['latitude'], row['longitude'])).kilometers, axis=1
    )
    best_df['norm_dist'] = minmax_normalize(best_df['d_real'])

    # 유효 거리 D_eff 계산 (정규화된 거리 + 이동수단 패널티)
    best_df['D_eff'] = best_df.apply(
        lambda row: calculate_eff_dist(row['norm_dist'], row['d_real'], transport), axis=1
    )

    # 최종 랭킹 점수 R 계산
    # R = S / (D_eff + 0.1) — 0.1은 D_eff=0일 때 발산 방지
    best_df['R'] = best_df['S'] / (best_df['D_eff'] + 0.1)

    top_places = best_df.nlargest(3, 'R')

    print("\n[추천 모듈] 상위 3개 장소 선정 결과 (순위 로그):")
    for idx, row in top_places.iterrows():
        print(f"- {row['가게명']} | 방문자:{row['방문자수']}, 블로그:{row['블로그수']} | 인기점수(S):{row['S']:.3f} | 실제거리:{row['d_real']:.1f}km | 유효거리(D_eff):{row['D_eff']:.3f} | 최종점수(R):{row['R']:.3f}")

    final_route = []
    current_loc = start_point
    unvisited = top_places.to_dict('records')

    while unvisited:
        next_place = min(unvisited, key=lambda x: geodesic(current_loc, (x['latitude'], x['longitude'])).kilometers)
        final_route.append(next_place)
        unvisited.remove(next_place)
        current_loc = (next_place['latitude'], next_place['longitude'])

    return final_route, start_point, start_name
