from flask import Flask, request, jsonify

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
        transport = data.get('transport', '대중교통')
        
        # --------------------------------------------------------
        # ※ 나중에 이 부분에 실제 군집화(Clustering) 모듈을 연동합니다.
        # 지금은 화면이 잘 넘어가는지 테스트하기 위한 가짜 데이터입니다.
        # --------------------------------------------------------
        
        themes_str = ', '.join(themes) if themes else '일반'
        
        # 3. Node.js로 돌려줄 응답 데이터 구성
        response_data = {
            "reason": f"선택하신 '{themes_str}' 테마와 '{transport}' 접근성을 고려한 '{region}' 맞춤 코스입니다.",
            "recommended_course": ["온양온천역", "신정호 관광지", "파라다이스 스파 도고"],
            "total_time": "12시간"
        }
        
        # 4. JSON 형태로 변환하여 정상(200) 응답
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"🔥 [Flask] 에러 발생: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Flask 서버 실행 (포트 5000)
    app.run(host='127.0.0.1', port=5000, debug=True)