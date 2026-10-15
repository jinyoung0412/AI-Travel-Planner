const express = require('express');
const axios = require('axios');
const cors = require('cors');
const { findPlace } = require('./kakao_place');
require('dotenv').config({ path: require('path').join(__dirname, '..', '.env'), quiet: true });

function positiveInteger(value, fallback, max) {
    const number = value === undefined ? fallback : Number(value);
    if (!Number.isInteger(number) || number < 1 || number > max) throw new Error('Invalid server configuration');
    return number;
}

function createApp({ httpClient = axios, env = process.env } = {}) {
    const app = express();
    const flask = (env.FLASK_BASE_URL || 'http://127.0.0.1:5001').replace(/\/+$/, '');
    const flaskUrl = new URL(flask);
    if (!['http:', 'https:'].includes(flaskUrl.protocol) || flaskUrl.username || flaskUrl.password ||
        flaskUrl.search || flaskUrl.hash) throw new Error('Invalid FLASK_BASE_URL');
    const timeout = positiveInteger(env.FLASK_TIMEOUT_MS, 30000, 120000);
    const origins = (env.CORS_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean);
    if (origins.length) app.use(cors({ origin: origins }));
    app.use(express.json({ limit: '16kb' }));

    async function forwardToFlask(req, res, path, resultField) {
        try {
            const response = await httpClient.post(`${flask}${path}`, req.body, {
                timeout, maxContentLength: 512 * 1024, maxRedirects: 0,
            });
            const body = response.data;
            if (!body || typeof body !== 'object' || Array.isArray(body) || !Array.isArray(body[resultField])) {
                return res.status(502).json({ success: false,
                    error: { error: '추천 서버의 응답을 확인하지 못했습니다.', reason: 'invalid_upstream_response' } });
            }
            return res.status(200).json({ success: true, data: body });
        } catch (error) {
            const status = error.response?.status;
            const body = error.response?.data;
            // Only schema/constraint failures and documented service failures cross the boundary.
            // HTML, stack traces and transport exception strings never reach the app.
            if ([400, 422, 503].includes(status) && body && typeof body === 'object' &&
                !Array.isArray(body) && typeof body.error === 'string' &&
                ['invalid_request', 'outside_service_area', 'category_required', 'category_unavailable', 'tags_unavailable'].includes(body.reason)) {
                return res.status(status).json({ success: false, error: body });
            }
            if (status === 422 && body && typeof body === 'object' &&
                body.metadata && ['insufficient_candidates', 'missing_slot_candidates', 'insufficient_distinct_places',
                    'insufficient_unique_courses'].includes(body.metadata.reason)) {
                return res.status(422).json({ success: false, error: body });
            }
            const timedOut = ['ECONNABORTED', 'ETIMEDOUT'].includes(error.code);
            return res.status(timedOut ? 504 : 502).json({ success: false, error: {
                error: timedOut ? '추천 서버 응답 시간이 초과되었습니다.' : '추천 서버에 연결하지 못했습니다.',
                reason: timedOut ? 'upstream_timeout' : 'upstream_unavailable',
            } });
        }
    }

    for (const [path, field] of [['/suggest/tags', 'tags'], ['/recommend/spot', 'places'], ['/recommend/course', 'courses']]) {
        app.post(path, (req, res) => forwardToFlask(req, res, path, field));
    }

    // Ambiguous or missing identity evidence falls back to the selected coordinate pin.
    app.get('/kakao/place', async (req, res) => {
        const { name, address = '', lat, lng } = req.query;
        const userLat = Number(lat), userLng = Number(lng);
        if (typeof name !== 'string' || !name.trim() || name.length > 200 ||
            typeof address !== 'string' || address.length > 500 ||
            typeof lat !== 'string' || typeof lng !== 'string' || !lat.trim() || !lng.trim() ||
            !Number.isFinite(userLat) || !Number.isFinite(userLng) ||
            Math.abs(userLat) > 90 || Math.abs(userLng) > 180) {
            return res.status(400).json({ error: 'name, lat, lng 파라미터를 확인해주세요.', reason: 'invalid_request' });
        }
        const key = (env.KAKAO_API_KEY || '').trim();
        if (!key) return res.json({ place_url: null, kakao_place_id: null, reason: 'map_not_configured' });
        try {
            const match = await findPlace(httpClient, { name: name.trim(), address, lat: userLat, lng: userLng },
                { Authorization: `KakaoAK ${key}` });
            return res.json({ place_url: match?.place_url ?? null, kakao_place_id: match?.id ?? null });
        } catch (error) {
            const timedOut = ['ECONNABORTED', 'ETIMEDOUT'].includes(error.code);
            return res.status(timedOut ? 504 : 502).json({
                error: '지도 상세 정보를 조회하지 못했습니다.',
                reason: timedOut ? 'upstream_timeout' : 'upstream_unavailable',
            });
        }
    });

    app.use((req, res) => res.status(404).json({ success: false,
        error: { error: '요청한 경로가 없습니다.', reason: 'invalid_request' } }));
    app.use((error, req, res, next) => {
        if (res.headersSent) return next(error);
        const status = error.type === 'entity.too.large' ? 413 : error.type === 'entity.parse.failed' ? 400 : 500;
        return res.status(status).json({ success: false, error: {
            error: status === 413 ? '요청 크기는 16KB 이하여야 합니다.' : status === 400 ? 'JSON 요청을 확인해주세요.' : '요청 처리 중 오류가 발생했습니다.',
            reason: status === 500 ? 'internal_error' : 'invalid_request',
        } });
    });
    return app;
}

function startServer(env = process.env) {
    const port = positiveInteger(env.NODE_PORT || env.PORT, 8080, 65535);
    const host = env.NODE_HOST || '127.0.0.1';
    return createApp({ env }).listen(port, host, () => console.log(`[Node] 서버 실행 중: ${host}:${port}`));
}

if (require.main === module) startServer();
module.exports = { createApp, startServer };
