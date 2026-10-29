const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const http = require('node:http');
const { once } = require('node:events');
const { createCourseRouteHandler, normalize, validRequest } = require('./course_routes');
const { createApp } = require('./server');

const secret = 'test-only-server-route-secret';
const stops = [
    { index: 0, name: '출발', lng: 127.1, lat: 36.8 },
    { index: 1, name: '도착', lng: 127.101, lat: 36.801 },
    { index: 2, name: '다음', lng: 127.102, lat: 36.802 },
];
const coords = stop => [stop.lng, stop.lat];
const step = (points, type = 'WALKING') => ({ path: { points }, properties: { type } });
function provider(mode, from = stops[0], to = stops[1]) {
    const points = [coords(from), coords(to)];
    const properties = { totalDistance: 170, totalTime: 130 };
    if (mode === 'car') return { routes: [{ result_code: 0,
        summary: { distance: 170, duration: 130 }, sections: [{ roads: [{ vertexes: points.flat() }] }] }] };
    if (mode === 'transit') return { status: 'OK', routes: [{ properties, steps: [step(points, 'BUS')] }] };
    return { status: 'OK', route: { properties, legs: [{ steps: [step(points)] }] } };
}
function makeHandler(get, options = {}) {
    return createCourseRouteHandler({ httpClient: { get }, env: { KAKAO_ROUTE_REST_API_KEY: secret }, ...options });
}
function start(handler, body = { mode: 'walk', stops: stops.slice(0, 2) }) {
    const req = new EventEmitter();
    req.body = body;
    req.headers = { authorization: 'untrusted-client-key' };
    const res = new EventEmitter();
    res.statusCode = 200;
    res.status = code => { res.statusCode = code; return res; };
    res.json = value => { res.body = value; res.writableEnded = true; res.writableFinished = true; return res; };
    const done = handler(req, res);
    return { req, res, done };
}
async function invoke(handler, body) {
    const run = start(handler, body);
    await run.done;
    assert.equal(run.req.listenerCount('aborted'), 0);
    assert.equal(run.res.listenerCount('close'), 0);
    return run.res;
}
function unavailable(res, reason) {
    assert.equal(res.statusCode, 200);
    assert.equal(res.body.success, true);
    assert.equal(res.body.data.status, 'unavailable');
    assert.deepEqual(res.body.data.segments, [{ fromIndex: 0, toIndex: 1,
        status: 'unavailable', reason, paths: [] }]);
    assert.equal(res.body.data.distanceMeters, undefined);
    assert.equal(res.body.data.durationSeconds, undefined);
    assert.ok(!JSON.stringify(res.body).includes(secret));
    assert.ok(!JSON.stringify(res.body).includes('private upstream detail'));
}

for (const mode of ['car', 'walk', 'transit']) {
    test(`course ${mode}: official endpoint, server credential, bounded request and original WGS84 geometry`, async () => {
        let calls = 0;
        const endpoints = { car: 'https://apis-navi.kakaomobility.com/v1/directions',
            walk: 'https://dapi.kakao.com/v2/routing/walk',
            transit: 'https://dapi.kakao.com/v2/routing/publictraffic' };
        const res = await invoke(makeHandler(async (url, config) => {
            calls++;
            assert.equal(url, endpoints[mode]);
            assert.deepEqual(config.headers, { Authorization: `KakaoAK ${secret}` });
            assert.equal(config.timeout, 6000);
            assert.equal(config.maxRedirects, 0);
            assert.equal(config.maxContentLength, 4 * 1024 * 1024);
            assert.equal(config.signal.aborted, false);
            assert.deepEqual(config.params, mode === 'car' ? {
                origin: '127.1,36.8', destination: '127.101,36.801', summary: false, alternatives: false,
            } : { start_x: 127.1, start_y: 36.8, end_x: 127.101, end_y: 36.801,
                input_coord: 'WGS84', output_coord: 'WGS84' });
            return { data: provider(mode) };
        }), { mode, stops: stops.slice(0, 2) });
        assert.equal(calls, 1);
        assert.deepEqual(res.body, { success: true, data: { mode, status: 'ready',
            segments: [{ fromIndex: 0, toIndex: 1, status: 'ready',
                paths: [{ mode, points: stops.slice(0, 2).map(coords) }], distanceMeters: 170, durationSeconds: 130 }],
            distanceMeters: 170, durationSeconds: 130 } });
    });
}

