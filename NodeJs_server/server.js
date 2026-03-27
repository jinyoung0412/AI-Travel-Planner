const express = require('express');
const axios = require('axios');
const cors = require('cors');

const app = express();
app.use(express.json());
app.use(cors());

const FLASK_SERVER_URL = 'http://127.0.0.1:5000/ai-predict';

app.post('/ai-predict', async (req, res) => {
    try {
        console.log("[Node.js] 앱에서 받은 데이터:", req.body);
        
        const flaskResponse = await axios.post(FLASK_SERVER_URL, req.body);
        console.log("[Node.js] Flask 서버 통신 성공 (AI 연산 완료)");

        res.status(200).json({
            success: true,
            message: "AI 추천 완료",
            data: flaskResponse.data
        });
        
    } catch (error) {
        if (error.response) {
            console.error("[Node.js] Flask 서버 에러:", error.response.data);
            res.status(error.response.status).json({
                success: false,
                message: "Flask 서버 내부 에러",
                error: error.response.data
            });
        } else {
            console.error("[Node.js] 통신 에러:", error.message);
            res.status(500).json({
                success: false,
                message: "AI 서버 통신 에러",
                error: error.message
            });
        }
    }
});

const PORT = 8080;
app.listen(PORT, '0.0.0.0', () => {
    console.log(`[Node] 서버가 0.0.0.0:${PORT} 에서 실행 중입니다.`);
});