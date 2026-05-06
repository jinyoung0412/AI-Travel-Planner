const express = require('express');
const axios   = require('axios');
const cors    = require('cors');
require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });

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

// 텍스트 → 페르소나 태그 자동 제안
app.post('/suggest/tags', (req, res) => forwardToFlask(req, res, '/suggest/tags'));

// 지금 당장 뭘 할지 — 단일 장소 즉시 추천 (상위 5곳)
app.post('/recommend/spot', (req, res) => forwardToFlask(req, res, '/recommend/spot'));

// 오늘 뭘 할지 — 5-stop 당일 코스 추천 (3가지 옵션)
app.post('/recommend/course', (req, res) => forwardToFlask(req, res, '/recommend/course'));

// 카카오 결과 이름이 검색어와 일치하는지 확인
// "설화산" 검색 시 "설화산펜션" 같은 엉뚱한 결과 차단
function isNameMatch(resultName, query) {
    return resultName === query || resultName.startsWith(query + ' ');
}

// 두 좌표 간 거리(미터) 계산
function haversineM(lat1, lng1, lat2, lng2) {
    const R = 6371000;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLng = (lng2 - lng1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2
        + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180)
        * Math.sin(dLng / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// 카카오 로컬 API — 장소명 + 좌표로 place_url 반환 (2단계 탐색)
app.get('/kakao/place', async (req, res) => {
    const { name, lat, lng } = req.query;
    if (!name || !lat || !lng) {
        return res.status(400).json({ error: 'name, lat, lng 파라미터 필요' });
    }
    const headers = { Authorization: `KakaoAK ${process.env.KAKAO_API_KEY}` };
    const userLat = parseFloat(lat);
    const userLng = parseFloat(lng);

    try {
        // 1차: 이름 + 좌표 반경 3km
        const r1 = await axios.get(
            'https://dapi.kakao.com/v2/local/search/keyword.json',
            { params: { query: name, x: userLng, y: userLat, radius: 1000, size: 1 }, headers }
        );
        const doc1 = r1.data.documents?.[0];
        if (doc1?.place_url && isNameMatch(doc1.place_name, name)) {
            console.log(`[kakao] 1차 탐색 성공: ${name}`);
            return res.json({ place_url: doc1.place_url });
        }

        // 2차: 좌표 없이 이름만 검색 → 이름 일치 + 가장 가까운 것 선택 (10km 이내)
        const r2 = await axios.get(
            'https://dapi.kakao.com/v2/local/search/keyword.json',
            { params: { query: name, size: 5 }, headers }
        );
        const docs = r2.data.documents ?? [];
        const closest = docs
            .filter(d => d.place_url && isNameMatch(d.place_name, name))
            .map(d => ({ ...d, dist: haversineM(userLat, userLng, parseFloat(d.y), parseFloat(d.x)) }))
            .filter(d => d.dist <= 10000)
            .sort((a, b) => a.dist - b.dist)[0];

        if (closest) {
            console.log(`[kakao] 2차 탐색 성공: ${name} (거리 ${Math.round(closest.dist)}m)`);
            return res.json({ place_url: closest.place_url });
        }

        console.log(`[kakao] 탐색 실패: ${name}`);
        res.json({ place_url: null });
    } catch (error) {
        console.error('[Node] 카카오 API 오류:', error.message);
        res.status(500).json({ error: error.message });
    }
});

const PORT = 8080;
app.listen(PORT, '0.0.0.0', () => {
    console.log(`[Node] 서버 실행 중: 0.0.0.0:${PORT}`);
});
