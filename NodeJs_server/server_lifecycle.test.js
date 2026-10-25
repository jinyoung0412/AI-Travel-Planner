const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { once } = require('node:events');
const axios = require('axios');
const { createApp } = require('./server');
const { KAKAO_TIMEOUT_MS } = require('./kakao_place');

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const mapPath = '/kakao/place?' + new URLSearchParams({ name: '아지트',
    address: '충남 천안시 테스트로 1', lat: '36.8151', lng: '127.1139' });
const place = { id: '1', place_name: '아지트', place_url: 'http://place.map.kakao.com/1',
    road_address_name: '충남 천안시 테스트로 1', x: '127.1139', y: '36.8151' };

function deferred() {
    let resolve;
    const promise = new Promise(r => { resolve = r; });
    return { promise, resolve };
}

// Every endpoint is ephemeral literal loopback. The map wrapper replaces only
// the fixed provider URL; the HTTP, Axios adapter, body reading and aborts are real.
async function fixture(t, handler, timeout = 80) {
    let sequence = 0;
    const calls = [], responses = [], upstreamResponses = [];
    const server = http.createServer((req, res) => {
        upstreamResponses.push(res);
        req.resume();
        handler(req, res, ++sequence);
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const upstreamBase = `http://127.0.0.1:${server.address().port}`;
    const app = createApp({ env: { FLASK_BASE_URL: upstreamBase,
        FLASK_TIMEOUT_MS: String(timeout), KAKAO_API_KEY: 'test-only-map-key' },
    httpClient: {
        post(url, body, config) {
            calls.push(config);
            return axios.post(url, body, config);
        },
        get(url, config) {
            assert.equal(url, 'https://dapi.kakao.com/v2/local/search/keyword.json');
            calls.push(config);
            return axios.get(`${upstreamBase}/map`, config);
        },
    } });
    const gateway = http.createServer((req, res) => {
        const audit = { req, res, writesAfterClose: 0, ends: 0, requestClosed: false,
            closed: deferred(), initialAbortedListeners: req.listenerCount('aborted'),
            initialCloseListeners: res.listenerCount('close') };
        req.on('close', () => { audit.requestClosed = true; });
        res.on('close', audit.closed.resolve);
        const end = res.end;
        res.end = function(...args) {
            audit.ends++;
            if (res.destroyed) audit.writesAfterClose++;
            return end.apply(this, args);
        };
        responses.push(audit);
        app(req, res);
    });
    gateway.listen(0, '127.0.0.1');
    await once(gateway, 'listening');
    t.after(async () => {
        for (const s of [gateway, server]) {
            s.closeAllConnections();
            await new Promise(resolve => s.close(resolve));
        }
    });
    const base = `http://127.0.0.1:${gateway.address().port}`;
    function start(path = '/recommend/spot') {
        const done = deferred();
        const req = http.request(base + path, { method: path === mapPath ? 'GET' : 'POST',
            headers: { 'content-type': 'application/json' } }, res => {
            const parts = [];
            res.on('data', part => parts.push(part));
            res.on('end', () => done.resolve({ status: res.statusCode,
                body: JSON.parse(Buffer.concat(parts).toString()) }));
        });
        req.on('error', error => done.resolve({ error: error.code }));
        req.end(path === mapPath ? undefined : '{}');
        return { req, done: done.promise };
    }
    return { calls, responses, upstreamResponses, start, request: path => start(path).done };
}

function finish(res, body, status = 200) {
    res.writeHead(status, { 'content-type': 'application/json' });
    res.end(JSON.stringify(body));
}

function assertClean(audit) {
    assert.equal(audit.req.listenerCount('aborted'), audit.initialAbortedListeners);
    // The extra close listener is the fixture's own observation above.
    assert.equal(audit.res.listenerCount('close'), audit.initialCloseListeners + 1);
    assert.equal(audit.writesAfterClose, 0);
}

for (const [path, field] of [['/recommend/spot', 'places'], ['/recommend/course', 'courses'],
    ['/suggest/tags', 'tags']]) {
    test(`API-02: ${path} full-body deadline aborts a live trickle and recovers`, async t => {
        const closed = deferred();
        let completed = false;
        const f = await fixture(t, (req, res, number) => {
            if (number > 1) return finish(res, { [field]: [] });
            res.setHeader('content-type', 'application/json');
            res.write(`{"${field}":[`);
            let ticks = 0;
            const timer = setInterval(() => {
                if (++ticks === 25) { completed = true; clearInterval(timer); res.end(']}'); }
                else res.write(' ');
            }, 15);
            res.on('close', () => { clearInterval(timer); closed.resolve(); });
        });
        const result = await f.request(path);
        assert.equal(result.status, 504);
        assert.equal(result.body.error.reason, 'upstream_timeout');
        assert.equal(f.calls[0].signal.aborted, true);
        await closed.promise;
        assert.equal(completed, false);
        assertClean(f.responses[0]);
        assert.equal((await f.request(path)).status, 200);
        assertClean(f.responses[1]);
    });
}

for (const mode of ['no_headers', 'headers_then_stalled_body']) {
    test(`API-02: ${mode} returns safe 504 and closes upstream`, async t => {
        const closed = deferred();
        const f = await fixture(t, (req, res) => {
            if (mode === 'headers_then_stalled_body') {
                res.writeHead(200, { 'content-type': 'application/json' });
                res.write('{"places":');
            }
            res.on('close', closed.resolve);
        });
        const result = await f.request();
        assert.equal(result.status, 504);
        assert.equal(result.body.error.reason, 'upstream_timeout');
        await closed.promise;
        assertClean(f.responses[0]);
    });
}

test('API-03: a normal POST request close does not abort a pending response; cleanup cancels timer', async t => {
    const received = deferred(), release = deferred();
    const f = await fixture(t, async (req, res) => {
        received.resolve();
        await release.promise;
        finish(res, { places: [] });
    }, 180);
    const request = f.start();
    await received.promise;
    await pause(20);
    assert.equal(f.responses[0].requestClosed, true);
    assert.equal(f.calls[0].signal.aborted, false);
    release.resolve();
    assert.equal((await request.done).status, 200);
    assertClean(f.responses[0]);
    await pause(200);
    assert.equal(f.calls[0].signal.aborted, false);
});

test('upstream service failure preserves its contract and disposes its lifetime', async t => {
    const f = await fixture(t, (req, res) => finish(res,
        { error: '일시적 서비스 실패', reason: 'tags_unavailable', tags: [] }, 503));
    const result = await f.request('/suggest/tags');
    assert.equal(result.status, 503);
    assert.equal(result.body.error.reason, 'tags_unavailable');
    assertClean(f.responses[0]);
    await pause(100);
    assert.equal(f.calls[0].signal.aborted, false);
});

for (const path of ['/recommend/spot', mapPath]) {
    test(`API-03: disconnect aborts live ${path === mapPath ? 'map GET' : 'POST'} without writing an error`, async t => {
        const received = deferred(), closed = deferred();
        const f = await fixture(t, (req, res, number) => {
            if (number > 1) return finish(res, path === mapPath ? { documents: [place] } : { places: [] });
            res.on('close', closed.resolve);
            received.resolve();
        }, 500);
        const request = f.start(path);
        await received.promise;
        assert.equal(f.calls[0].signal.aborted, false);
        request.req.destroy();
        await f.responses[0].closed.promise;
        await closed.promise;
        assert.equal(f.calls[0].signal.aborted, true);
        assert.equal(f.responses[0].ends, 0);
        assertClean(f.responses[0]);
        const next = await f.request(path);
        assert.equal(next.status, 200);
        if (path === mapPath) assert.equal(next.body.place_url, 'https://place.map.kakao.com/1');
        assertClean(f.responses[1]);
    });
}

test('normal map lookup preserves URL identity and clears deadline/listeners', async t => {
    const f = await fixture(t, (req, res) => finish(res, { documents: [place] }));
    const result = await f.request(mapPath);
    assert.equal(result.status, 200);
    assert.equal(result.body.place_url, 'https://place.map.kakao.com/1');
    assert.equal(result.body.kakao_place_id, '1');
    assert.equal(f.calls[0].timeout, KAKAO_TIMEOUT_MS);
    assert.equal(f.calls[0].signal.aborted, false);
    assertClean(f.responses[0]);
});

test('map GET hard deadline covers a live trickling provider body', { timeout: 14000 }, async t => {
    const closed = deferred();
    let completed = false;
    const f = await fixture(t, (req, res) => {
        res.setHeader('content-type', 'application/json');
        res.write('{"documents":[');
        let ticks = 0;
        const timer = setInterval(() => {
            if (++ticks === 480) { completed = true; clearInterval(timer); res.end(']}'); }
            else res.write(' ');
        }, 25);
        res.on('close', () => { clearInterval(timer); closed.resolve(); });
    });
    const result = await f.request(mapPath);
    assert.equal(result.status, 504);
    assert.equal(result.body.reason, 'upstream_timeout');
    await closed.promise;
    assert.equal(completed, false);
    assert.equal(f.calls[0].signal.aborted, true);
    assertClean(f.responses[0]);
});

test('deadline/disconnect races close upstream once, dispose listeners and allow retry', async t => {
    for (const offset of [-5, 5]) {
        const received = deferred(), closed = deferred();
        const f = await fixture(t, (req, res, number) => {
            if (number > 1) return finish(res, { places: [] });
            res.on('close', closed.resolve);
            received.resolve();
        }, 50);
        const request = f.start();
        await received.promise;
        const timer = setTimeout(() => request.req.destroy(), 50 + offset);
        t.after(() => clearTimeout(timer));
        const result = await request.done;
        if (!result.error) {
            assert.equal(result.status, 504);
            assert.equal(result.body.error.reason, 'upstream_timeout');
        } else assert.equal(result.error, 'ECONNRESET');
        await closed.promise;
        await f.responses[0].closed.promise;
        assert.equal(f.calls[0].signal.aborted, true);
        assert.ok(f.responses[0].ends <= 1);
        assertClean(f.responses[0]);
        assert.equal((await f.request()).status, 200);
    }
});
