import 'dart:async';
import 'dart:convert';

import 'package:ai_travel_app/course_map_data.dart';
import 'package:ai_travel_app/course_map_document.dart';
import 'package:ai_travel_app/course_map_panel.dart';
import 'package:ai_travel_app/course_result_screen.dart';
import 'package:ai_travel_app/network/api_client.dart';
import 'package:ai_travel_app/network/course_route_client.dart';
import 'package:ai_travel_app/network/request_cancellation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _places = [
  {'name': '첫 장소', 'lat': 36.8, 'lng': 127.1},
  {'name': '둘째 장소', 'lat': 36.81, 'lng': 127.12},
];
const _curve = [
  [127.1, 36.8],
  [127.115, 36.8],
  [127.115, 36.805],
  [127.12, 36.81],
];
const _configuration = KakaoMapConfiguration(javascriptKey: 'test-only');

Map<String, dynamic> _response({
  String mode = 'transit',
  String pathMode = 'transit',
}) => {
  'success': true,
  'data': {
    'mode': mode,
    'status': 'ready',
    'segments': [
      {
        'fromIndex': 0,
        'toIndex': 1,
        'status': 'ready',
        'paths': [
          {'mode': pathMode, 'points': _curve},
        ],
      },
    ],
  },
};
CourseRouteData _route({String mode = 'transit'}) => CourseRouteData.parse(
  _response(mode: mode, pathMode: mode),
  mode: mode,
  stops: courseMapStops(_places),
);

class _Session implements CourseMapSession {
  final ValueChanged<String> message;
  Map<String, dynamic> payload = {};
  final payloads = <Map<String, dynamic>>[];
  bool closed = false;
  int viewportReconciliations = 0;
  _Session(this.message);
  @override
  Future<void> load(String html, String origin) async {
    payload =
        jsonDecode(RegExp(r'let state=(.*?), map=null').firstMatch(html)![1]!)
            as Map<String, dynamic>;
    payloads.add(payload);
    message(jsonEncode({'type': 'document'}));
  }

  @override
  Future<void> update(String script) async {
    if (script == 'window.courseMap && window.courseMap.reconcileViewport();') {
      viewportReconciliations++;
      return;
    }
    payload =
        jsonDecode(
              script.substring(
                script.indexOf('render(') + 7,
                script.length - 2,
              ),
            )
            as Map<String, dynamic>;
    payloads.add(payload);
    message(jsonEncode({'type': 'ready', 'revision': payload['revision']}));
  }

  @override
  Widget buildView() => const SizedBox(key: ValueKey('route-test-map'));
  @override
  Future<void> close() async {
    closed = true;
  }
}

class _AbortableTransport extends http.BaseClient {
  final started = Completer<void>();
  final didAbort = Completer<void>();
  bool aborted = false;
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    started.complete();
    await (request as http.AbortableRequest).abortTrigger;
    aborted = true;
    didAbort.complete();
    throw http.RequestAbortedException(request.url);
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test(
    'validated provider turns reach the document unchanged, with centered dashes and no arrows',
    () {
      final route = _route();
      final payload = courseMapPayload(
        stops: courseMapStops(_places),
        selectedIndex: null,
        revision: 1,
        route: route,
      );
      expect(
        (payload['route'] as Map)['segments'][0]['paths'][0]['points'],
        _curve,
      );
      final html = courseMapDocument(
        javascriptKey: 'test-only',
        payload: payload,
      );
      expect(
        html,
        contains(
          'projection.pointFromCoords(new kakao.maps.LatLng(coordinates[1],coordinates[0]))',
        ),
      );
      expect(
        html,
        contains('local.matrixTransform(camera).matrixTransform(inverse)'),
      );
      expect(html, contains("['visit-route','#914b33','5.6']"));
      expect(html, contains("['visit-route-center','#fffdfb','1.2']"));
      expect(html, contains("stroke-dasharray','7 6'"));
      expect(html, isNot(contains("classList.add('direction')")));
      expect(html, isNot(contains('M-5.5,-3')));
      expect(html, isNot(contains('tips.get(')));
      expect(html, contains('...routePaths().flatMap(path=>path.points)'));
      final noRoute = courseMapPayload(
        stops: courseMapStops(_places),
        selectedIndex: null,
        revision: 2,
      );
      expect(noRoute['route'], isNull);
    },
  );

