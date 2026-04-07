import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import warnings

warnings.filterwarnings("ignore", category=UserWarning)

# ============================================================
# [최적 군집 수 결정 방식]
#
# Silhouette Score 기반 자동 결정
# → Silhouette Score: 각 데이터 포인트가 자신의 군집에 얼마나 잘 속하는지를
#   측정하는 지표. 범위는 -1 ~ 1이며 1에 가까울수록 군집이 잘 나뉜 것.
# → k를 2부터 max_k까지 순회하며 Silhouette Score가 가장 높은 k를 선택.
# → 기존에는 total_places // 10 (대중교통) / // 20 (승용차) 으로
#   임의 결정했으나, 데이터 분포와 무관한 하드코딩이라 군집 품질 보장 불가.
# → max_k는 데이터 수의 제곱근으로 설정 (일반적인 경험적 상한선)
# ============================================================

def find_optimal_clusters(coords, max_k):
    """
    Silhouette Score를 기준으로 최적 군집 수(k)를 탐색.
    k는 2부터 max_k까지 순회하며 점수가 가장 높은 k를 반환.
    """
    best_k = 2
    best_score = -1

    for k in range(2, max_k + 1):
        kmeans = KMeans(n_clusters=k, n_init=10)
        labels = kmeans.fit_predict(coords)
        score = silhouette_score(coords, labels)
        print(f"[군집화 모듈] k={k} → Silhouette Score: {score:.4f}")
        if score > best_score:
            best_score = score
            best_k = k

    print(f"[군집화 모듈] 최적 군집 수 선택: k={best_k} (Score: {best_score:.4f})")
    return best_k

def perform_clustering(df, transport='대중교통/도보'):
    total_places = len(df)

    if total_places < 5:
        print("[군집화 모듈] 데이터가 5개 미만이므로 군집화를 생략합니다.")
        return df

    # 탐색할 최대 군집 수: 데이터 수의 제곱근 (경험적 상한선)
    # 이동수단에 따라 탐색 범위를 조정 (승용차는 더 넓은 범위 허용)
    if transport == '대중교통/도보':
        max_k = max(2, int(total_places ** 0.5) // 2)
    else:
        max_k = max(2, int(total_places ** 0.5))

    # 군집 수가 데이터 수를 초과하지 않도록 제한
    max_k = min(max_k, total_places - 1)

    print(f"[군집화 모듈] 데이터 {total_places}개 대상, 이동수단 '{transport}' 고려하여 최적 군집 수 탐색 (최대 k={max_k})")

    coords = df[['latitude', 'longitude']].values

    optimal_k = find_optimal_clusters(coords, max_k)

    kmeans = KMeans(n_clusters=optimal_k, n_init=10)
    result_df = df.copy()
    result_df['Cluster'] = kmeans.fit_predict(coords)

    print(f"[군집화 모듈] 군집화 연산 완료 (최적 군집 수: {optimal_k}개)")

    return result_df

if __name__ == "__main__":
    import os

    print("="*50)
    print("군집화 로직 단독 테스트 환경")
    print("="*50)

    if os.path.exists('chungnam_places_filtered.csv'):
        sample_df = pd.read_csv('chungnam_places_filtered.csv')
        clustered_df = perform_clustering(sample_df, transport='대중교통/도보')
