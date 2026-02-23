import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from geopy.distance import geodesic

# ==========================================
# 1. 초기 설정 및 수식 함수 정의 (계획서 기반)
# ==========================================

# 평점 계산 공식: S = V + (B * 0.3)
def calculate_score(v_reviews, b_reviews):
    return v_reviews + (b_reviews * 0.3)

# 유효 거리 계산 공식: D_eff = D_real * W
def calculate_effective_distance(d_real, transport_type):
    # 접근성 가중치 (W)
    weight_map = {
        '대중교통_역세권': 0.7,
        '대중교통_일반': 1.0,
        '자가용': 0.5
    }
    w = weight_map.get(transport_type, 1.0)
    return d_real * w

# 랭킹 점수 계산 공식: R = S / D_eff
def calculate_ranking(score, d_eff):
    # 거리가 0일 경우(자기 자신) 0으로 나누는 에러 방지
    if d_eff == 0:
        d_eff = 0.1 
    return score / d_eff


# ==========================================
# 2. 메인 알고리즘 파이프라인
# ==========================================

def run_recommendation_algorithm():
    # 1. 가짜 데이터 로드
    df = pd.read_csv('dummy_data.csv')
    print("✅ [1단계] 데이터 로드 완료 (총 장소: {}개)".format(len(df)))

    # 2. 평점(S) 일괄 계산 및 컬럼 추가
    df['S'] = df.apply(lambda row: calculate_score(row['V'], row['B']), axis=1)

    # 3. 사용자 맞춤형 필터링 (예: '힐링', '맛집' 테마 선택)
    selected_themes = ['힐링', '맛집']
    filtered_df = df[df['Theme'].isin(selected_themes)].copy()
    print(f"\n✅ [2단계] '{selected_themes}' 테마 필터링 완료 (남은 장소: {len(filtered_df)}개)")
    print(filtered_df[['Name', 'Theme', 'S']])

    # 4. K-Means 군집화 (활동 지역 기준)
    # 1박 2일 일정이라고 가정하고 군집(K)을 2개로 설정
    num_clusters = 2 
    coords = filtered_df[['Lat', 'Lng']].values
    
    kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
    filtered_df['Cluster'] = kmeans.fit_predict(coords)
    
    print(f"\n✅ [3단계] 지리적 좌표 기반 군집화 완료 (K={num_clusters})")

    # 5. 추천 기준점 설정 (예: 시작점을 '천안아산역' KTX 근처로 임의 지정)
    start_point = (36.7944, 127.1044) # 천안아산역 위경도
    transport = '대중교통_일반' # 사용자 입력 이동수단 가중치

    # 6. 유효거리(D_eff) 및 랭킹점수(R) 계산
    rankings = []
    
    for index, row in filtered_df.iterrows():
        target_point = (row['Lat'], row['Lng'])
        
        # geopy를 사용해 실제 직선거리(D_real) 도출 (km 단위)
        d_real = geodesic(start_point, target_point).kilometers
        
        # 유효 거리(D_eff) 계산
        d_eff = calculate_effective_distance(d_real, transport)
        
        # 랭킹 점수(R) 계산
        r_score = calculate_ranking(row['S'], d_eff)
        
        rankings.append({
            'Name': row['Name'],
            'Theme': row['Theme'],
            'Cluster': row['Cluster'],
            'S (평점)': round(row['S'], 1),
            'D_real (실제거리km)': round(d_real, 2),
            'D_eff (유효거리km)': round(d_eff, 2),
            'R (랭킹점수)': round(r_score, 2)
        })

    result_df = pd.DataFrame(rankings)
    
    # 랭킹 점수(R)가 높은 순서대로 내림차순 정렬
    final_course = result_df.sort_values(by='R (랭킹점수)', ascending=False)
    
    print("\n✅ [4단계] 랭킹 점수 산정 및 최종 코스 추천 결과")
    print(final_course.to_string(index=False))

if __name__ == '__main__':
    run_recommendation_algorithm()