from flask import Flask, request, jsonify
import pandas as pd
import os

# 1. 분리해둔 AI 모듈 임포트
from clustering_ai import perform_clustering
from recommendation_ai import get_best_route

app = Flask(__name__)

# Node.js에서 POST 요청으로 접근했을 때 실행됨
@app.route('/ai-predict', methods=['POST'])
def ai_predict():
    try:
        # 1. Node.js가 보낸 JSON 데이터 받기
        data = request.get_json()
        print(f"📦 [Flask] Node.js에서 받은 데이터: {data}")
        
        # 2. 데이터 추출 (기본값 설정)
        themes = data.get('themes', [])
        region = data.get('region', '충남 전체')
        transport = data.get('transport', '대중교통/도보') # '승용차' 또는 '대중교통/도보'
        
        # 3. 더미 데이터 로드
        if not os.path.exists('dummy_data.csv'):
            return jsonify({"error": "dummy_data.csv 파일이 서버에 없습니다."}), 500
            
        df = pd.read_csv('dummy_data.csv')
        
        # 4. 사용자 맞춤형 테마 필터링
        if themes:
            df = df[df['Theme'].isin(themes)]
            
        # 데이터 부족 시 예외 처리 (테마 필터링 후 장소가 너무 적으면 원본 복구)
        if df.empty or len(df) < 3:
            df = pd.read_csv('dummy_data.csv')
            reason_text = f"선택하신 조건에 맞는 장소가 부족하여 전체 데이터를 기반으로 분석한 '{region}' 맞춤 코스입니다."
        else:
            themes_str = ', '.join(themes)
            reason_text = f"선택하신 '{themes_str}' 테마와 '{transport}' 접근성을 고려한 '{region}' AI 최적화 코스입니다."

        # 5. AI 모듈 연동 (군집화 -> 경로 추천 및 TSP 정렬)
        # 군집화 모듈 실행 (목표 군집 수 2개)
        clustered_df = perform_clustering(df, num_clusters=2)
        
        # 추천 로직 모듈 실행 (최종 상위 3개 최단 동선 도출)
        final_route = get_best_route(clustered_df, transport=transport)
        
        # 6. Node.js로 돌려줄 응답 데이터 조립
        # final_route 안의 딕셔너리에서 'Name'만 뽑아서 리스트로 만듦
        course_names = [place['Name'] for place in final_route]
        
        response_data = {
            "reason": reason_text,
            "recommended_course": course_names,
            "total_time": f"약 {len(course_names) * 3}시간" # 장소당 임의로 3시간 배정
        }
        
        print(f"✅ [Flask] AI 연산 완료 및 응답: {course_names}")
        
        # 7. JSON 형태로 변환하여 정상(200) 응답
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"🔥 [Flask] 에러 발생: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Flask 서버 실행 (포트 5000)
    app.run(host='127.0.0.1', port=5000, debug=True)