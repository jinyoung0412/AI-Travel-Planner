from flask import Flask, jsonify, request
# from flask_cors import CORS  # 나중에 연동할 때 주석 해제

app = Flask(__name__)
# CORS(app) # 나중에 연동할 때 주석 해제

# 한글 깨짐 방지
app.config['JSON_AS_ASCII'] = False

@app.route('/')
def home():
    return "Flask AI Server is Running!"

# Node.js와 통신 테스트용 API
@app.route('/api/test', methods=['POST'])
def test_api():
    data = request.json
    print(f"Node에서 받은 데이터: {data}")
    return jsonify({"status": "success", "message": "Flask가 데이터를 받았습니다!", "echo": data})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)