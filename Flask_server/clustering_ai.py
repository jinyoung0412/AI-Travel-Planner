import pandas as pd
from sklearn.cluster import KMeans
import warnings

# sklearn의 메모리 누수 관련 불필요한 경고 숨김
warnings.filterwarnings("ignore", category=UserWarning)

def perform_clustering(df, num_clusters=2):
    """
    Flask 서버에서 실시간으로 호출하는 군집화 핵심 함수.
    DataFrame을 입력받아 'Cluster' 컬럼을 추가하여 반환합니다.
    """
    print(f"🤖 [군집화 모듈] 데이터 {len(df)}개 대상, {num_clusters}개 군집 생성 시작")
    
    # 예외 처리: 필터링된 장소 개수가 목표 군집 수보다 적을 경우
    if len(df) < num_clusters:
        print(f"⚠️ [군집화 모듈] 데이터 수가 군집 수({num_clusters})보다 적어 군집 수를 {len(df)}로 조정합니다.")
        num_clusters = len(df)
        
    # 데이터가 0개면 그대로 반환
    if num_clusters == 0:
        return df
            
    # 순수 위도(Lat)와 경도(Lng)만 추출하여 K-Means 학습 데이터로 사용
    coords = df[['Lat', 'Lng']].values
    
    # K-Means 알고리즘 초기화 및 실행
    # n_init=10: 초기 중심점 설정을 10번 반복하여 최적의 결과를 찾음
    kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
    
    # 원본 데이터 훼손(SettingWithCopyWarning) 방지를 위해 명시적 복사본 생성
    result_df = df.copy() 
    result_df['Cluster'] = kmeans.fit_predict(coords)
    
    print("✅ [군집화 모듈] 군집화 연산 완료")
    
    return result_df

# ==========================================
# 팀원 로컬 디버깅 및 알고리즘 고도화용 테스트 영역
# ==========================================
if __name__ == "__main__":
    # 이 부분은 Flask 서버 통신 시에는 실행되지 않으며,
    # 팀원이 이 파일만 단독으로 실행(python clustering_ai.py)할 때만 작동합니다.
    import os
    
    print("="*50)
    print("🧪 군집화 로직 단독 테스트 환경")
    print("="*50)
    
    if os.path.exists('dummy_data.csv'):
        # 1. 가짜 데이터 로드
        sample_df = pd.read_csv('dummy_data.csv')
        print(f"📄 dummy_data.csv 로드 완료 (총 {len(sample_df)}행)")
        
        # 2. 군집화 모듈 실행
        clustered_df = perform_clustering(sample_df, num_clusters=2)
        
        # 3. 콘솔에 결과 출력
        print("\n📊 [클러스터링 결과 요약]")
        for cluster_id in sorted(clustered_df['Cluster'].unique()):
            cluster_data = clustered_df[clustered_df['Cluster'] == cluster_id]
            places = cluster_data['Name'].tolist()
            print(f"  - Cluster {cluster_id} ({len(places)}곳): {', '.join(places)}")
            
        print("="*50)
    else:
        print("❌ 에러: 현재 폴더에 테스트용 dummy_data.csv 파일이 없습니다.")