test('course endpoint is wired into POST /routes/course without Flask or external requests', async t => {
    let calls = 0;
    const app = createApp({ env: { KAKAO_API_KEY: secret }, httpClient: {
        post: async () => assert.fail('Flask must not receive routing requests'),
        get: async () => { calls++; return { data: provider('car') }; },
    } });
    const server = app.listen(0, '127.0.0.1');
    await once(server, 'listening');
    t.after(() => new Promise(resolve => server.close(resolve)));
    const result = await new Promise((resolve, reject) => {
        const req = http.request({ hostname: '127.0.0.1', port: server.address().port,
            path: '/routes/course', method: 'POST', headers: { 'content-type': 'application/json' } }, res => {
            const chunks = [];
            res.on('data', chunk => chunks.push(chunk));
            res.on('end', () => resolve({ status: res.statusCode, body: JSON.parse(Buffer.concat(chunks)) }));
        });
        req.on('error', reject);
        req.end(JSON.stringify({ mode: 'car', stops: stops.slice(0, 2) }));
    });
    assert.equal(result.status, 200);
    assert.equal(result.body.data.status, 'ready');
    assert.equal(calls, 1);
});

test('transit preserves walking, bus and subway parts without connecting real geometry gaps', () => {
    const a = coords(stops[0]), b = [127.1002, 36.8002], c = [127.1004, 36.8004];
    const d = [127.1006, 36.8006], z = coords(stops[1]);
    const body = provider('transit');
    body.routes[0].steps = [step([a, b]), step([b, c], 'BUS'), step([d, z], 'SUBWAY')];
    assert.deepEqual(normalize(body, 'transit', stops[0], stops[1]).paths,
        [{ mode: 'walk', points: [a, b] }, { mode: 'transit', points: [b, c] }, { mode: 'transit', points: [d, z] }]);
});

test('contiguous steps join only in the same mode, remove repeated coordinates and skip single-coordinate steps', () => {
    const a = coords(stops[0]), b = [127.1005, 36.8005], z = coords(stops[1]);
    const body = provider('walk');
    body.route.legs[0].steps = [step([a]), step([a, a, b]), step([b, z, z])];
    assert.deepEqual(normalize(body, 'walk', stops[0], stops[1]).paths,
        [{ mode: 'walk', points: [a, b, z] }]);
});

test('transit chooses the shortest-time itinerary and car chooses a successful result', () => {
    const body = provider('transit');
    body.routes.unshift({ properties: { totalTime: 900, totalDistance: 999 }, steps: [step(stops.slice(0, 2).map(coords), 'SUBWAY')] });
    assert.equal(normalize(body, 'transit', stops[0], stops[1]).durationSeconds, 130);
    const car = provider('car');
    car.routes.unshift({ result_code: 104, result_msg: 'private upstream detail' });
    assert.equal(normalize(car, 'car', stops[0], stops[1]).distanceMeters, 170);
});

for (const mode of ['walk', 'car']) {
    test(`${mode} no route produces no guessed line`, async () => {
        const data = mode === 'car' ? { routes: [{ result_code: 104 }] } : { status: 'NO_RESULTS' };
        unavailable(await invoke(makeHandler(async () => ({ data })), { mode, stops: stops.slice(0, 2) }), 'no_route');
    });
}

test('partial success keeps original segment identities and omits misleading course totals', async () => {
    const res = await invoke(makeHandler(async (_url, config) => config.params.start_x === stops[0].lng ?
        { data: provider('walk') } : { data: { status: 'NO_RESULTS' } }), { mode: 'walk', stops });
    assert.equal(res.body.data.status, 'partial');
    assert.deepEqual(res.body.data.segments.map(s => [s.fromIndex, s.toIndex, s.status]), [[0, 1, 'ready'], [1, 2, 'unavailable']]);
    assert.deepEqual(res.body.data.segments[1].paths, []);
    assert.equal(res.body.data.distanceMeters, undefined);
    assert.equal(res.body.data.durationSeconds, undefined);
});

