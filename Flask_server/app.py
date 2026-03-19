from flask import Flask, request, jsonify
import pandas as pd
import os

from clustering_ai import perform_clustering
from recommendation_ai import get_best_route

app = Flask(__name__)

@app.route('/ai-predict', methods=['POST'])
def ai_predict():
    try:
        data = request.get_json()
        print(f"\n[Flask] Node.js에서 받은 데이터: {data}")
        
        themes = data.get('themes', [])
        region = data.get('region', '충남 전체')
        transport = data.get('transport', '대중교통/도보')
        
        file_path = r'C:\AI-Travel-Planner\Preprocess\data\processed\chungnam_places_filtered.csv'
        
        if not os.path.exists(file_path):
            return jsonify({"error": "chungnam_places_filtered.csv 파일이 서버에 없습니다."}), 500
            
        df = pd.read_csv(file_path)
        
        if region != '충남 전체':
            region_filtered = df[df['주소'].str.contains(region, na=False)]
            if len(region_filtered) >= 3:
                df = region_filtered
            else:
                print(f"[Flask] '{region}' 지역 데이터가 부족하여 전체 지역으로 탐색합니다..")
        
        if themes:
            theme_filtered = df[df['search_category'].isin(themes)]
            if len(theme_filtered) >= 3:
                df = theme_filtered
            else:
                print("[Flask] 테마 데이터가 부족하여 필터링을 무시합니다.")
            
        if df.empty or len(df) < 3:
            df = pd.read_csv(file_path)
            reason_text = f"조건에 맞는 장소가 부족하여 전체 데이터를 기반으로 분석한 '{region}' 맞춤 코스입니다."
        else:
            themes_str = ', '.join(themes)
            reason_text = f"선택하신 '{themes_str}' 테마와 '{transport}' 접근성을 고려한 '{region}' AI 최적화 코스입니다."

        clustered_df = perform_clustering(df, transport=transport)
        
        final_route = get_best_route(clustered_df, transport=transport, region=region)
        
        course_names = [place['가게명'] for place in final_route]
        
        response_data = {
            "reason": reason_text,
            "recommended_course": course_names,
            "total_time": f"약 {len(course_names) * 3}시간"
        }
        
        print(f"[Flask] AI 연산 완료 및 응답: {course_names}")
        
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"[Flask] 에러 발생: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)