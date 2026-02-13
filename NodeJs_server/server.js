// server.js
const express = require('express');
const cors = require('cors');
const app = express();
const port = 3000; // 서버 포트 번호

// 1. 보안 설정 (모든 곳에서 접속 허용)
app.use(cors());

// 2. JSON 데이터 해석기 장착 (앱에서 보낸 데이터 읽으려면 필수)
app.use(express.json());

// [테스트 1] 주소창에 쳤을 때 (GET 요청)
app.get('/', (req, res) => {
    res.send('Node.js 서버 작동 시작 (Team Lead Server)');
});

// [테스트 2] 앱에서 데이터 보냈을 때 (POST 요청)
app.post('/api/test', (req, res) => {
    const clientData = req.body;
    console.log("📱 앱에서 받은 데이터:", clientData);

    // 잘 받았다고 응답해주기
    res.json({
        message: "데이터 수신 완료.",
        yourData: clientData
    });
});

// 서버 시작
app.listen(port, () => {
    console.log(`✅ 서버가 http://localhost:${port} 에서 대기 중입니다.`);
});