test('missing original index never requests or draws across a skipped stop', async () => {
    let calls = 0;
    const handler = makeHandler(async () => { calls++; return { data: provider('walk', stops[1], stops[2]) }; });
    const noPairs = await invoke(handler, { mode: 'walk', stops: [stops[0], stops[2]] });
    assert.deepEqual(noPairs.body.data.segments, []);
    assert.equal(calls, 0);
    const res = await invoke(handler, { mode: 'walk', stops: [stops[1], stops[2], { index: 4, name: '빈 구간 뒤', lng: 127.104, lat: 36.804 }] });
    assert.deepEqual(res.body.data.segments.map(s => [s.fromIndex, s.toIndex]), [[1, 2]]);
    assert.equal(calls, 1);
});

test('a single valid stop requires no upstream call', async () => {
    const res = await invoke(makeHandler(async () => assert.fail('No pair to request')), { mode: 'walk', stops: [stops[0]] });
    assert.equal(res.body.data.status, 'unavailable');
    assert.deepEqual(res.body.data.segments, []);
});

test('only nearby transit no_route may fall back to a real walking itinerary', async () => {
    const urls = [];
    const res = await invoke(makeHandler(async url => {
        urls.push(url);
        return { data: url.endsWith('publictraffic') ? { status: 'NO_RESULTS' } : provider('walk') };
    }), { mode: 'transit', stops: stops.slice(0, 2) });
    assert.equal(urls.length, 2);
    assert.ok(urls[1].endsWith('/walk'));
    assert.equal(res.body.data.mode, 'transit');
    assert.equal(res.body.data.segments[0].walkingFallback, true);
    assert.equal(res.body.data.segments[0].paths[0].mode, 'walk');
});

test('transit no_route over 1.5km does not substitute walking', async () => {
    let calls = 0;
    const res = await invoke(makeHandler(async () => { calls++; return { data: { status: 'NO_RESULTS' } }; }),
        { mode: 'transit', stops: [stops[0], { ...stops[1], lng: 127.13 }] });
    unavailable(res, 'no_route');
    assert.equal(calls, 1);
});

for (const [label, error, reason] of [
    ['permission', { response: { status: 403, data: { message: 'private upstream detail' } } }, 'permission_denied'],
    ['quota', { response: { status: 429 } }, 'quota_exceeded'],
    ['timeout', { code: 'ECONNABORTED', message: 'private upstream detail' }, 'timeout'],
    ['unavailable', { message: 'private upstream detail', response: { status: 500, data: secret } }, 'upstream_unavailable'],
]) {
    test(`transit ${label} remains unavailable without walking fallback or private provider details`, async () => {
        let calls = 0;
        const res = await invoke(makeHandler(async () => { calls++; throw error; }), { mode: 'transit', stops: stops.slice(0, 2) });
        unavailable(res, reason);
        assert.equal(calls, 1);
    });
}

test('provider quota and permission codes are safe failures even in HTTP 200 responses', async () => {
    for (const [code, reason] of [[-10, 'quota_exceeded'], [-401, 'permission_denied'], [-3, 'permission_denied'], [-5, 'permission_denied']]) {
        unavailable(await invoke(makeHandler(async () => ({ data: { code, msg: 'private upstream detail' } }))), reason);
    }
});

test('no configured key makes zero provider calls', async () => {
    unavailable(await invoke(makeHandler(async () => assert.fail('No configured credential'), { env: {} })), 'not_configured');
});

test('dedicated route credential takes precedence and fallback map credential remains server-side', async () => {
    for (const env of [{ KAKAO_ROUTE_REST_API_KEY: secret, KAKAO_API_KEY: 'other' }, { KAKAO_API_KEY: secret }]) {
        const res = await invoke(makeHandler(async (_url, config) => {
            assert.equal(config.headers.Authorization, `KakaoAK ${secret}`);
            return { data: provider('walk') };
        }, { env }));
        assert.equal(res.body.data.status, 'ready');
        assert.ok(!JSON.stringify(res.body).includes(secret));
    }
});

