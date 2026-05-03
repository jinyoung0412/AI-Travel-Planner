const express = require('express');
const axios   = require('axios');
const cors    = require('cors');

const app = express();
app.use(express.json());
app.use(cors());

const FLASK = 'http://127.0.0.1:5000';

async function forwardToFlask(req, res, path) {
    try {
        console.log(`[Node] 수신 (${path}):`, req.body);
        const response = await axios.post(`${FLASK}${path}`, req.body);
        console.log(`[Node] Flask 응답 완료 (${path})`);
        res.status(200).json({ success: true, data: response.data });
    } catch (error) {
        if (error.response) {
            console.error(`[Node] Flask 오류 (${path}):`, error.response.data);
            res.status(error.response.status).json({
                success: false,
                error: error.response.data,
            });
        } else {
            console.error(`[Node] 통신 오류 (${path}):`, error.message);
            res.status(500).json({ success: false, error: error.message });
        }
    }
}

// 지금 당장 뭘 할지 — 단일 장소 즉시 추천 (상위 5곳)
app.post('/recommend/spot', (req, res) => forwardToFlask(req, res, '/recommend/spot'));

// 오늘 뭘 할지 — 3-stop 당일 코스 추천
app.post('/recommend/course', (req, res) => forwardToFlask(req, res, '/recommend/course'));

const PORT = 8080;
app.listen(PORT, '0.0.0.0', () => {
    console.log(`[Node] 서버 실행 중: 0.0.0.0:${PORT}`);
});
