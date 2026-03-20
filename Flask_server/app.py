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
        print(f"[Flask] 수신 데이터: {data}")
        
        themes = data.get('themes', [])
        transport = data.get('transport', '대중교통/도보')
        duration = data.get('duration', '당일치기')
        
        file_path = r'C:\AI-Travel-Planner\Preprocess\data\processed\chungnam_places_filtered.csv'
        
        if not os.path.exists(file_path):
            return jsonify({"error": "데이터 파일이 서버에 없습니다."}), 500
            
        df = pd.read_csv(file_path)
        df = df[df['주소'].str.contains('천안|아산', na=False)]
        
        region_target = '천안/아산'
        if duration == '당일치기' and transport == '대중교통/도보':
            asan_df = df[df['주소'].str.contains('아산', na=False)]
            if len(asan_df) >= 3:
                df = asan_df
                region_target = '아산'
        
        if themes:
            theme_filtered = df[df['search_category'].isin(themes)]
            if len(theme_filtered) >= 3:
                df = theme_filtered
            
        if df.empty or len(df) < 3:
            df = pd.read_csv(file_path)
            df = df[df['주소'].str.contains('천안|아산', na=False)]
            reason_text = "조건에 맞는 장소가 부족하여 천안/아산 전체 데이터를 기반으로 한 맞춤 코스입니다."
        else:
            themes_str = ', '.join(themes)
            reason_text = f"선택하신 '{themes_str}' 테마와 '{transport}' 접근성을 고려한 최적화 코스입니다."

        clustered_df = perform_clustering(df, transport=transport)
        
        final_route, start_point, start_name = get_best_route(clustered_df, transport=transport, region=region_target)
        
        course_data = []
        for place in final_route:
            course_data.append({
                "name": place['가게명'],
                "lat": place['latitude'],
                "lng": place['longitude'],
                "address": place['주소'],
                "category": place['search_category']
            })
            
        start_hub_data = None
        if start_name:
            start_hub_data = {
                "name": start_name,
                "lat": start_point[0],
                "lng": start_point[1]
            }
        
        response_data = {
            "reason": reason_text,
            "start_hub": start_hub_data,
            "recommended_course": course_data,
            "total_time": f"약 {len(course_data) * 3}시간"
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"[Flask] 에러 발생: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)