  test(
    'transit allows an all-walking provider leg, but never car replacement',
    () {
      final stops = courseMapStops(_places);
      final walk = CourseRouteData.parse(
        _response(pathMode: 'walk'),
        mode: 'transit',
        stops: stops,
      );
      expect(walk.status, 'ready');
      expect(walk.segments.single.paths.single.mode, 'walk');
      expect(
        CourseRouteData.parse(
          _response(pathMode: 'car'),
          mode: 'transit',
          stops: stops,
        ).hasPaths,
        false,
      );
      expect(courseRouteMode('대중교통'), 'transit');
      for (final label in ['차', '자동차', '자차', 'car']) {
        expect(courseRouteMode(label), 'car');
      }
      expect(courseRouteMode('도보'), 'walk');
    },
  );

  test(
    'invalid coordinates, missing visits, duplicate and excessive geometry are rejected',
    () {
      final stops = courseMapStops(_places);
      CourseRouteData parse(
        Map<String, dynamic> response, {
        List<CourseMapStop>? visits,
      }) => CourseRouteData.parse(
        response,
        mode: 'transit',
        stops: visits ?? stops,
      );
      for (final point in [
        [double.nan, 36.8],
        [127.1, double.infinity],
        [0, 0],
        [127.1, 39.6],
        [133, 36.8],
        [127.1],
      ]) {
        final response = _response();
        response['data']['segments'][0]['paths'][0]['points'] = [
          _curve.first,
          point,
        ];
        expect(parse(response).hasPaths, false);
      }
      final excessive = _response();
      excessive['data']['segments'][0]['paths'][0]['points'] = List.filled(
        CourseRouteData.maxPoints + 1,
        _curve.first,
      );
      expect(parse(excessive).hasPaths, false);
      final duplicate = _response();
      duplicate['data']['segments'].add(duplicate['data']['segments'][0]);
      expect(parse(duplicate).hasPaths, false);
      final missing = _response();
      missing['data']['segments'] = [];
      expect(parse(missing).hasPaths, false);
      final gapStops = courseMapStops([
        _places[0],
        {'name': '누락'},
        _places[1],
      ]);
      final gap = _response();
      gap['data']['segments'][0]['toIndex'] = 2;
      expect(parse(gap, visits: gapStops).hasPaths, false);
      expect(
        () => _route().segments.single.paths.single.points.add([127.1, 36.8]),
        throwsUnsupportedError,
      );
    },
  );

  test(
    'partial data keeps only real successful segments and suppresses permission retries',
    () {
      final stops = courseMapStops([
        ..._places,
        {'name': '셋째', 'lat': 36.82, 'lng': 127.13},
      ]);
      final response = _response();
      response['data']['status'] = 'partial';
      response['data']['segments'].add({
        'fromIndex': 1,
        'toIndex': 2,
        'status': 'unavailable',
        'reason': 'permission_denied',
        'paths': [],
      });
      final route = CourseRouteData.parse(
        response,
        mode: 'transit',
        stops: stops,
      );
      expect(route.status, 'partial');
      expect(route.hasPaths, true);
      expect(route.segments.last.paths, isEmpty);
      expect(route.canRetry, false);
    },
  );

  test(
    'client sends original indices, caches validated success and does not cache a cancelled response',
    () async {
      var requests = 0;
      final pending = Completer<http.Response>();
      final httpClient = MockClient((request) async {
        requests++;
        expect(request.url.path, '/routes/course');
        final body = jsonDecode(request.body) as Map;
        expect(body['mode'], 'car');
        expect(body['stops'].map((dynamic stop) => stop['index']), [0, 1]);
        expect(body['stops'][0].keys.toSet(), {'index', 'name', 'lat', 'lng'});
        return requests == 1
            ? pending.future
            : http.Response(
                jsonEncode(_response(mode: 'car', pathMode: 'car')),
                200,
              );
      });
      final client = CourseRouteClient(
        api: ApiClient(baseUrl: 'https://example.test', client: httpClient),
      );
      addTearDown(client.close);
      final cancellation = RequestCancellation();
      final first = client.load(
        mode: 'car',
        stops: courseMapStops(_places),
        cancellation: cancellation,
      );
      await Future<void>.delayed(Duration.zero);
      cancellation.cancel();
      pending.complete(
        http.Response(jsonEncode(_response(mode: 'car', pathMode: 'car')), 200),
      );
      expect((await first).hasPaths, false);
      expect(
        (await client.load(
          mode: 'car',
          stops: courseMapStops(_places),
          cancellation: RequestCancellation(),
        )).hasPaths,
        true,
      );
      expect(
        (await client.load(
          mode: 'car',
          stops: courseMapStops(_places),
          cancellation: RequestCancellation(),
        )).hasPaths,
        true,
      );
      expect(requests, 2);
      final preCancelled = RequestCancellation()..cancel();
      expect(
        (await client.load(
          mode: 'car',
          stops: courseMapStops(_places),
          cancellation: preCancelled,
        )).hasPaths,
        false,
      );
      expect(requests, 2);
    },
  );

