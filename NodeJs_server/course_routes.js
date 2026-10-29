const { upstreamRequest } = require('./upstream_request');

const ENDPOINTS = Object.freeze({
    walk: 'https://dapi.kakao.com/v2/routing/walk',
    transit: 'https://dapi.kakao.com/v2/routing/publictraffic',
    car: 'https://apis-navi.kakaomobility.com/v1/directions',
});
const MAX_POINTS = 50000;
const MAX_SEGMENT_POINTS = MAX_POINTS / 4;
const NO_ROUTE = new Set(['SAME_POINT', 'START_LINK_NOT_FOUND', 'END_LINK_NOT_FOUND',
    'TOO_MANY_SEARCH_LINK', 'TOO_FAR_AWAY', 'ROUTE_RESULT_NOT_FOUND',
    'STARTNODES_NULL', 'ENDNODES_NULL', 'EQUAL_POINTS', 'NO_RESULTS']);

function coordinate(lng, lat) {
    return typeof lng === 'number' && Number.isFinite(lng) && lng >= 124 && lng <= 132 &&
        typeof lat === 'number' && Number.isFinite(lat) && lat >= 33 && lat <= 39.5;
}

function validRequest(body) {
    if (!body || typeof body.mode !== 'string' || !Object.hasOwn(ENDPOINTS, body.mode) || !Array.isArray(body.stops) ||
        body.stops.length < 1 || body.stops.length > 5) return false;
    let previous = -1;
    return body.stops.every(stop => {
        if (!stop || !Number.isInteger(stop.index) || stop.index < 0 || stop.index > 4 ||
            stop.index <= previous || typeof stop.name !== 'string' || stop.name.length > 200 ||
            !coordinate(stop.lng, stop.lat)) return false;
        previous = stop.index;
        return true;
    });
}

function failure(reason) {
    const error = new Error('Route unavailable');
    error.reason = reason;
    return error;
}

function metric(value, max) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > max) {
        throw failure('invalid_upstream_response');
    }
    return Math.round(value);
}

function meters(a, b) {
    const radians = Math.PI / 180;
    const dy = (b[1] - a[1]) * radians, dx = (b[0] - a[0]) * radians;
    const h = Math.sin(dy / 2) ** 2 + Math.cos(a[1] * radians) * Math.cos(b[1] * radians) * Math.sin(dx / 2) ** 2;
    return 12742000 * Math.asin(Math.min(1, Math.sqrt(h)));
}

function pathsFromSteps(steps, requestedMode) {
    if (!Array.isArray(steps) || !steps.length || steps.length > 2000) {
        throw failure('invalid_upstream_response');
    }
    const paths = [];
    let pointCount = 0;
    for (const step of steps) {
        const points = step?.path?.points;
        const type = step?.properties?.type;
        const mode = requestedMode === 'transit' ? type === 'WALKING' ? 'walk' :
            ['BUS', 'SUBWAY'].includes(type) ? 'transit' : null : requestedMode;
        if (!mode || !Array.isArray(points) || !points.length ||
            (pointCount += points.length) > MAX_SEGMENT_POINTS ||
            !points.every(p => Array.isArray(p) && p.length === 2 && coordinate(p[0], p[1]))) {
            throw failure('invalid_upstream_response');
        }
        // Preserve separate provider paths at real gaps; never bridge missing geometry.
        const cleaned = points.filter((p, index) => index === 0 || p[0] !== points[index - 1][0] || p[1] !== points[index - 1][1]);
        if (cleaned.length < 2) continue;
        const previous = paths.at(-1);
        if (previous?.mode === mode && meters(previous.points.at(-1), cleaned[0]) < 0.2) {
            previous.points.push(...cleaned.slice(1));
        } else {
            paths.push({ mode, points: cleaned.map(p => [...p]) });
        }
    }
    if (!paths.length) throw failure('invalid_upstream_response');
    return paths;
}

