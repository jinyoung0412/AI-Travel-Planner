from flask import Flask, request, jsonify
import pandas as pd
import os

from clustering_ai import perform_clustering
from recommendation_ai import get_best_route

app = Flask(__name__)

@app.route('/ai-predict', methods=['POST'])
def ai_predict():
    try:
        print("\n" + "="*50)
        print("[V5 행정구역 엄격 필터링 버전] 요청 수신")
        print("="*50)
        
        data = request.get_json()
        print(f"[Flask] 프론트엔드 수신 데이터: {data}")
        
        themes = data.get('themes', [])
        region_req = str(data.get('region', '천안/아산')).strip()
        transport = data.get('transport', '대중교통/도보')
        
        file_path = r'C:\AI-Travel-Planner\Preprocess\data\processed\chungnam_places_filtered.csv'
        
        if not os.path.exists(file_path):
            return jsonify({"error": "데이터 파일이 서버에 없습니다."}), 500
            
        df = pd.read_csv(file_path)
        
        if '아산' in region_req:
            df = df[df['주소'].str.contains('아산시', na=False)]
            region_target = '아산'
        elif '천안' in region_req:
            df = df[df['주소'].str.contains('천안시', na=False)]
            region_target = '천안'
        else:
            df = df[df['주소'].str.contains('천안시|아산시', na=False)]
            region_target = '천안/아산'

        print(f"[Flask] 1차 지역 필터링 완료: {region_target} (남은 장소: {len(df)}개)")

        if themes:
            theme_filtered = df[df['search_category'].isin(themes)]
            if len(theme_filtered) >= 3:
                df = theme_filtered
                print(f"[Flask] 2차 테마 필터링 완료: {themes} (남은 장소: {len(df)}개)")
            else:
                print(f"[Flask] 2차 테마 필터링 무시: 조건에 맞는 장소가 3개 미만이라 {region_target} 전체에서 탐색합니다.")
        
        if df.empty or len(df) < 3:
            df = pd.read_csv(file_path)
            if '아산' in region_req:
                df = df[df['주소'].str.contains('아산시', na=False)]
            elif '천안' in region_req:
                df = df[df['주소'].str.contains('천안시', na=False)]
            else:
                df = df[df['주소'].str.contains('천안시|아산시', na=False)]
            
            themes_str = ', '.join(themes) if themes else '선택없음'
            reason_text = f"'{themes_str}' 테마의 장소가 부족하여, {region_target} 전체 핫플레이스를 기반으로 구성한 맞춤 코스입니다."
        else:
            themes_str = ', '.join(themes)
            reason_text = f"선택하신 '{themes_str}' 테마와 '{transport}' 접근성을 고려한 {region_target} 최적화 코스입니다."

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
        
        print("[Flask] AI 연산 완료 및 응답 데이터 전송 성공")
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"[Flask] 에러 발생: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)