const malformed = [
    ['nonobject', () => null], ['unknown status', () => ({ status: 'SECRET_STATUS' })],
    ['missing legs', b => { delete b.route.legs; return b; }],
    ['missing leg steps', b => { b.route.legs = [{}]; return b; }],
    ['empty steps', b => { b.route.legs[0].steps = []; return b; }],
    ['single point only', b => { b.route.legs[0].steps = [step([coords(stops[0])])]; return b; }],
    ['nonfinite point', b => { b.route.legs[0].steps[0].path.points[1][0] = NaN; return b; }],
    ['string point', b => { b.route.legs[0].steps[0].path.points[1][0] = '127.101'; return b; }],
    ['swapped coordinates', b => { b.route.legs[0].steps[0].path.points = [[36.8, 127.1], [36.801, 127.101]]; return b; }],
    ['oversize points', b => { b.route.legs[0].steps[0].path.points = Array.from({ length: 12501 }, () => coords(stops[0])); return b; }],
    ['wrong endpoint', b => { b.route.legs[0].steps[0].path.points = [[128.1, 36.8], [128.101, 36.801]]; return b; }],
    ['negative metric', b => { b.route.properties.totalDistance = -1; return b; }],
    ['missing metric', b => { delete b.route.properties.totalTime; return b; }],
];
for (const [label, change] of malformed) {
    test(`malformed upstream ${label} is rejected without a replacement line`, async () => {
        unavailable(await invoke(makeHandler(async () => ({ data: change(provider('walk')) }))), 'invalid_upstream_response');
    });
}

test('malformed transit type and malformed car vertexes cannot become geometry', async () => {
    const transit = provider('transit');
    transit.routes[0].steps[0].properties.type = 'UNKNOWN';
    const car = provider('car');
    car.routes[0].sections[0].roads[0].vertexes = [127.1, 36.8, 127.101];
    for (const [mode, data] of [['transit', transit], ['car', car]]) {
        unavailable(await invoke(makeHandler(async () => ({ data })), { mode, stops: stops.slice(0, 2) }), 'invalid_upstream_response');
    }
});

test('invalid request bodies fail before any external request', async () => {
    const valid = { mode: 'walk', stops: stops.slice(0, 2) };
    const bodies = [null, {}, { ...valid, mode: 'bicycle' }, { ...valid, stops: [] },
        { ...valid, stops: Array.from({ length: 6 }, (_, index) => ({ ...stops[0], index })) },
        { ...valid, stops: [stops[1], stops[0]] }, { ...valid, stops: [stops[0], stops[0]] }];
    for (const value of [{ index: -1 }, { index: 5 }, { index: '0' }, { name: null }, { name: 'x'.repeat(201) },
        { lng: '127.1' }, { lat: null }, { lat: Infinity }, { lng: 0 }, { lat: 40 }]) {
        bodies.push({ ...valid, stops: [{ ...stops[0], ...value }, stops[1]] });
    }
    for (const body of bodies) {
        assert.equal(validRequest(body), false);
        const res = await invoke(makeHandler(async () => assert.fail('Invalid request must not call API')), body);
        assert.equal(res.statusCode, 400);
        assert.equal(res.body.error.reason, 'invalid_request');
    }
});

test('cache separates direction and mode, returns isolated values, and expires at mode TTL', async () => {
    let timestamp = 1000;
    const calls = [];
    const handler = makeHandler(async (url, config) => {
        calls.push(url);
        const mode = url.endsWith('/walk') ? 'walk' : url.endsWith('/publictraffic') ? 'transit' : 'car';
        const reverse = mode === 'car' ? config.params.origin.startsWith('127.101,') : config.params.start_x === stops[1].lng;
        return { data: provider(mode, reverse ? stops[1] : stops[0], reverse ? stops[0] : stops[1]) };
    }, { now: () => timestamp });
    const body = { mode: 'walk', stops: stops.slice(0, 2) };
    const first = await invoke(handler, body);
    first.body.data.segments[0].paths[0].points[0][0] = 0;
    const second = await invoke(handler, body);
    assert.equal(second.body.data.segments[0].paths[0].points[0][0], stops[0].lng);
    assert.equal(calls.length, 1);
    await invoke(handler, { mode: 'walk', stops: [{ ...stops[1], index: 0 }, { ...stops[0], index: 1 }] });
    await invoke(handler, { ...body, mode: 'car' });
    await invoke(handler, { ...body, mode: 'transit' });
    assert.equal(calls.length, 4);
    timestamp += 60000;
    await invoke(handler, { ...body, mode: 'car' });
    await invoke(handler, { ...body, mode: 'transit' });
    await invoke(handler, body);
    assert.equal(calls.length, 6);
    timestamp = 301000;
    await invoke(handler, body);
    assert.equal(calls.length, 7);
});