function normalize(body, mode, from, to) {
    if (!body || typeof body !== 'object' || Array.isArray(body)) throw failure('invalid_upstream_response');
    if (body.code === -10) throw failure('quota_exceeded');
    if ([-401, -3, -5].includes(body.code)) throw failure('permission_denied');
    const finish = (paths, distanceMeters, durationSeconds) => {
        if (paths.length > 100) throw failure('invalid_upstream_response');
        // Parks and large venues are often stored at their center while the
        // provider returns the reachable entrance. Keep that real endpoint.
        const endpointLimit = mode === 'walk' ? 300 : 1000;
        if (meters([from.lng, from.lat], paths[0].points[0]) > endpointLimit ||
            meters([to.lng, to.lat], paths.at(-1).points.at(-1)) > endpointLimit) throw failure('invalid_upstream_response');
        return { paths, distanceMeters, durationSeconds };
    };
    let paths, distanceMeters, durationSeconds;
    if (mode === 'car') {
        if (!Array.isArray(body.routes) || !body.routes.length) throw failure('invalid_upstream_response');
        const route = body.routes.find(r => r?.result_code === 0);
        if (!route) throw failure('no_route');
        if (!Array.isArray(route.sections) || !route.sections.length || route.sections.length > 8) {
            throw failure('invalid_upstream_response');
        }
        const steps = route.sections.flatMap(section => {
            if (!Array.isArray(section?.roads) || section.roads.length > 2000) throw failure('invalid_upstream_response');
            return section.roads.map(road => {
                const v = road?.vertexes;
                if (!Array.isArray(v) || v.length % 2 || v.length < 2 || v.length > MAX_SEGMENT_POINTS * 2) {
                    throw failure('invalid_upstream_response');
                }
                const points = [];
                for (let i = 0; i < v.length; i += 2) points.push([v[i], v[i + 1]]);
                return { path: { points } };
            });
        });
        paths = pathsFromSteps(steps, mode);
        distanceMeters = metric(route.summary?.distance, 500000);
        durationSeconds = metric(route.summary?.duration, 604800);
    } else {
        if (body.status !== 'OK') throw failure(NO_ROUTE.has(body.status) ? 'no_route' : 'invalid_upstream_response');
        let route, steps;
        if (mode === 'walk') {
            route = body.route;
            if (!Array.isArray(route?.legs) || !route.legs.length || route.legs.length > 8 ||
                route.legs.some(leg => !Array.isArray(leg?.steps))) throw failure('invalid_upstream_response');
            steps = route.legs.flatMap(leg => leg.steps);
        } else {
            if (!Array.isArray(body.routes) || !body.routes.length || body.routes.length > 64) throw failure('invalid_upstream_response');
            // The API can return several alternatives. Display the quickest valid itinerary.
            const alternatives = [...body.routes].sort((a, b) => (a?.properties?.totalTime ?? Infinity) -
                (b?.properties?.totalTime ?? Infinity));
            for (const candidate of alternatives) {
                try {
                    return finish(pathsFromSteps(candidate?.steps, mode),
                        metric(candidate?.properties?.totalDistance, 500000),
                        metric(candidate?.properties?.totalTime, 604800));
                } catch (_) {
                    // A malformed alternative cannot discard a later valid route.
                }
            }
            throw failure('invalid_upstream_response');
        }
        paths = pathsFromSteps(steps, mode);
        distanceMeters = metric(route?.properties?.totalDistance, 500000);
        durationSeconds = metric(route?.properties?.totalTime, 604800);
    }
    return finish(paths, distanceMeters, durationSeconds);
}

