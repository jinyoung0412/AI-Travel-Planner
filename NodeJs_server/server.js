const express = require('express');
const axios = require('axios');
const cors = require('cors');

const app = express();
app.use(express.json());
app.use(cors());

// 파이썬 Flask 서버 주소
const FLASK_SERVER_URL = 'http://127.0.0.1:5000/ai-predict';

// 앱에서 POST 요청으로 /ai-predict 주소로 접근했을 때 실행됨
app.post('/ai-predict', async (req, res) => {
    try {
        console.log("[Node.js] 앱에서 받은 데이터:", req.body);
        
        // 1. 받은 데이터를 그대로 Flask 서버로 쏴줌
        const flaskResponse = await axios.post(FLASK_SERVER_URL, req.body);
        
        console.log("[Node.js] Flask에서 받은 응답:", flaskResponse.data);

        // 2. Flask의 결과를 앱이 읽기 편한 규격(success, data 등)으로 포장해서 응답
        res.status(200).json({
            success: true,
            message: "AI 추천 완료",
            data: flaskResponse.data
        });
        
    } catch (error) {
        console.error(" [Node.js] 에러 발생:", error.message);
        
        // Flask 서버가 꺼져있거나 통신에 실패했을 때 500 에러를 앱으로 보냄
        res.status(500).json({
            success: false,
            message: "AI 서버 통신 에러",
            error: error.message
        });
    }
});

const PORT = 8080;
app.listen(PORT, () => {
    console.log(`[Node] 서버가 ${PORT} 포트에서 실행 중입니다.`); //uhiuhu
});