test('failed routes are retried instead of cached', async () => {
    let calls = 0;
    const handler = makeHandler(async () => ({ data: ++calls === 1 ? { status: 'NO_RESULTS' } : provider('walk') }));
    unavailable(await invoke(handler), 'no_route');
    assert.equal((await invoke(handler)).body.data.status, 'ready');
    assert.equal(calls, 2);
});

for (const event of ['request aborted', 'response closed']) {
    test(`${event} aborts upstream, suppresses response and cleans lifetime listeners`, async () => {
        let signal;
        const handler = makeHandler(async (_url, config) => {
            signal = config.signal;
            return await new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject({ code: 'ERR_CANCELED' }), { once: true }));
        });
        const run = start(handler);
        assert.equal(signal.aborted, false);
        if (event === 'request aborted') run.req.emit('aborted');
        else { run.res.destroyed = true; run.res.emit('close'); }
        await run.done;
        assert.equal(signal.aborted, true);
        assert.equal(run.res.body, undefined);
        assert.equal(run.req.listenerCount('aborted'), 0);
        assert.equal(run.res.listenerCount('close'), 0);
    });
}

test('whole-course deadline aborts every pending segment and emits only safe timeout results', async t => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const signals = [];
    const run = start(makeHandler(async (_url, config) => {
        signals.push(config.signal);
        return await new Promise((_resolve, reject) => config.signal.addEventListener('abort', () => reject({ code: 'ERR_CANCELED', message: secret }), { once: true }));
    }), { mode: 'walk', stops });
    assert.equal(signals.length, 2);
    t.mock.timers.tick(9999);
    assert.equal(signals[0].aborted, false);
    t.mock.timers.tick(1);
    await run.done;
    assert.ok(signals.every(signal => signal.aborted));
    assert.equal(run.res.body.data.status, 'unavailable');
    assert.ok(run.res.body.data.segments.every(segment => segment.reason === 'timeout' && segment.paths.length === 0));
    assert.ok(!JSON.stringify(run.res.body).includes(secret));
    assert.equal(run.req.listenerCount('aborted'), 0);
    assert.equal(run.res.listenerCount('close'), 0);
});

test('a malformed faster transit alternative cannot discard the next valid itinerary', async () => {
    for (const corrupt of [
        route => { route.steps = []; },
        route => { route.steps[0].path.points = [[128.1, 36.8], [128.101, 36.801]]; },
        route => { route.properties.totalDistance = -1; },
        route => { route.steps[0].properties.type = 'UNKNOWN'; },
    ]) {
        const body = provider('transit');
        const faster = structuredClone(body.routes[0]);
        faster.properties.totalTime = 1;
        corrupt(faster);
        body.routes.unshift(faster);
        let calls = 0;
        const res = await invoke(makeHandler(async () => { calls++; return { data: body }; }),
            { mode: 'transit', stops: stops.slice(0, 2) });
        assert.equal(res.body.data.status, 'ready');
        assert.equal(res.body.data.durationSeconds, 130);
        assert.equal(res.body.data.distanceMeters, 170);
        assert.equal(calls, 1);
    }
});