  test(
    'route HTTP transport aborts both cancelled and timed-out requests',
    () async {
      final cancelledTransport = _AbortableTransport();
      final cancelledClient = CourseRouteClient(
        api: ApiClient(
          baseUrl: 'https://example.test',
          client: cancelledTransport,
        ),
      );
      addTearDown(cancelledClient.close);
      final cancellation = RequestCancellation();
      final cancelled = cancelledClient.load(
        mode: 'transit',
        stops: courseMapStops(_places),
        cancellation: cancellation,
      );
      await cancelledTransport.started.future;
      cancellation.cancel();
      expect((await cancelled).hasPaths, false);
      expect(cancelledTransport.aborted, true);

      final timedTransport = _AbortableTransport();
      final timedClient = CourseRouteClient(
        api: ApiClient(
          baseUrl: 'https://example.test',
          client: timedTransport,
          timeout: const Duration(milliseconds: 10),
        ),
      );
      addTearDown(timedClient.close);
      final timed = await timedClient.load(
        mode: 'transit',
        stops: courseMapStops(_places),
        cancellation: RequestCancellation(),
      );
      expect(timed.hasPaths, false);
      expect(timed.failureReason, 'timeout');
      await timedTransport.didAbort.future;
      expect(timedTransport.aborted, true);
    },
  );

