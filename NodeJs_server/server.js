const express = require('express');
const axios = require('axios');
const app = express();
const PORT = 8080; // 👈 여기를 8080으로 맞춰야 합니다!

app.use(express.json());

// [API] 앱(Flutter)에서 여행 추천 요청을 받는 곳
app.post('/api/recommend', async (req, res) => {
    console.log('📱 [Node] 앱에서 요청 도착:', req.body);

    try {
        // 1. Node.js가 데이터를 들고 Flask AI 서버(5000번)로 달려감
        // 주의: Flask 주소는 보통 127.0.0.1:5000 사용
        const flaskResponse = await axios.post('http://127.0.0.1:5000/ai-predict', req.body);
        
        console.log('🤖 [Node] Flask 응답 받음:', flaskResponse.data);

        // 2. AI 결과를 앱에게 최종 전달
        res.json({
            success: true,
            message: "AI 추천 완료",
            data: flaskResponse.data
        });

    } catch (error) {
        console.error('🔥 [Node] Flask 통신 에러:', error.message);
        res.status(500).json({ success: false, message: "AI 서버 연결 실패" });
    }
});

app.listen(PORT, () => {
    console.log(`🚀 Node.js 서버 실행 중: http://localhost:${PORT}`); // 👈 이제 8080으로 뜰 겁니다
});