test('five ordered stops request exactly four adjacent routes and sum only provider metrics', async () => {
    const five = Array.from({ length: 5 }, (_, index) => ({ index, name: `장소 ${index + 1}`,
        lng: 127.1 + index * 0.001, lat: 36.8 + index * 0.001 }));
    const pairs = [];
    const res = await invoke(makeHandler(async (_url, config) => {
        const from = five.find(stop => stop.lng === config.params.start_x);
        const to = five.find(stop => stop.lng === config.params.end_x);
        pairs.push([from.index, to.index]);
        return { data: provider('walk', from, to) };
    }), { mode: 'walk', stops: five });
    assert.deepEqual(pairs, [[0, 1], [1, 2], [2, 3], [3, 4]]);
    assert.equal(res.body.data.status, 'ready');
    assert.equal(res.body.data.distanceMeters, 680);
    assert.equal(res.body.data.durationSeconds, 520);
    assert.equal(res.body.data.segments.length, 4);
});

const accessStops = [stops[0], { ...stops[1], lng: 127.13 }];
function transitWithAccess(transfer = false) {
    const body = provider('transit', ...accessStops);
    body.routes[0].steps = transfer ? [
        step([[127.1045, 36.8], [127.112, 36.8004]], 'BUS'),
        step([[127.1135, 36.8004], [127.127, 36.801]], 'SUBWAY'),
    ] : [step([[127.1045, 36.8], [127.127, 36.801]], 'BUS')];
    return body;
}
function realWalkReply(params) {
    const from = { lng: params.start_x, lat: params.start_y };
    const to = { lng: params.end_x, lat: params.end_y };
    const points = [coords(from), [(from.lng + to.lng) / 2, (from.lat + to.lat) / 2 + 0.0002], coords(to)];
    const data = provider('walk', from, to);
    data.route.legs[0].steps = [step(points)];
    return { data, points };
}
for (const transfer of [false, true]) {
    test(`transit retrieves real curved walking geometry for venue access${transfer ? ' and a missing transfer' : ''}`, async () => {
        let transitCalls = 0;
        const walkReplies = [];
        const body = transitWithAccess(transfer);
        const res = await invoke(makeHandler(async (url, config) => {
            if (url.endsWith('/publictraffic')) { transitCalls++; return { data: body }; }
            assert.ok(url.endsWith('/walk'));
            assert.equal(config.params.input_coord, 'WGS84');
            assert.equal(config.params.output_coord, 'WGS84');
            assert.equal(config.headers.Authorization, `KakaoAK ${secret}`);
            const reply = realWalkReply(config.params);
            walkReplies.push(reply);
            return { data: reply.data };
        }), { mode: 'transit', stops: accessStops });
        assert.equal(transitCalls, 1);
        assert.equal(walkReplies.length, transfer ? 3 : 2);
        assert.equal(res.body.data.status, 'ready');
        const paths = res.body.data.segments[0].paths;
        const expected = transfer ? [
            { mode: 'walk', points: walkReplies[0].points },
            { mode: 'transit', points: body.routes[0].steps[0].path.points },
            { mode: 'walk', points: walkReplies[1].points },
            { mode: 'transit', points: body.routes[0].steps[1].path.points },
            { mode: 'walk', points: walkReplies[2].points },
        ] : [
            { mode: 'walk', points: walkReplies[0].points },
            { mode: 'transit', points: body.routes[0].steps[0].path.points },
            { mode: 'walk', points: walkReplies[1].points },
        ];
        assert.deepEqual(paths, expected);
        assert.deepEqual(paths[0].points[0], coords(accessStops[0]));
        assert.deepEqual(paths.at(-1).points.at(-1), coords(accessStops[1]));
        assert.ok(paths.filter(path => path.mode === 'walk').every(path => path.points.length === 3));
    });
}

for (const [label, response, reason] of [
    ['no route', { data: { status: 'NO_RESULTS' } }, 'no_route'],
    ['permission', { error: { response: { status: 403, data: secret } } }, 'permission_denied'],
    ['timeout', { error: { code: 'ETIMEDOUT', message: 'private upstream detail' } }, 'timeout'],
]) {
    test(`failed transit access ${label} leaves the whole long leg unavailable without a line`, async () => {
        let transitCalls = 0, walkCalls = 0;
        const res = await invoke(makeHandler(async url => {
            if (url.endsWith('/publictraffic')) { transitCalls++; return { data: transitWithAccess() }; }
            walkCalls++;
            if (response.error) throw response.error;
            return response;
        }), { mode: 'transit', stops: accessStops });
        unavailable(res, reason);
        assert.equal(transitCalls, 1);
        assert.equal(walkCalls, 2);
    });
}