function createCourseRouteHandler({ httpClient, env, now = Date.now }) {
    // Short, bounded in-memory cache only; traffic-sensitive results expire sooner.
    const cache = new Map();
    const timeout = 10000;
    const getKey = () => (env.KAKAO_ROUTE_REST_API_KEY || env.KAKAO_API_KEY || '').trim();

    async function fetchSegment(mode, from, to, signal) {
        const key = getKey();
        if (!key) throw failure('not_configured');
        const params = mode === 'car' ? {
            origin: `${from.lng},${from.lat}`, destination: `${to.lng},${to.lat}`,
            summary: false, alternatives: false,
        } : {
            start_x: from.lng, start_y: from.lat, end_x: to.lng, end_y: to.lat,
            input_coord: 'WGS84', output_coord: 'WGS84',
        };
        try {
            const result = await httpClient.get(ENDPOINTS[mode], {
                params, headers: { Authorization: `KakaoAK ${key}` },
                signal, timeout: 6000, maxRedirects: 0, maxContentLength: 4 * 1024 * 1024,
            });
            if (signal.aborted) throw failure('timeout');
            const route = normalize(result.data, mode, from, to);
            return mode === 'transit' ? await completeTransit(route, from, to, signal) : route;
        } catch (error) {
            if (error.reason) throw error;
            const status = error.response?.status;
            const code = error.response?.data?.code;
            throw failure(status === 429 || code === -10 ? 'quota_exceeded' :
                [401, 403].includes(status) ? 'permission_denied' :
                    signal.aborted || ['ETIMEDOUT', 'ECONNABORTED', 'ERR_CANCELED'].includes(error.code) ? 'timeout' : 'upstream_unavailable');
        }
    }

    async function completeTransit(route, from, to, signal) {
        // Some transit itineraries supply the vehicle shape without walking
        // access/transfer geometry. Fetch those real paths instead of drawing
        // a straight connector between a venue and a distant bus stop.
        const tasks = [], insertions = [];
        const endpoint = p => ({ lng: p[0], lat: p[1] });
        const connect = (a, b, at) => {
            const gap = meters([a.lng, a.lat], [b.lng, b.lat]);
            if (gap <= 10) return;
            if (gap > 1500 || tasks.length >= 6) throw failure('invalid_upstream_response');
            insertions.push(at);
            tasks.push(() => fetchSegment('walk', a, b, signal));
        };
        let previous = from;
        for (let i = 0; i < route.paths.length; i++) {
            connect(previous, endpoint(route.paths[i].points[0]), i);
            previous = endpoint(route.paths[i].points.at(-1));
        }
        connect(previous, to, route.paths.length);
        const settled = await Promise.allSettled(tasks.map(run => run()));
        const failed = settled.find(value => value.status === 'rejected');
        if (failed) throw failed.reason;
        const access = settled.map(value => value.value);
        const byIndex = new Map(insertions.map((at, i) => [at, access[i].paths]));
        const paths = route.paths.flatMap((path, i) => [...(byIndex.get(i) || []), path]);
        paths.push(...(byIndex.get(route.paths.length) || []));
        if (paths.length > 100 || paths.reduce((sum, p) => sum + p.points.length, 0) > MAX_SEGMENT_POINTS) {
            throw failure('invalid_upstream_response');
        }
        return { ...route, paths };
    }

    async function segment(mode, from, to, signal) {
        const cacheKey = `${mode}:${from.lng},${from.lat}:${to.lng},${to.lat}`;
        const stored = cache.get(cacheKey);
        if (stored?.expires > now()) {
            cache.delete(cacheKey);
            cache.set(cacheKey, stored);
            return structuredClone(stored.value);
        }
        cache.delete(cacheKey);
        let value;
        try {
            value = await fetchSegment(mode, from, to, signal);
        } catch (error) {
            // Public transit includes short walking connections. Only a genuine
            // no-route result may use a real walking route; never hide API faults.
            if (mode !== 'transit' || error.reason !== 'no_route' ||
                meters([from.lng, from.lat], [to.lng, to.lat]) > 1500 || signal.aborted) throw error;
            value = { ...await fetchSegment('walk', from, to, signal), walkingFallback: true };
        }
        if (signal.aborted) throw failure('timeout');
        cache.set(cacheKey, { expires: now() + (mode === 'walk' ? 300000 : 60000), value: structuredClone(value) });
        while (cache.size > 128) cache.delete(cache.keys().next().value);
        return value;
    }

    return async (req, res) => {
        if (!validRequest(req.body)) return res.status(400).json({ success: false,
            error: { error: '길찾기 조건을 확인해주세요.', reason: 'invalid_request' } });
        const { mode, stops } = req.body;
        const upstream = upstreamRequest(req, res, timeout);
        try {
            const pairs = stops.slice(1).map((to, i) => [stops[i], to]).filter(([from, to]) => to.index === from.index + 1);
            const segments = await Promise.all(pairs.map(async ([from, to]) => {
                const identity = { fromIndex: from.index, toIndex: to.index };
                try {
                    return { ...identity, status: 'ready', ...await segment(mode, from, to, upstream.signal) };
                } catch (error) {
                    return { ...identity, status: 'unavailable', reason: upstream.timedOut ? 'timeout' : error.reason || 'upstream_unavailable', paths: [] };
                }
            }));
            if (!upstream.canRespond()) return;
            const ready = segments.filter(s => s.status === 'ready');
            const data = { mode, status: ready.length && ready.length === segments.length ? 'ready' : ready.length ? 'partial' : 'unavailable', segments };
            if (ready.length && ready.length === segments.length) {
                data.distanceMeters = ready.reduce((sum, s) => sum + s.distanceMeters, 0);
                data.durationSeconds = ready.reduce((sum, s) => sum + s.durationSeconds, 0);
            }
            return res.json({ success: true, data });
        } finally {
            upstream.dispose();
        }
    };
}

module.exports = { createCourseRouteHandler, normalize, validRequest };
