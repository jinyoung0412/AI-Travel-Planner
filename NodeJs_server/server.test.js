const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { createApp } = require('./server');

async function request(app, { path = '/recommend/spot', body = {}, raw, method = 'POST', headers = {} } = {}) {
    const server = app.listen(0, '127.0.0.1');
    await new Promise(resolve => server.once('listening', resolve));
    try {
        return await new Promise((resolve, reject) => {
            const req = http.request({ host: '127.0.0.1', port: server.address().port, path, method,
                headers: { 'Content-Type': 'application/json', ...headers } }, res => {
                const chunks = [];
                res.on('data', chunk => chunks.push(chunk));
                res.on('end', () => resolve({ status: res.statusCode, headers: res.headers,
                    body: JSON.parse(Buffer.concat(chunks).toString()) }));
            });
            req.on('error', reject);
            req.end(method === 'POST' ? raw ?? JSON.stringify(body) : undefined);
        });
    } finally {
        await new Promise(resolve => server.close(resolve));
    }
}

const fail = () => { throw new Error('External calls forbidden'); };
const fake = post => createApp({ httpClient: { post, get: fail }, env: {} });

test('travel interpretation preserves the versioned preview and exact manual controls', async () => {
    const preview = { travel_request: { schema_version: 1, stages: [{ id: 's1' }] },
        intent_token: 'signed', mode_switch_required: false, target_mode: 'spot', target_count: 1 };
    const input = { intent_version: 1, user_text: '친구와 조용한 카페', region: '아산', transport: '차' };
    const response = await request(fake(async (url, body) => {
        assert.ok(url.endsWith('/travel/interpret'));
        assert.deepEqual(body, input);
        return { data: preview };
    }), { path: '/travel/interpret', body: input });
    assert.equal(response.status, 200);
    assert.deepEqual(response.body.data, preview);
});

test('intent failures retain confirmation and unverified alternatives without becoming success', async () => {
    for (const reason of ['intent_unavailable', 'intent_conflict', 'intent_expired',
        'course_confirmation_required', 'unverified_conditions', 'insufficient_candidates', 'activity_clarification_required']) {
        const status = reason === 'intent_unavailable' ? 503 : reason === 'intent_expired' ? 400 : 422;
        const body = { error: '요청을 확인해주세요.', reason,
            metadata: { intent_status: 'needs_confirmation', constraints_relaxed: [] },
            alternatives: [{ stage_id: 's2', names: ['미확인 맥주집'] }] };
        const response = await request(fake(async () => { throw { response: { status, data: body } }; }),
            { path: '/recommend/course' });
        assert.equal(response.status, status);
        assert.deepEqual(response.body, { success: false, error: body });
    }
});

test('activity clarification reaches the app without issuing a recommendation token', async () => {
    const preview = { clarification_required: true,
        travel_request: { schema_version: 1, stages: [], ambiguities: [{ quote: '데이트' }] },
        clarification: { kind: 'activity', message: '어떤 활동을 원하세요?', token: 'signed-clarification',
            options: [{ value: '카페', label: '카페·디저트' }, { value: '자연·산책', label: '산책·자연' }] } };
    const input = { user_text: '연인이랑 데이트 할 곳을 찾고있어요', intent_version: 1, mode: 'spot', seed: 19 };
    const response = await request(fake(async (url, body) => {
        assert.ok(url.endsWith('/travel/interpret'));
        assert.deepEqual(body, input);
        return { data: preview };
    }), { path: '/travel/interpret', body: input });
    assert.equal(response.status, 200);
    assert.deepEqual(response.body, { success: true, data: preview });
    assert.equal(response.body.data.intent_token, undefined);
});

