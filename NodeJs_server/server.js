const express = require('express');
const axios   = require('axios');
const cors    = require('cors');
const { findPlace } = require('./kakao_place');
require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });

const app = express();
app.use(express.json());
app.use(cors());

const FLASK = 'http://127.0.0.1:5001';

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

// 텍스트 → 페르소나 태그 자동 제안
app.post('/suggest/tags', (req, res) => forwardToFlask(req, res, '/suggest/tags'));

// 지금 당장 뭘 할지 — 단일 장소 즉시 추천 (상위 5곳)
app.post('/recommend/spot', (req, res) => forwardToFlask(req, res, '/recommend/spot'));

// 오늘 뭘 할지 — 5-stop 당일 코스 추천 (3가지 옵션)
app.post('/recommend/course', (req, res) => forwardToFlask(req, res, '/recommend/course'));

// Name-address-coordinate evidence is required before opening another provider's
// detail page. Ambiguous/missing matches fall back to the selected coordinate pin.
app.get('/kakao/place', async (req, res) => {
    const { name, address = '', lat, lng } = req.query;
    const userLat = Number(lat), userLng = Number(lng);
    if (typeof name !== 'string' || !name.trim() || typeof address !== 'string' ||
        typeof lat !== 'string' || typeof lng !== 'string' || !lat.trim() || !lng.trim() ||
        !Number.isFinite(userLat) || !Number.isFinite(userLng) ||
        Math.abs(userLat) > 90 || Math.abs(userLng) > 180) {
        return res.status(400).json({ error: 'name, lat, lng 파라미터를 확인해주세요.' });
    }
    try {
        const match = await findPlace(axios, { name, address, lat: userLat, lng: userLng },
            { Authorization: `KakaoAK ${process.env.KAKAO_API_KEY}` });
        return res.json({ place_url: match?.place_url ?? null, kakao_place_id: match?.id ?? null });
    } catch (error) {
        console.error('[Node] 카카오 API 오류:', error.message);
        return res.status(502).json({ error: '지도 상세 정보를 조회하지 못했습니다.' });
    }
});

const PORT = 8080;
app.listen(PORT, '0.0.0.0', () => {
    console.log(`[Node] 서버 실행 중: 0.0.0.0:${PORT}`);
});
