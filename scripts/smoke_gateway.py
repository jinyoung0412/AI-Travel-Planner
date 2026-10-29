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
        # Full new contract over the production gateway and frozen read-only DB.
        # Model semantics here are a fixed fixture, never a paid/live call.
        import travel_intent as ti
        intent_calls = []
        sentence = '연인과 산책하다가 시끌벅적한 야장에 가고 싶다'
        def model(system, message, **kwargs):
            message = json.loads(message)
            intent_calls.append(system)
            if system != ti.SELECTION_SYSTEM:
                assert message == {'source_text': sentence, 'region': '천안'}
                return dict(schema_version=1, companion=dict(value='연인과', quote='연인과'),
                    stages=[dict(id='s1', activity='산책', quote='산책', category_filters=['공원', '산책로'], conditions=[], preferences=[]),
                            dict(id='s2', activity='야외 맥주', quote='야장', category_filters=['맥주', '호프'],
                                 conditions=[dict(field='outdoor_seating', value=True, required=True, quote='야장')],
                                 preferences=[dict(field='lively', quote='시끌벅적한')])],
                    exclusions=[], ambiguities=[], unsupported=[], requested_visit_count=None)
            assert sum(map(len, message['candidates'])) <= 30
            return {'courses': [[dict(stage_id=s['id'], place_id=p[0]['place_id'],
                evidence_refs=[e['id'] for e in p[0]['evidence']], reason_codes=['category_match', 'distance'],
                satisfied_condition_ids=p[0]['satisfied_condition_ids'], unverified_condition_ids=p[0]['unverified_condition_ids'])
                for s, p in zip(message['stages'], message['candidates'])]]}
        app._call_claude = model
        intent_request = {**payload, 'mode': 'spot', 'user_text': sentence, 'persona_tags': [],
                          'intent_version': 1, 'plan_mode': 'natural'}
        status, preview = request('/travel/interpret', intent_request)
        assert status == 200 and preview['data']['mode_switch_required'] is True
        course_request = {**intent_request, 'count': 1, 'slot_types': [],
                          'intent_token': preview['data']['intent_token']}
        status, missing = request('/recommend/course', course_request)
        assert status == 422 and missing['error']['reason'] == 'unverified_conditions'
        status, alternative = request('/recommend/course', {**course_request, 'accept_unverified': True})
        assert status == 200, alternative
        assert len(alternative['data']['courses'][0]) == 2
        assert alternative['data']['metadata']['intent_status'] == 'unverified_alternative'
        assert alternative['data']['metadata']['selection_method'] == 'ai_candidates'
        assert len(intent_calls) == 2
        # A purpose-only request has no recommendation token yet. Exercise the
        # actual gateway envelope, then the signed activity choice and completed
        # recommendation, so a gateway requiring intent_token too early fails here.
        date_sentence = '연인이랑 데이트 할 곳을 찾고있어요'
        date_calls = []
        def date_model(system, message, **kwargs):
            message = json.loads(message)
            date_calls.append((system, message))
            assert kwargs['max_retries'] == 1
            if system != ti.SELECTION_SYSTEM:
                assert message['region'] == '천안'
                selected = message['source_text'] == date_sentence + '\n추가로 직접 선택한 활동: 카페·디저트'
                assert selected or message['source_text'] == date_sentence
                return dict(schema_version=1, companion=dict(value='연인과', quote='연인이랑'),
                    stages=([dict(id='s1', activity='카페·디저트', quote='카페·디저트',
                                  category_filters=['카페'], conditions=[], preferences=[])] if selected else []),
                    exclusions=[], ambiguities=[] if selected else [dict(quote='데이트', reason='활동 선택이 필요합니다')],
                    unsupported=[], requested_visit_count=None)
            assert message['expected_count'] == message['count'] == 1
            candidate = message['candidates'][0][0]
            return {'courses': [[dict(stage_id='s1', place_id=candidate['place_id'],
                evidence_refs=[e['id'] for e in candidate['evidence']], reason_codes=['category_match', 'distance'],
                satisfied_condition_ids=candidate['satisfied_condition_ids'],
                unverified_condition_ids=candidate['unverified_condition_ids'])]]}
        app._call_claude = date_model
        date_request = {**intent_request, 'user_text': date_sentence, 'count': 1, 'seed': 43,
                        'persona_tags': ['연인과', '첫 데이트']}
        status, clarification = request('/travel/interpret', date_request)
        assert status == 200 and clarification['success'] is True, clarification
        clarification = clarification['data']
        assert clarification['clarification_required'] is True
        assert 'intent_token' not in clarification
        assert len(clarification['clarification']['options']) == 6
        assert clarification['travel_request']['source_text'] == date_sentence
        assert clarification['travel_request']['applied_controls']['persona_tags'] == date_request['persona_tags']
        # The unresolved plan must also cross Node's error whitelist intact.
        status, unresolved = request('/recommend/spot', date_request)
        assert status == 422 and unresolved['error']['reason'] == 'activity_clarification_required', unresolved
        clarified_request = {**date_request, 'activity_choice': '카페',
                             'clarification_token': clarification['clarification']['token']}
        status, resolved = request('/travel/interpret', clarified_request)
        assert status == 200 and resolved['success'] is True, resolved
        resolved = resolved['data']
        assert resolved['clarification_required'] is False and resolved['intent_token']
        assert resolved['travel_request']['source_text'] == date_sentence
        assert resolved['travel_request']['activity_choice'] == '카페'
        assert resolved['travel_request']['companion']['value'] == '연인과'
        assert resolved['travel_request']['applied_controls']['persona_tags'] == date_request['persona_tags']
        assert resolved['travel_request']['unapplied_manual_tags'] == ['첫 데이트']
        recommend_date = {**date_request, 'activity_choice': '카페', 'intent_token': resolved['intent_token']}
        status, date_result = request('/recommend/spot', recommend_date)
        assert status == 200 and date_result['success'] is True, date_result
        assert len(date_result['data']['places']) == 1
        assert app.category_matches(date_result['data']['places'][0]['category'], app.SLOT_CATEGORY_MAP['카페'])
        metadata = date_result['data']['metadata']
        assert metadata['selection_method'] in ('ai_candidates', 'rules_fallback')
        if metadata['selection_method'] == 'rules_fallback':
            assert metadata['selection_fallback_reason'] == 'quality_guard'
        assert metadata['travel_request']['source_text'] == date_sentence
        assert metadata['travel_request']['applied_controls']['persona_tags'] == date_request['persona_tags']
        # Completed tokens bind the original seed and selected activity; neither
        # can be changed at recommendation time without another confirmation.
        for changed in ({'seed': 44}, {'activity_choice': '음식'}):
            status, rejected = request('/recommend/spot', {**recommend_date, **changed})
            assert status == 400 and rejected['error']['reason'] == 'intent_expired', rejected
        assert sum(system != ti.SELECTION_SYSTEM for system, _ in date_calls) == 2
        assert sum(system == ti.SELECTION_SYSTEM for system, _ in date_calls) == 1
        print(json.dumps({'loopback_only': True, 'cases': 16, 'courses': 5, 'spots': 5,
                          'natural_visits': 2, 'mock_interpretation_calls': 1, 'mock_selection_calls': 1,
                          'activity_clarification_flow': True, 'clarification_mock_interpretation_calls': 2,
                          'clarification_mock_selection_calls': 1,
                          'clarification_selection_method': metadata['selection_method'],
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