test('malformed activity clarification fails at the gateway', async () => {
    const preview = { clarification_required: true, travel_request: { stages: [] },
        clarification: { kind: 'activity', message: '활동 선택', token: 'signed',
            options: [{ value: '카페', label: '카페·디저트' }] } };
    const mutations = [
        body => { body.travel_request = []; },
        body => { body.intent_token = 'mixed-purpose'; },
        body => { body.clarification_required = 'true'; },
        body => { body.clarification = null; },
        body => { body.clarification.kind = 'unknown'; },
        body => { body.clarification.message = ''; },
        body => { body.clarification.token = ''; },
        body => { body.clarification.token = 'x'.repeat(12001); },
        body => { body.clarification.options = []; },
        body => { body.clarification.options[0].value = '임의 활동'; },
        body => { body.clarification.options[0].label = null; },
        body => { body.clarification.options.push({ ...body.clarification.options[0] }); },
    ];
    for (const mutate of mutations) {
        const body = structuredClone(preview);
        mutate(body);
        const response = await request(fake(async () => ({ data: body })), { path: '/travel/interpret' });
        assert.equal(response.status, 502);
        assert.equal(response.body.error.reason, 'invalid_upstream_response');
    }
});

test('malformed interpretation response is rejected', async () => {
    for (const body of [{ travel_request: [], intent_token: 't' }, { travel_request: {} }, null]) {
        const response = await request(fake(async () => ({ data: body })), { path: '/travel/interpret' });
        assert.equal(response.status, 502);
    }
});

test('all recommendation routes preserve the existing success envelope and bounded transport', async () => {
    for (const [path, field] of [['/recommend/spot', 'places'], ['/recommend/course', 'courses'], ['/suggest/tags', 'tags']]) {
        const body = { [field]: [], metadata: { preference_evidence: 'unavailable' } };
        const input = { user_text: '공원' };
        const app = createApp({ env: { FLASK_BASE_URL: 'http://mock.local:6001/', FLASK_TIMEOUT_MS: '1234' },
            httpClient: { post: async (url, data, options) => {
                assert.equal(url, `http://mock.local:6001${path}`);
                assert.deepEqual(data, input);
                assert.equal(options.timeout, 1234);
                assert.equal(options.maxRedirects, 0);
                return { data: body };
            } } });
        assert.deepEqual(await request(app, { path, body: input }).then(r => r.body), { success: true, data: body });
    }
});

test('400, 422 and 503 from Flask retain actionable structured details', async () => {
    const cases = [
        [400, { error: 'count는 정수여야 합니다.', reason: 'invalid_request' }],
        [422, { error: '지역 밖', reason: 'outside_service_area' }],
        [422, { error: '장소 종류 필요', reason: 'category_required' }],
        [422, { error: '장소 부족', courses: [], course_metrics: [],
            metadata: { reason: 'missing_slot_candidates', constraints_relaxed: [] } }],
        [503, { error: '언어 해석 불가', reason: 'category_unavailable' }],
        [503, { tags: [], error: '태그 제안 불가', reason: 'tags_unavailable' }],
    ];
    for (const [status, body] of cases) {
        const response = await request(fake(async () => { throw { response: { status, data: body } }; }));
        assert.equal(response.status, status);
        assert.deepEqual(response.body, { success: false, error: body });
    }
});

test('transport timeout, internal errors and malformed upstream bodies never leak details', async () => {
    for (const [error, status, reason] of [
        [{ code: 'ECONNABORTED', message: 'secret address' }, 504, 'upstream_timeout'],
        [{ code: 'ECONNREFUSED', message: 'secret address' }, 502, 'upstream_unavailable'],
        [{ response: { status: 500, data: { error: 'secret stack' } } }, 502, 'upstream_error'],
        [{ response: { status: 502, data: '<html>secret stack</html>' } }, 502, 'upstream_error'],
        [{ response: { status: 503, data: '<html>secret stack</html>' } }, 502, 'upstream_error'],
        [{ response: { status: 422, data: { metadata: { reason: 'missing_slot_candidates' }, stack: 'secret stack' } } }, 502, 'invalid_upstream_response'],
        [{ code: 'ETIMEDOUT', response: { status: 500, data: 'secret' } }, 504, 'upstream_timeout'],
    ]) {
        const result = await request(fake(async () => { throw error; }));
        assert.equal(result.status, status);
        assert.equal(result.body.error.reason, reason);
        assert.ok(!JSON.stringify(result.body).includes('secret'));
        if (reason === 'upstream_error') assert.ok(!result.body.error.error.includes('연결'));
    }
    for (const data of ['<html>private stack</html>', [], null, { places: 'bad' }]) {
        const result = await request(fake(async () => ({ data })));
        assert.equal(result.status, 502);
        assert.equal(result.body.error.reason, 'invalid_upstream_response');
    }
});

