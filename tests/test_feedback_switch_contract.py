"""Actual Dart facade bodies must agree with Flask's signed mode-switch plan."""
import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

import app
from place_identity import ensure_ids
from test_api_dart import DART, PACKAGES, ROOT


HARNESS = r'''
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ai_travel_app/recommendation_source.dart';

Future<void> main() async {
  final captured = <Map<String, dynamic>>[];
  await http.runWithClient(() async {
    const source = ApiRecommendationSource();
    final request = RecommendationRequest(
      mode: 'spot', userText: '카페 갔다가 공원 산책', transport: '대중교통',
      region: '천안', lat: 36.8013, lng: 127.13587, tags: QA_TAGS, count: 5,
      slotTypes: ['음식', '자연·산책', '카페'], naturalPlan: false, seed: 42,
    );
    await source.interpret(request);
    await source.recommend(request.reviewed(
      token: 'QA_TOKEN', targetMode: 'course', targetCount: 1,
    ));
  }, () => MockClient((request) async {
    captured.add({'path': request.url.path, 'body': jsonDecode(request.body)});
    return http.Response(jsonEncode({'success': false, 'error': {
      'error': '오프라인 요청 캡처', 'reason': 'unavailable',
    }}), 503, headers: {'content-type': 'application/json; charset=utf-8'});
  }));
  print(jsonEncode(captured));
}
'''


@pytest.mark.skipif(not DART or not Path(DART).is_file() or not PACKAGES.exists(),
                   reason='Installed Dart SDK and offline packages required')
@pytest.mark.parametrize('tags', [
    [],
    ['연인과', '로맨틱한', '기념일'],
    ['친구와', '활동적인', '실내 위주'],
])
def test_dart_spot_to_course_body_accepts_real_flask_signature(tmp_path, monkeypatch, tags):
    script = tmp_path / 'mode_switch.dart'
    script.write_text(HARNESS.replace('QA_TAGS', json.dumps(tags, ensure_ascii=False)))
    run = subprocess.run([DART, f'--packages={PACKAGES}', str(script)], cwd=ROOT,
                         text=True, capture_output=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    captured = json.loads(run.stdout)
    assert [r['path'] for r in captured] == ['/travel/interpret', '/recommend/course']
    initial, switched = [r['body'] for r in captured]
    assert initial['persona_tags'] == switched['persona_tags'] == tags

    def model(system, message, **kwargs):
        if system == app.intent.SELECTION_SYSTEM:
            raise RuntimeError('Use the deterministic selection in this contract test')
        return dict(schema_version=1, companion=None, stages=[
            dict(id='s1', activity='카페', quote='카페', category_filters=['카페'],
                 conditions=[], preferences=[]),
            dict(id='s2', activity='공원 산책', quote='공원 산책', category_filters=['공원'],
                 conditions=[], preferences=[]),
        ], exclusions=[], ambiguities=[], unsupported=[], requested_visit_count=None)

    frame = ensure_ids(pd.DataFrame([
        dict(가게명=name, 주소=f'충남 천안시 테스트로 {i + 1}', 지역='천안', 카테고리=kind,
             latitude=36.8013 + .0001 * i, longitude=127.13587,
             방문자수=100, 블로그수=0, blog_tags='{}')
        for i, (name, kind) in enumerate([('계약 카페', '카페'), ('계약 공원', '공원')])
    ]))
    monkeypatch.setattr(app, '_call_claude', model)
    monkeypatch.setattr(app, 'get_df', lambda *_: frame.copy())
    client = app.app.test_client()
    preview = client.post('/travel/interpret', json=initial)
    assert preview.status_code == 200, preview.json
    assert preview.json['mode_switch_required'] is True
    switched['intent_token'] = preview.json['intent_token']
    response = client.post('/recommend/course', json=switched)
    assert response.status_code == 200, response.json
    assert [p['name'] for p in response.json['courses'][0]] == ['계약 카페', '계약 공원']
    rejected = client.post('/recommend/course', json={**switched, 'plan_mode': 'manual'})
    assert rejected.status_code == 400
    assert rejected.json['reason'] == 'intent_expired'
