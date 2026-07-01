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

def perform_clustering(df, transport='대중교통'):
    """
    반경 내 후보 장소들을 지리적으로 군집화하여 'Cluster' 컬럼을 추가한다.

    코스 추천의 핵심 전제 — "한 코스 안의 장소들은 지리적으로 가까워야 한다" —
    를 충족시키기 위한 사전 단계. 군집화된 결과를 받은 코스 생성 단계에서는
    동일 군집 내 장소들만으로 한 코스를 구성한다.

    이동 수단에 따라 탐색 범위(max_k)를 차등 적용:
    - 대중교통: 더 작은 max_k → 군집을 더 좁게 → 코스 내 이동 거리 단축
    - 승용차: 더 넓은 max_k → 군집을 더 넓게 → 다양한 장소 조합 가능

    데이터가 5개 미만이면 의미 있는 군집화가 불가능하므로 생략하고 원본 반환.
    """
    total_places = len(df)

    if total_places < 5:
        print("[군집화 모듈] 데이터가 5개 미만이므로 군집화를 생략합니다.")
        return df

    # 탐색할 최대 군집 수: 데이터 수의 제곱근 (경험적 상한선)
    # 대중교통은 //3으로 더 좁게 제한 → 한 군집의 지리적 범위가 도보 이동 가능 수준으로 축소
    if transport == '대중교통':
        max_k = max(2, int(total_places ** 0.5) // 3)
    else:
        max_k = max(2, int(total_places ** 0.5))

    # 코스 구성 가능성 보장 (군집당 최소 장소 확보) + 절대 상한선 15
    max_k = min(max_k, total_places - 1, 15)

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
        clustered_df = perform_clustering(sample_df, transport='대중교통')
