import pandas as pd
from sklearn.cluster import KMeans
import warnings

warnings.filterwarnings("ignore", category=UserWarning)

def perform_clustering(df, transport='대중교통/도보'):
    total_places = len(df)
    
    if total_places < 5:
        print("[군집화모듈] 데이터가 5개 미만이므로 군집화를 생략합니다.")
        return df

    if transport == '대중교통/도보':
        num_clusters = max(2, total_places // 10)
    else:
        num_clusters = max(2, total_places // 20)

    print(f"[군집화 모듈] 데이터 {total_places}개 대상, 이동수단 '{transport}' 고려하여 {num_clusters}개 군집 생성 시작")
    
    coords = df[['latitude', 'longitude']].values
    
    kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
    
    result_df = df.copy() 
    result_df['Cluster'] = kmeans.fit_predict(coords)
    
    print(f"[군집화모듈] 군집화 연산 완료 (생성된 군집 수: {num_clusters}개)")
    
    return result_df

if __name__ == "__main__":
    import os
    
    print("="*50)
    print("군집화 로직 단독 테스트 환경")
    print("="*50)
    
    if os.path.exists('chungnam_places_filtered.csv'):
        sample_df = pd.read_csv('chungnam_places_filtered.csv')
        clustered_df = perform_clustering(sample_df, transport='대중교통/도보')