test('failed access waits for all sibling walking requests to settle before responding', async () => {
    let resolveSecond, walks = 0;
    const run = start(makeHandler(async (url, config) => {
        if (url.endsWith('/publictraffic')) return { data: transitWithAccess() };
        if (++walks === 1) throw { response: { status: 403 } };
        return await new Promise(resolve => { resolveSecond = () => resolve({ data: realWalkReply(config.params).data }); });
    }), { mode: 'transit', stops: accessStops });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(walks, 2);
    assert.equal(run.res.body, undefined);
    resolveSecond();
    await run.done;
    unavailable(run.res, 'permission_denied');
    assert.equal(run.req.listenerCount('aborted'), 0);
    assert.equal(run.res.listenerCount('close'), 0);
});

test('a transit transfer over 1.5km is rejected before access requests and never bridged', async () => {
    const body = transitWithAccess(true);
    body.routes[0].steps[0].path.points = [coords(accessStops[0]), [127.108, 36.8]];
    body.routes[0].steps[1].path.points = [[127.126, 36.8], coords(accessStops[1])];
    let calls = 0;
    const res = await invoke(makeHandler(async url => {
        calls++;
        assert.ok(url.endsWith('/publictraffic'));
        return { data: body };
    }), { mode: 'transit', stops: accessStops });
    unavailable(res, 'invalid_upstream_response');
    assert.equal(calls, 1);
});

test('official walking path endpoints near the places remain unmodified', async () => {
    const body = provider('walk');
    const points = [[127.1003, 36.8], [127.1005, 36.8004], [127.1008, 36.801]];
    body.route.legs[0].steps[0].path.points = structuredClone(points);
    const res = await invoke(makeHandler(async () => ({ data: body })));
    assert.equal(res.body.data.status, 'ready');
    assert.deepEqual(res.body.data.segments[0].paths[0].points, points);
    assert.deepEqual(body.route.legs[0].steps[0].path.points, points);
});

test('walking geometry with an endpoint more than 300m from a place is rejected', async () => {
    for (const [index, point] of [[0, [127.104, 36.8]], [1, [127.105, 36.801]]]) {
        const body = provider('walk');
        body.route.legs[0].steps[0].path.points[index] = point;
        unavailable(await invoke(makeHandler(async () => ({ data: body }))), 'invalid_upstream_response');
    }
});

test('a park center 106m from the official walking endpoint accepts the original provider geometry', async () => {
    const parkStops = [stops[0], { ...stops[1], lng: 127.105, lat: 36.805 }];
    // A latitude difference of 0.0009535 degrees is approximately 106m here.
    // Parks may use their center as the place coordinate while routes use an entrance.
    const points = [[127.1, 36.8009535], [127.102, 36.803], coords(parkStops[1])];
    const body = provider('walk', ...parkStops);
    body.route.legs[0].steps[0].path.points = structuredClone(points);
    let calls = 0;
    const res = await invoke(makeHandler(async (url, config) => {
        calls++;
        assert.ok(url.endsWith('/v2/routing/walk'));
        assert.equal(config.params.start_x, parkStops[0].lng);
        assert.equal(config.params.start_y, parkStops[0].lat);
        return { data: body };
    }), { mode: 'walk', stops: parkStops });
    assert.equal(calls, 1);
    assert.equal(res.body.data.status, 'ready');
    assert.deepEqual(res.body.data.segments[0].paths, [{ mode: 'walk', points }]);
    assert.deepEqual(body.route.legs[0].steps[0].path.points, points);
    assert.notDeepEqual(res.body.data.segments[0].paths[0].points[0], coords(parkStops[0]));
});

test('object or array route modes cannot coerce into a valid provider mode', async () => {
    for (const mode of [{}, [], ['walk'], { toString: 'walk' }]) {
        const res = await invoke(makeHandler(async () => assert.fail('Invalid mode must not call API')),
            { mode, stops: stops.slice(0, 2) });
        assert.equal(res.statusCode, 400);
        assert.equal(res.body.error.reason, 'invalid_request');
    }
});
