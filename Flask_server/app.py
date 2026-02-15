from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# Node.js에서 오는 요청을 허용 (보안 문지기)
CORS(app) 

# [API] Node.js가 데이터를 던지는 구멍
@app.route('/ai-predict', methods=['POST'])
def ai_predict():
    # 1. 데이터 받기
    data = request.get_json()
    print(f"📦 [Flask] Node.js에서 받은 데이터: {data}")

    # 2. (임시) 가짜 결과 만들어서 돌려주기 (테스트용)
    dummy_result = {
        "recommended_course": ["협재 해수욕장", "오설록", "금오름"],
        "reason": "사용자님이 선호하는 '힐링' 태그 기반 추천",
        "total_time": "4시간"
    }

    return jsonify(dummy_result)

if __name__ == '__main__':
    # 0.0.0.0으로 열어야 외부 접속이 원활함
    app.run(host='0.0.0.0', port=5000, debug=True)