test('invalid JSON, oversized requests and unknown paths use safe JSON errors', async () => {
    const app = fake(fail);
    assert.equal((await request(app, { raw: '{bad' })).status, 400);
    assert.equal((await request(app, { body: { user_text: 'x'.repeat(17000) } })).status, 413);
    const missing = await request(app, { path: '/private', method: 'GET' });
    assert.equal(missing.status, 404);
    assert.equal(missing.body.error.reason, 'invalid_request');
});

const mapPath = '/kakao/place?name=%EC%95%84%EC%A7%80%ED%8A%B8&address=%EC%B6%A9%EB%82%A8%20%EC%B2%9C%EC%95%88%EC%8B%9C%20%ED%85%8C%EC%8A%A4%ED%8A%B8%EB%A1%9C%201&lat=36.8151&lng=127.1139';
test('keyless map lookup makes no external call and preserves pin fallback', async () => {
    const response = await request(fake(fail), { method: 'GET', path: mapPath });
    assert.equal(response.status, 200);
    assert.equal(response.body.place_url, null);
    assert.equal(response.body.reason, 'map_not_configured');
    for (const suffix of ['&lat=', '&lng=NaN', '&lat=91', '&name=']) {
        assert.equal((await request(fake(fail), { method: 'GET', path: mapPath + suffix })).status, 400);
    }
});

test('map success, malformed response and timeout are handled with mocked HTTP', async () => {
    for (const [get, status] of [
        [async () => ({ data: { documents: [{ id: '1', place_url: 'https://place.map.kakao.com/1',
            place_name: '아지트', x: '127.1139', y: '36.8151', road_address_name: '충남 천안시 테스트로 1' }] } }), 200],
        [async () => ({ data: '<html>secret</html>' }), 502],
        [async () => { throw { code: 'ECONNABORTED' }; }, 504],
    ]) {
        const app = createApp({ env: { KAKAO_API_KEY: 'mock-key' }, httpClient: { get } });
        const response = await request(app, { method: 'GET', path: mapPath });
        assert.equal(response.status, status);
        if (status === 200) assert.equal(response.body.place_url, 'https://place.map.kakao.com/1');
    }
});

test('CORS is opt-in for specified browser origins; native clients need no CORS', async () => {
    const app = createApp({ env: { CORS_ORIGINS: 'http://localhost:8000' }, httpClient: { post: fail } });
    assert.equal((await request(app, { method: 'GET', path: '/missing', headers: { Origin: 'http://localhost:8000' } })).headers['access-control-allow-origin'], 'http://localhost:8000');
    assert.equal((await request(app, { method: 'GET', path: '/missing', headers: { Origin: 'https://other.invalid' } })).headers['access-control-allow-origin'], undefined);
    assert.equal((await request(fake(fail), { method: 'GET', path: '/missing', headers: { Origin: 'http://localhost:8000' } })).headers['access-control-allow-origin'], undefined);
});

test('invalid startup settings fail before opening a listener', () => {
    for (const env of [{ FLASK_TIMEOUT_MS: '0' }, { FLASK_TIMEOUT_MS: 'NaN' },
        { FLASK_BASE_URL: 'file:///tmp' }, { FLASK_BASE_URL: 'http://user:secret@localhost' }]) {
        assert.throws(() => createApp({ env }));
    }
});

test('recent result IDs and selected course order cross the gateway without reinterpretation', async () => {
    for (const [path, field] of [['/recommend/spot', 'places'], ['/recommend/course', 'courses'], ['/travel/interpret', 'travel_request']]) {
        const input = { user_text: '여자친구랑 100일기념 데이트', intent_version: 1,
            plan_mode: 'manual', slot_types: ['음식', '자연·산책', '카페'],
            recent_place_ids: ['local:v1:first', 'local:v1:second'], seed: 928, randomize: true };
        const data = field === 'travel_request' ? { travel_request: { stages: [] }, intent_token: 'signed' } : { [field]: [] };
        const response = await request(fake(async (url, body) => {
            assert.ok(url.endsWith(path));
            assert.deepEqual(body, input);
            return { data };
        }), { path, body: input });
        assert.equal(response.status, 200);
        assert.deepEqual(response.body.data, data);
    }
});
