"""Connect production Flask and Node over loopback only, with all keys disabled."""
import hashlib
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import threading
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'Flask_server/places.db'
sys.path.insert(0, str(ROOT))
from scripts.offline_environment import install, allow_gateway_loopback
install()


def forbidden(*args, **kwargs):
    raise AssertionError('External HTTP/model calls are forbidden during gateway smoke')


def main():
    allow_gateway_loopback()
    for key in ('ANTHROPIC_API_KEY', 'KAKAO_API_KEY', 'NAVER_API_ID', 'NAVER_API_SECRET'):
        os.environ[key] = ''
    os.environ['PLACES_DB_PATH'] = str(DB)
    sys.path[:0] = [str(ROOT), str(ROOT / 'Flask_server')]
    import app
    import httpx
    import requests
    from werkzeug.serving import make_server

    app._call_claude = forbidden
    httpx.Client.send = forbidden
    requests.sessions.Session.request = forbidden
    before = hashlib.sha256(DB.read_bytes()).hexdigest()
    flask = make_server('127.0.0.1', 0, app.app)
    thread = threading.Thread(target=flask.serve_forever, daemon=True)
    thread.start()
    gateway = None
    try:
        # Use real Axios for the production forwarding path, with an exact
        # loopback allowlist so this smoke cannot call a map or external host.
        node_source = '''
const {createApp} = require('./NodeJs_server/server');
const {createRequire} = require('node:module');
const axios = createRequire(require('node:path').resolve('NodeJs_server/server.js'))('axios');
const base = process.argv[1];
const httpClient = {
  post(url, ...args) {
    if (!url.startsWith(base + '/')) throw new Error('External HTTP forbidden');
    return axios.post(url, ...args);
  },
  get() { throw new Error('External HTTP forbidden'); }
};
const server = createApp({httpClient, env:{FLASK_BASE_URL:base, KAKAO_API_KEY:''}})
  .listen(0, '127.0.0.1', () => console.log(JSON.stringify({port:server.address().port})));
'''
        env = os.environ.copy()
        for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
            env.pop(key, None)
        env['NO_PROXY'] = '127.0.0.1,localhost'
        gateway = subprocess.Popen(['node', '-e', node_source, f'http://127.0.0.1:{flask.server_port}'],
                                   cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with selectors.DefaultSelector() as selector:
            selector.register(gateway.stdout, selectors.EVENT_READ)
            if not selector.select(10):
                raise RuntimeError('Gateway did not become ready')
            port = json.loads(gateway.stdout.readline())['port']
        opener = build_opener(ProxyHandler({}))

        def request(path, body=None):
            data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
            req = Request(f'http://127.0.0.1:{port}{path}', data=data,
                          headers={'Content-Type': 'application/json'})
            try:
                response = opener.open(req, timeout=15)
            except HTTPError as error:
                response = error
            with response:
                return response.status, json.load(response)

        payload = {'user_lat': 36.8151, 'user_lng': 127.1139, 'region': '천안',
                   'transport': '대중교통', 'persona_tags': ['조용한'], 'count': 5,
                   'spot_count': 3, 'slot_types': ['음식', '자연·산책', '카페'], 'seed': 42}
        status, envelope = request('/recommend/course', payload)
        assert status == 200 and envelope['success'] is True
        data = envelope['data']
        assert len(data['courses']) == 5
        assert data['metadata']['constraints_relaxed'] == []
        assert data['metadata']['preference_evidence'] == 'unavailable'
        for course in data['courses']:
            assert len(course) == len({p['place_id'] for p in course}) == 3
            assert all(app.category_matches(p['category'], app.SLOT_CATEGORY_MAP[slot])
                       for p, slot in zip(course, payload['slot_types']))
        assert all(m['travel_time_minutes'] is None for m in data['course_metrics'])
        assert request('/recommend/course', payload)[1]['data']['courses'] == data['courses']
        status, spot = request('/recommend/spot', {**payload, 'user_text': '닭갈비'})
        assert status == 200 and len(spot['data']['places']) == 5
        assert all(app.category_matches(p['category'], ['닭갈비']) for p in spot['data']['places'])
        for body, status, reason in (
            ({**payload, 'slot_types': ['음식']}, 400, 'invalid_request'),
            ({**payload, 'user_lat': 38}, 422, 'outside_service_area'),
        ):
            actual, error = request('/recommend/course', body)
            assert actual == status and error['error']['reason'] == reason
        status, tags = request('/suggest/tags', {'user_text': '카페'})
        assert status == 503 and tags['error']['reason'] == 'tags_unavailable'
        status, pin = request('/kakao/place?' + urlencode({'name': '아지트', 'lat': 36.8151, 'lng': 127.1139}))
        assert status == 200 and pin['place_url'] is None and pin['reason'] == 'map_not_configured'
        print(json.dumps({'loopback_only': True, 'cases': 7, 'courses': 5, 'spots': 5,
                          'error_statuses': [400, 422, 503], 'repeatable': True,
                          'preference_evidence': data['metadata']['preference_evidence']}, ensure_ascii=False))
    finally:
        if gateway is not None:
            gateway.terminate()
            try:
                gateway.wait(timeout=5)
            except subprocess.TimeoutExpired:
                gateway.kill()
                gateway.wait(timeout=5)
        flask.shutdown()
        flask.server_close()
        thread.join(timeout=5)
        assert hashlib.sha256(DB.read_bytes()).hexdigest() == before, 'Source DB changed'


if __name__ == '__main__':
    main()
