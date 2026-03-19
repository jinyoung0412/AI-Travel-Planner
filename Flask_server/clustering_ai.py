import pandas as pd
from sklearn.cluster import KMeans
import warnings

warnings.filterwarnings("ignore", category=UserWarning)

def perform_clustering(df, num_clusters=2):
    print(f"[군집화 모듈] 데이터 {len(df)}개 대상, {num_clusters}개 군집 생성 시작")
    
    if len(df) < num_clusters:
        print(f"[군집화 모듈] 데이터 수가 군집 수({num_clusters})보다 적어 군집 수를 {len(df)}로 조정합니다.")
        num_clusters = len(df)
        
    if num_clusters == 0:
        return df
            
    coords = df[['latitude', 'longitude']].values
    
    kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
    
    result_df = df.copy() 
    result_df['Cluster'] = kmeans.fit_predict(coords)
    
    print("[군집화 모듈] 군집화 연산 완료")
    
    return result_df

if __name__ == "__main__":
    import os
    
    print("="*50)
    print("군집화 로직 단독 테스트 환경")
    print("="*50)
    
    if os.path.exists('chungnam_places_filtered.csv'):
        sample_df = pd.read_csv('chungnam_places_filtered.csv')
        print(f"chungnam_places_filtered.csv 로드 완료 (총 {len(sample_df)}개 장소)")
        
        clustered_df = perform_clustering(sample_df, num_clusters=3)
        print(f"\n군집화 결과 샘플:\n{clustered_df[['가게명', 'latitude', 'longitude', 'Cluster']].head(10)}")
    else:
        print("chungnam_places_filtered.csv 파일이 없습니다. 경로를 확인해주세요.")