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
#
# 5. 최적 군집 선택 기준
#    → 각 군집마다 해당 군집 중심에서 가장 가까운 교통 거점을 기준으로
#      군집 내 모든 장소의 R을 계산한 뒤, 군집 평균 R이 가장 높은 군집 선택
#    → 기존에는 인기도(S)만으로 군집을 선택했기 때문에,
#      교통 거점에서 멀리 떨어진 군집이 선택되는 문제가 있었음
#    → 평균 R 기준으로 선택하면 인기도와 접근성을 동시에 고려하게 됨
#
# 6. 거리 정규화 기준
#    → 군집 내부 기준이 아닌 전체 유효 군집의 거리를 합산하여 전역 정규화 수행
#    → 기존에는 군집별로 거리를 독립적으로 정규화했기 때문에,
#      실제로 멀리 있는 군집도 내부적으로 0~1로 정규화되어
#      절대 거리가 무시되는 문제가 있었음
#    → 전역 정규화를 통해 멀리 있는 장소는 실제로 높은 norm_dist를 가지게 됨
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

def compute_r_for_cluster(cluster_df, start_point, transport, global_min_dist=None, global_max_dist=None):
    """
    주어진 군집 내 장소들의 R 점수를 계산하여 반환.
    거리 정규화는 전역 기준(global_min_dist, global_max_dist)으로 수행.
    → 군집별 독립 정규화 시 절대 거리가 무시되는 문제를 해결.
    전역 기준값이 없으면 군집 내부 기준으로 fallback.
    """
    df = cluster_df.copy()
    df['d_real'] = df.apply(
        lambda row: geodesic(start_point, (row['latitude'], row['longitude'])).kilometers, axis=1
    )

    if global_min_dist is not None and global_max_dist is not None and global_max_dist > global_min_dist:
        # 전역 기준 정규화: 절대 거리가 반영됨
        df['norm_dist'] = (df['d_real'] - global_min_dist) / (global_max_dist - global_min_dist)
    else:
        # fallback: 군집 내부 기준 정규화
        df['norm_dist'] = minmax_normalize(df['d_real'])

    df['D_eff'] = df.apply(lambda row: calculate_eff_dist(row['norm_dist'], row['d_real'], transport), axis=1)
    df['R'] = df['S'] / (df['D_eff'] + 0.1)
    return df

def get_best_route(df_input, transport, region="천안/아산"):
    df = df_input.copy()

    print(f"\n--- [{region}] 경로 추천 연산 시작 ---")

    # 방문자수, 블로그수 각각 Min-Max 정규화 (0~1) — 전체 데이터 기준
    df['norm_visitors'] = minmax_normalize(df['방문자수'])
    df['norm_blogs'] = minmax_normalize(df['블로그수'])

    # 인기 점수 S 계산 (정규화된 값 기반)
    df['S'] = df.apply(lambda row: calculate_score(row['norm_visitors'], row['norm_blogs']), axis=1)

    global_min_dist = None
    global_max_dist = None

    if 'Cluster' in df.columns and len(df['Cluster'].unique()) > 1:
        cluster_counts = df['Cluster'].value_counts()
        valid_clusters = cluster_counts[cluster_counts >= 3].index

        if len(valid_clusters) > 0:
            # 군집별로 교통 거점을 기준으로 R을 계산하여 최적 군집 선택
            # → 인기도(S)만 보던 기존 방식에서, 접근성까지 반영한 평균 R 기준으로 변경

            # 전역 거리 정규화 기준 계산
            # → 모든 유효 군집의 장소-거점 간 거리를 수집하여 전역 min/max 산출
            # → 이를 통해 군집 간 절대 거리 비교가 가능해짐
            all_distances = []
            cluster_start_points = {}
            for cluster_id in valid_clusters:
                c_df = df[df['Cluster'] == cluster_id]
                c_center = (c_df['latitude'].mean(), c_df['longitude'].mean())
                if transport == '대중교통/도보':
                    c_start_point, _ = get_best_start_hub(c_center, region)
                else:
                    c_start_point = c_center
                cluster_start_points[cluster_id] = c_start_point
                distances = c_df.apply(
                    lambda row: geodesic(c_start_point, (row['latitude'], row['longitude'])).kilometers, axis=1
                )
                all_distances.extend(distances.tolist())

            global_min_dist = min(all_distances)
            global_max_dist = max(all_distances)

            cluster_r_scores = {}
            for cluster_id in valid_clusters:
                c_df = df[df['Cluster'] == cluster_id]
                c_start_point = cluster_start_points[cluster_id]
                c_df_with_r = compute_r_for_cluster(c_df, c_start_point, transport, global_min_dist, global_max_dist)
                cluster_r_scores[cluster_id] = c_df_with_r['R'].mean()

            best_cluster = max(cluster_r_scores, key=cluster_r_scores.get)
            best_df = df[df['Cluster'] == best_cluster].copy()
            print(f"[추천 모듈] 전역 거리 범위: {global_min_dist:.1f}km ~ {global_max_dist:.1f}km")
            print(f"[추천 모듈] 군집별 평균 R 점수: { {k: round(v, 3) for k, v in cluster_r_scores.items()} }")
            print(f"[추천 모듈] 선택된 최적 군집: {best_cluster}번 (장소 {len(best_df)}개)")
        else:
            best_df = df.copy()
            print("[추천 모듈] 모든 군집의 장소가 3개 미만이므로 전체 데이터를 사용합니다.")
    else:
        best_df = df.copy()

    # 최적 군집의 교통 거점 확정
    cluster_center = (best_df['latitude'].mean(), best_df['longitude'].mean())

    start_name = None
    if transport == '대중교통/도보':
        start_point, start_name = get_best_start_hub(cluster_center, region)
        print(f"[추천 모듈] 대중교통 탐색 시작 기준점: {start_name} {start_point}")
    else:
        start_point = cluster_center
        print(f"[추천 모듈] 자가용 탐색 시작 기준점(군집 중심): {start_point}")

    # 최적 군집 내 최종 R 계산 (전역 거리 기준 적용)
    global_min_dist = global_min_dist if 'global_min_dist' in dir() else None
    global_max_dist = global_max_dist if 'global_max_dist' in dir() else None
    best_df = compute_r_for_cluster(best_df, start_point, transport, global_min_dist, global_max_dist)

    top_places = best_df.nlargest(3, 'R')

    print("\n[추천 모듈] 상위 3개 장소 선정 결과 (순위 로그):")
    for _, row in top_places.iterrows():
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