  testWidgets(
    'SDK readiness is independent; inactive and changed courses cancel and ignore late routes',
    (tester) async {
      final sessions = <_Session>[];
      final calls =
          <
            ({
              RequestCancellation cancellation,
              Completer<CourseRouteData> result,
            })
          >[];
      Future<CourseRouteData> loader({
        required String mode,
        required List<CourseMapStop> stops,
        required RequestCancellation cancellation,
      }) {
        final result = Completer<CourseRouteData>();
        calls.add((cancellation: cancellation, result: result));
        return result.future;
      }

      CourseMapSession factory(
        ValueChanged<String> message,
        VoidCallback failure,
      ) {
        final session = _Session(message);
        sessions.add(session);
        return session;
      }

      Widget panel({
        bool active = true,
        List<Map<String, dynamic>> places = _places,
      }) => MaterialApp(
        home: Scaffold(
          body: CourseMapPanel(
            places: places,
            selectedIndex: null,
            onSelect: (_) {},
            active: active,
            configuration: _configuration,
            sessionFactory: factory,
            routeLoader: loader,
          ),
        ),
      );
      await tester.pumpWidget(panel());
      await tester.pump();
      expect(find.byKey(const ValueKey('route-test-map')), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsNothing);
      expect(find.byType(LinearProgressIndicator), findsOneWidget);
      expect(calls.length, 1);
      await tester.pumpWidget(panel(active: false));
      await tester.pump();
      expect(calls.first.cancellation.isCancelled, true);
      expect(sessions.first.closed, true);
      calls.first.result.complete(_route());
      await tester.pump();
      await tester.pumpWidget(panel());
      await tester.pump();
      expect(calls.length, 2);
      final changed = [
        _places[0],
        {..._places[1], 'lat': 36.83},
      ];
      await tester.pumpWidget(panel(places: changed));
      await tester.pump();
      expect(calls[1].cancellation.isCancelled, true);
      expect(calls.length, 3);
      calls[1].result.complete(_route());
      await tester.pump();
      expect(sessions.last.payload['route'], isNull);
      calls[2].result.complete(
        CourseRouteData.unavailable('transit', 'timeout'),
      );
      await tester.pump();
      expect(sessions.last.payload['route']['segments'], isEmpty);
      expect(find.text('경로 다시 시도'), findsOneWidget);
      expect(find.byKey(const ValueKey('route-test-map')), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'a changed course clears ready geometry before sending its new stops',
    (tester) async {
      final sessions = <_Session>[];
      final next = Completer<CourseRouteData>();
      var calls = 0;
      Future<CourseRouteData> loader({
        required String mode,
        required List<CourseMapStop> stops,
        required RequestCancellation cancellation,
      }) {
        calls++;
        return calls == 1 ? Future.value(_route()) : next.future;
      }

      CourseMapSession factory(
        ValueChanged<String> message,
        VoidCallback failure,
      ) {
        final session = _Session(message);
        sessions.add(session);
        return session;
      }

      Widget panel(List<Map<String, dynamic>> places) => MaterialApp(
        home: Scaffold(
          body: CourseMapPanel(
            places: places,
            selectedIndex: null,
            onSelect: (_) {},
            configuration: _configuration,
            sessionFactory: factory,
            routeLoader: loader,
          ),
        ),
      );
      await tester.pumpWidget(panel(_places));
      await tester.pumpAndSettle();
      expect(sessions.single.payload['route']['status'], 'ready');
      final changed = [
        {..._places[0], 'name': '새 장소'},
        _places[1],
      ];
      await tester.pumpWidget(panel(changed));
      await tester.pump();
      final newPayloads = sessions.single.payloads.where(
        (payload) => payload['stops'][0]['name'] == '새 장소',
      );
      expect(newPayloads, isNotEmpty);
      expect(newPayloads.every((payload) => payload['route'] == null), true);
      await tester.pumpWidget(const SizedBox());
      next.complete(_route());
      await tester.pump();
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'route timeout cancels the request; permission failures preserve map without retry loop',
    (tester) async {
      late RequestCancellation captured;
      final pending = Completer<CourseRouteData>();
      Future<CourseRouteData> loader({
        required String mode,
        required List<CourseMapStop> stops,
        required RequestCancellation cancellation,
      }) {
        return pending.future;
      }

      Future<CourseRouteData> capture({
        required String mode,
        required List<CourseMapStop> stops,
        required RequestCancellation cancellation,
      }) {
        // Keep the actual cancellation handle used by the panel.
        captured = cancellation;
        return loader(mode: mode, stops: stops, cancellation: cancellation);
      }

      final sessions = <_Session>[];
      CourseMapSession factory(
        ValueChanged<String> message,
        VoidCallback failure,
      ) {
        final session = _Session(message);
        sessions.add(session);
        return session;
      }

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CourseMapPanel(
              places: _places,
              selectedIndex: null,
              onSelect: (_) {},
              configuration: _configuration,
              sessionFactory: factory,
              routeLoader: capture,
              routeTimeout: const Duration(milliseconds: 100),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 101));
      expect(captured.isCancelled, true);
      expect(find.text('경로 다시 시도'), findsOneWidget);
      pending.complete(_route());
      await tester.pump();
      expect(sessions.last.payload['route']['status'], 'unavailable');
      await tester.pumpWidget(const SizedBox());
      Future<CourseRouteData> denied({
        required String mode,
        required List<CourseMapStop> stops,
        required RequestCancellation cancellation,
      }) async => CourseRouteData.unavailable(mode, 'permission_denied');
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CourseMapPanel(
              places: _places,
              selectedIndex: null,
              onSelect: (_) {},
              configuration: _configuration,
              sessionFactory: factory,
              routeLoader: denied,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('경로를 표시할 수 없어요'), findsOneWidget);
      expect(find.text('경로 다시 시도'), findsNothing);
      expect(find.byKey(const ValueKey('route-test-map')), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'result passes selected transport and only loads the active course',
    (tester) async {
      final modes = <String>[];
      final visits = <List<CourseMapStop>>[];
      Future<CourseRouteData> loader({
        required String mode,
        required List<CourseMapStop> stops,
        required RequestCancellation cancellation,
      }) async {
        modes.add(mode);
        visits.add(stops);
        return CourseRouteData.unavailable(mode);
      }

      await tester.pumpWidget(
        MaterialApp(
          home: CourseResultScreen(
            courses: [
              _places,
              [
                {..._places[0], 'name': '다른 첫 장소'},
                {..._places[1], 'name': '다른 둘째 장소'},
              ],
            ],
            requestedCount: 2,
            transport: '차',
            mapConfiguration: _configuration,
            routeLoader: loader,
            mapSessionFactory: (message, failure) => _Session(message),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(modes, ['car']);
      expect(visits.single.first.name, '첫 장소');
      await tester.tap(find.text('코스 2'));
      await tester.pumpAndSettle();
      expect(modes, ['car', 'car']);
      expect(visits.last.first.name, '다른 첫 장소');
      await tester.pumpWidget(const SizedBox());
    },
  );
}
