"""Run the real Dart HTTP client with in-memory HTTP mocks (no device or API key).

After `flutter pub get --offline --directory android_app`, this test needs only
Dart. Keep the harness here so API-owned tests do not modify shared Flutter tests.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import unquote, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / 'android_app/.dart_tool/package_config.json'


def dart_sdk():
    if os.environ.get('DART_BIN'):
        return os.environ['DART_BIN']
    if PACKAGES.exists():
        packages = json.loads(PACKAGES.read_text())['packages']
        flutter = next((p for p in packages if p['name'] == 'flutter'), None)
        if flutter:
            sdk = Path(unquote(urlparse(flutter['rootUri']).path)).parents[1]
            dart = sdk / 'bin/cache/dart-sdk/bin/dart'
            if dart.exists():
                return str(dart)
    return shutil.which('dart') or ''


DART = dart_sdk()

HARNESS = r'''
import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ai_travel_app/api_service.dart';
import 'package:ai_travel_app/network/api_client.dart';

class HangingClient extends http.BaseClient {
  bool aborted = false;
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    (request as http.Abortable).abortTrigger!.then((_) => aborted = true);
    return Completer<http.StreamedResponse>().future;
  }
}

int checks = 0;
void check(bool value, String label) {
  checks++;
  if (!value) throw StateError(label);
}

http.Response jsonResponse(Object data, [int status = 200]) => http.Response(
  jsonEncode(data), status, headers: {'content-type': 'application/json; charset=utf-8'},
);

const place = {'place_id': 'naver:1', 'identity_key': 'local:1', 'name': '공원',
  'lat': 36.8151, 'lng': 127.1139, 'address': '충남 천안시 테스트로 1', 'category': '공원',
  'score': 0.0, 'blog_tag_status': 'legacy_unverified'};

Future<Map<String, dynamic>> spot(ApiClient client) => client.getSpotRecommendation(
  userText: '공원', transport: '대중교통', region: '천안', userLat: 36.8151,
  userLng: 127.1139, personaTags: ['조용한'], count: 5,
);

Future<void> main(List<String> args) async {
  check(ApiService.baseUrl == args.single, 'compile-time base URL and emulator default');
  final inputClient = ApiClient(baseUrl: 'http://mock.invalid:8088/', client: MockClient((req) async {
    check(req.url.toString() == 'http://mock.invalid:8088/recommend/spot', 'configured base URL');
    check(req.headers['content-type']!.startsWith('application/json'), 'JSON content type');
    final body = jsonDecode(req.body);
    check(body['user_text'] == '공원' && body['count'] == 5 && body['user_lat'] == 36.8151,
      'spot payload fields preserve types');
    return jsonResponse({'success': true, 'data': {'places': [place],
      'metadata': {'preference_evidence': 'unavailable', 'verified_tag_candidate_count': 0}}});
  }));
  final success = await spot(inputClient);
  check(success['success'] == true && success['data']['places'][0]['name'] == '공원', 'UTF-8 envelope');
  check(success['data']['metadata']['preference_evidence'] == 'unavailable', 'evidence metadata');
  inputClient.close();

  final courseClient = ApiClient(client: MockClient((req) async {
    final body = jsonDecode(req.body);
    check(req.url.path == '/recommend/course' && body['spot_count'] == 3 &&
      body['slot_types'].join(',') == '음식,자연·산책,카페', 'ordered slot payload');
    return jsonResponse({'success': true, 'data': {'courses': [[place]],
      'course_metrics': [{'travel_time_minutes': null}], 'metadata': {'constraints_relaxed': []}}});
  }));
  final course = await courseClient.getCourseRecommendation(transport: '차', region: '아산',
    userLat: 36.8151, userLng: 127.1139, personaTags: [], count: 3,
    spotCount: 3, slotTypes: ['음식', '자연·산책', '카페']);
  check(course['data']['course_metrics'][0]['travel_time_minutes'] == null, 'no invented travel time');
  courseClient.close();

  for (final wrapped in [true, false]) {
    final failure = {'error': '조건에 맞는 장소가 없습니다.', 'places': [],
      'metadata': {'reason': 'insufficient_candidates', 'constraints_relaxed': []}};
    final client = ApiClient(client: MockClient((_) async => jsonResponse(
      wrapped ? {'success': false, 'error': failure} : failure, 422)));
    final result = await spot(client);
    check(result['error'] is String && result['error'] == failure['error'], 'flat UI-safe error');
    check(result['status_code'] == 422 && result['metadata']['reason'] == 'insufficient_candidates',
      '422 constraints are retained');
    client.close();
  }
  for (final status in [400, 503, 504]) {
    final client = ApiClient(client: MockClient((_) async => jsonResponse(
      {'success': false, 'error': {'error': '처리할 수 없습니다.', 'reason': 'mock_reason'}}, status)));
    final result = await spot(client);
    check(result['error'] == '처리할 수 없습니다.' && result['status_code'] == status &&
      result['reason'] == 'mock_reason', 'status $status remains actionable');
    client.close();
  }

  for (final body in ['<html>private stack</html>', '[]', 'null']) {
    final client = ApiClient(client: MockClient((_) async => http.Response(body, 502)));
    final result = await spot(client);
    check(result['reason'] == 'invalid_response' && result['status_code'] == 502 && !result['error'].contains('private'), 'non-JSON response');
    client.close();
  }
  for (final data in [
    {'places': 'bad'}, {'places': [null]}, {'places': [{'name': 'bad', 'lat': 'NaN', 'lng': 127}]},
    {'places': [place], 'metadata': []}, {'data': []},
  ]) {
    final client = ApiClient(client: MockClient((_) async => jsonResponse(data)));
    check((await spot(client))['reason'] == 'invalid_response', 'malformed successful recommendation');
    client.close();
  }
  final direct = ApiClient(client: MockClient((_) async => jsonResponse({'places': [place]})));
  check((await spot(direct))['places'][0]['name'] == '공원', 'legacy direct Flask success');
  direct.close();

  final disconnected = ApiClient(client: MockClient((_) async => throw http.ClientException('private address')));
  final unavailable = await spot(disconnected);
  check(unavailable['reason'] == 'network_unavailable' && !unavailable['error'].contains('private'),
    'network exception is sanitized');
  disconnected.close();

  final hanging = ApiClient(timeout: const Duration(milliseconds: 5), client: MockClient((_) => Completer<http.Response>().future));
  check((await spot(hanging))['reason'] == 'network_timeout', 'POST timeout');
  check(await hanging.getKakaoPlaceUrl(name: '공원', lat: 36.8, lng: 127.1) == null, 'map timeout pin fallback');
  hanging.close();
  final cancelTransport = HangingClient();
  final cancellable = ApiClient(timeout: const Duration(milliseconds: 5), client: cancelTransport);
  check((await spot(cancellable))['reason'] == 'network_timeout', 'abortable timeout result');
  await Future<void>.delayed(Duration.zero);
  check(cancelTransport.aborted, 'deadline aborts the underlying request');
  cancellable.close();
  final stalledBody = StreamController<List<int>>();
  final slowBody = ApiClient(timeout: const Duration(milliseconds: 5), client: MockClient.streaming(
    (_, __) async => http.StreamedResponse(stalledBody.stream, 200)));
  check((await spot(slowBody))['reason'] == 'network_timeout', 'deadline covers the full response body');
  await stalledBody.close();
  slowBody.close();

  for (final wrapped in [true, false]) {
    final tags = ApiClient(client: MockClient((_) async => jsonResponse(wrapped
      ? {'success': true, 'data': {'tags': ['혼자', '조용한', '혼자']}} : {'tags': ['혼자', '조용한', '혼자']})));
    check((await tags.suggestTags(userText: '추천')).join(',') == '혼자,조용한', 'tag response compatibility');
    tags.close();
  }
  for (final body in [{'tags': [3]}, {'tags': 'bad'}, {'success': false, 'error': {'error': '장애'}}]) {
    final tags = ApiClient(client: MockClient((_) async => jsonResponse(body)));
    check((await tags.suggestTags(userText: '추천')).isEmpty, 'tag errors remain optional');
    tags.close();
  }
  final blank = ApiClient(client: MockClient((_) async => throw StateError('blank input must be local')));
  check((await blank.suggestTags(userText: '  ')).isEmpty, 'blank tag suggestion skips HTTP');
  blank.close();

  for (final url in ['https://place.map.kakao.com/123', 'http://place.map.kakao.com/123', 'https://other.invalid/123', 'javascript:alert(1)', null]) {
    final map = ApiClient(client: MockClient((req) async {
      check(req.url.queryParameters['address'] == '충남 천안시 테스트로 1', 'original map identity evidence');
      check(req.url.queryParameters['lat'] == '36.8151', 'original map coordinate');
      return jsonResponse({'place_url': url});
    }));
    check(await map.getKakaoPlaceUrl(name: '공원', address: '충남 천안시 테스트로 1',
      lat: 36.8151, lng: 127.1139) == (url != null && url.contains('place.map.kakao.com') ? 'https://place.map.kakao.com/123' : null), 'map URL validation');
    map.close();
  }
  print('$checks Dart contract checks passed');
}
'''


@pytest.mark.skipif(not DART or not Path(DART).is_file() or not PACKAGES.exists(),
                    reason='Dart SDK and android_app offline pub dependencies are required')
@pytest.mark.parametrize('base_url', ['http://10.0.2.2:8080', 'http://configured.invalid:9080'])
def test_dart_client_http_contract(tmp_path, base_url):
    harness = tmp_path / 'api_client_contract.dart'
    harness.write_text(HARNESS)
    args = [DART, f'--packages={PACKAGES}']
    if base_url != 'http://10.0.2.2:8080':
        args.append(f'-DAPI_BASE_URL={base_url}')
    result = subprocess.run([*args, str(harness), base_url], cwd=ROOT,
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'Dart contract checks passed' in result.stdout
