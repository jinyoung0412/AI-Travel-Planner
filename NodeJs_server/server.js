const express = require('express');
const axios   = require('axios');
const cors    = require('cors');
const jwt     = require('jsonwebtoken');
const db      = require('./db');
require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });

const JWT_SECRET = process.env.JWT_SECRET;

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

// ── JWT 인증 미들웨어 ─────────────────────────────────────────
function authMiddleware(req, res, next) {
    const header = req.headers.authorization;
    if (!header || !header.startsWith('Bearer ')) {
        return res.status(401).json({ error: '인증이 필요합니다.' });
    }
    try {
        req.user = jwt.verify(header.slice(7), JWT_SECRET);
        next();
    } catch {
        res.status(401).json({ error: '유효하지 않은 토큰입니다.' });
    }
}

// ── 카카오 로그인 ─────────────────────────────────────────────
app.post('/auth/kakao', async (req, res) => {
    const { access_token } = req.body;
    if (!access_token) return res.status(400).json({ error: 'access_token 필요' });

    try {
        const { data } = await axios.get('https://kapi.kakao.com/v2/user/me', {
            headers: { Authorization: `Bearer ${access_token}` },
        });

        const kakaoId   = String(data.id);
        const nickname  = data.kakao_account?.profile?.nickname ?? null;
        const profileImg = data.kakao_account?.profile?.profile_image_url ?? null;

        const existing = db.prepare('SELECT * FROM users WHERE kakao_id = ?').get(kakaoId);
        let userId;
        if (existing) {
            db.prepare('UPDATE users SET nickname = ?, profile_img = ? WHERE kakao_id = ?')
              .run(nickname, profileImg, kakaoId);
            userId = existing.id;
        } else {
            const result = db.prepare(
                'INSERT INTO users (kakao_id, nickname, profile_img) VALUES (?, ?, ?)'
            ).run(kakaoId, nickname, profileImg);
            userId = result.lastInsertRowid;
        }

        const token = jwt.sign({ userId, nickname, profileImg }, JWT_SECRET, { expiresIn: '30d' });
        console.log(`[auth] 로그인: ${nickname} (id=${userId})`);
        res.json({ token, nickname, profile_img: profileImg });
    } catch (e) {
        console.error('[auth] 카카오 로그인 오류:', e.message);
        res.status(500).json({ error: e.message });
    }
});

// ── 저장 — 스팟 ───────────────────────────────────────────────
app.get('/saves/spots', authMiddleware, (req, res) => {
    const spots = db.prepare('SELECT * FROM saved_spots WHERE user_id = ? ORDER BY saved_at DESC')
                    .all(req.user.userId);
    res.json(spots);
});

app.post('/saves/spots', authMiddleware, (req, res) => {
    const { name, lat, lng, category, kakao_url } = req.body;
    if (!name) return res.status(400).json({ error: 'name 필요' });
    const result = db.prepare(
        'INSERT INTO saved_spots (user_id, name, lat, lng, category, kakao_url) VALUES (?, ?, ?, ?, ?, ?)'
    ).run(req.user.userId, name, lat, lng, category, kakao_url);
    res.json({ id: result.lastInsertRowid });
});

app.delete('/saves/spots/:id', authMiddleware, (req, res) => {
    db.prepare('DELETE FROM saved_spots WHERE id = ? AND user_id = ?')
      .run(req.params.id, req.user.userId);
    res.json({ ok: true });
});

// ── 저장 — 코스 ───────────────────────────────────────────────
app.get('/saves/courses', authMiddleware, (req, res) => {
    const courses = db.prepare('SELECT * FROM saved_courses WHERE user_id = ? ORDER BY created_at DESC')
                      .all(req.user.userId);
    const result = courses.map(c => ({
        ...c,
        spots: db.prepare('SELECT * FROM saved_course_spots WHERE course_id = ? ORDER BY spot_order')
                  .all(c.id),
    }));
    res.json(result);
});

app.post('/saves/courses', authMiddleware, (req, res) => {
    const { region, spots } = req.body;
    if (!spots?.length) return res.status(400).json({ error: 'spots 필요' });

    const course = db.prepare('INSERT INTO saved_courses (user_id, region) VALUES (?, ?)')
                     .run(req.user.userId, region);
    const courseId = course.lastInsertRowid;

    const insertSpot = db.prepare(
        'INSERT INTO saved_course_spots (course_id, spot_order, name, lat, lng, category, kakao_url) VALUES (?, ?, ?, ?, ?, ?, ?)'
    );
    spots.forEach((s, i) => insertSpot.run(courseId, i, s.name, s.lat, s.lng, s.category, s.kakao_url));

    res.json({ id: courseId });
});

app.delete('/saves/courses/:id', authMiddleware, (req, res) => {
    db.prepare('DELETE FROM saved_courses WHERE id = ? AND user_id = ?')
      .run(req.params.id, req.user.userId);
    res.json({ ok: true });
});

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
