import 'dart:convert';

import 'package:ai_travel_app/course_map_data.dart';
import 'package:ai_travel_app/course_map_document.dart';
import 'package:ai_travel_app/course_map_panel.dart';
import 'package:ai_travel_app/course_result_screen.dart';
import 'package:ai_travel_app/course_timeline.dart';
import 'package:ai_travel_app/local_storage_service.dart';
import 'package:ai_travel_app/network/request_cancellation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

const configuration = KakaoMapConfiguration(javascriptKey: 'test-only');
const a = <String, dynamic>{
  'place_id': 'test:a',
  'name': '첫 장소',
  'address': '충남 아산시 첫 길',
  'lat': '36.78055',
  'lng': '127.00316',
};
const b = <String, dynamic>{
  'place_id': 'test:b',
  'name': '두 번째 장소',
  'address': '충남 아산시 둘째 길',
  'lat': 36.7918,
  'lng': 127.006,
};

class FakeSession implements CourseMapSession {
  final ValueChanged<String> onMessage;
  final VoidCallback onFailure;
  String html = '';
  String origin = '';
  Map<String, dynamic> payload = {};
  bool closed = false;
  int viewportReconciliations = 0;
  final bool readyOnLoad;
  FakeSession(this.onMessage, this.onFailure, {this.readyOnLoad = false});

  @override
  Future<void> load(String html, String origin) async {
    this.html = html;
    this.origin = origin;
    final json = RegExp(r'let state=(.*?), map=null').firstMatch(html)![1]!;
    payload = jsonDecode(json) as Map<String, dynamic>;
    emit('document');
    if (readyOnLoad) emit('ready');
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
  }

  void emit(String type, {int? index, int? revision}) => onMessage(
    jsonEncode({
      'type': type,
      'revision': revision ?? payload['revision'],
      if (index != null) 'index': index,
    }),
  );

  @override
  Widget buildView() =>
      const ColoredBox(key: ValueKey('fake-map'), color: Color(0xFFEEEEEE));

  @override
  Future<void> close() async => closed = true;
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('coordinate restrictions preserve original visit numbers', () {
    final stops = courseMapStops([
      a,
      {
        ...b,
        'coordinate_quality': {'map_coordinate_eligible': false},
      },
      b,
      {...a, 'lat': 'NaN'},
      {...a, 'lat': 91},
      {...a, 'lng': -181},
      {...a, 'lat': 0, 'lng': 0},
      {
        ...a,
        'coordinate_quality': {'status': 'blocked'},
      },
      {...a, 'lat': null},
    ]);
    expect(stops.map((s) => s.index), [0, 2]);
    expect(stops.map((s) => s.toJson()['sequence']), [1, 3]);
    expect(stops.first.lat, 36.78055);
    expect(const KakaoMapConfiguration().isConfigured, isFalse);
    for (final origin in [
      'http://localhost',
      'https://a/b',
      'data:foo',
      'https://user:secret@a',
      'https://a?secret=x',
    ]) {
      expect(
        KakaoMapConfiguration(javascriptKey: 'x', origin: origin).isConfigured,
        isFalse,
      );
    }
    expect(configuration.isConfigured, isTrue);
  });

  test('place names cannot close scripts or become overlay markup', () {
    const name = '</script><img src=x onerror=alert(1)>';
    final html = courseMapDocument(
      javascriptKey: 'test-only',
      payload: courseMapPayload(
        stops: courseMapStops([
          {...a, 'name': name},
        ]),
        selectedIndex: null,
        revision: 1,
      ),
    );
    expect(html, isNot(contains(name)));
    expect(html, contains(r'\u003c/script\u003e'));
    expect(html, contains('label.textContent=String(stop.sequence)'));
    for (final text in [
      '방문 3곳',
      '방문 순서대로 표시',
      '점선은 방문 순서예요',
      '지도 배치 미리보기',
      '이 순서로 들러보세요',
    ]) {
      expect(html, isNot(contains(text)));
    }
  });

  test(
    'identical visits keep real coordinates and original numbers for every leg',
    () {
      final places = [
        for (var index = 0; index < 5; index++)
          {...a, 'name': '같은 위치 ${index + 1}'},
      ];
      final payload = courseMapPayload(
        stops: courseMapStops(places),
        selectedIndex: 3,
        revision: 7,
      );
      final stops = (payload['stops'] as List).cast<Map<String, dynamic>>();
      expect(stops.map((stop) => stop['index']), [0, 1, 2, 3, 4]);
      expect(stops.map((stop) => stop['sequence']), [1, 2, 3, 4, 5]);
      expect(
        stops.every(
          (stop) => stop['lat'] == 36.78055 && stop['lng'] == 127.00316,
        ),
        true,
      );
      expect(payload['selectedIndex'], 3);
      final html = courseMapDocument(
        javascriptKey: 'test-only',
        payload: payload,
      );
      expect(courseMapHasLeg(courseMapStops(places), 3), true);
      expect(
        courseMapPayload(
          stops: courseMapStops(places),
          selectedIndex: 3,
          revision: 8,
          selectedLeg: 3,
        )['selectedLeg'],
        3,
      );
      expect(
        courseMapPayload(
          stops: courseMapStops(places),
          selectedIndex: 3,
          revision: 8,
          selectedLeg: 4,
        )['selectedLeg'],
        isNull,
      );
      expect(html, contains('visibleStops().forEach(stop=>'));
      expect(
        html,
        contains(
          'stop.index===state.selectedLeg||stop.index===state.selectedLeg+1',
        ),
      );
      for (final removed in [
        'visit-leader',
        'visit-pin-leader',
        'getBoundingClientRect',
        "className='stack'",
        'gridTemplateColumns',
        'stop-group',
        'picker',
      ]) {
        expect(html, isNot(contains(removed)), reason: removed);
      }
      expect(html, contains("['visit-route','#914b33','5.6']"));
      expect(html, contains("stroke-dasharray','7 6'"));
    },
  );

  testWidgets('missing configuration and coordinates leave the list usable', (
    tester,
  ) async {
    var creations = 0;
    CourseMapSession factory(
      ValueChanged<String> message,
      VoidCallback failure,
    ) {
      creations++;
      return FakeSession(message, failure);
    }

    await tester.pumpWidget(
      MaterialApp(
        home: CourseResultScreen(
          courses: const [
            [a, b],
          ],
          requestedCount: 1,
          mapSessionFactory: factory,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(creations, 0);
    expect(find.text('첫 장소'), findsOneWidget);
    expect(find.text('두 번째 장소'), findsOneWidget);
    expect(find.text('지도 다시 시도'), findsNothing);
    expect(find.byType(CircularProgressIndicator), findsNothing);
    await tester.pumpWidget(
      MaterialApp(
        home: CourseResultScreen(
          courses: [
            [
              {...a, 'lat': null},
              {
                ...b,
                'coordinate_quality': {'status': 'blocked'},
              },
            ],
          ],
          requestedCount: 1,
          mapConfiguration: configuration,
          mapSessionFactory: factory,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(creations, 0);
    expect(find.text('첫 장소'), findsOneWidget);
    expect(find.text('두 번째 장소'), findsOneWidget);
  });

  testWidgets(
    'bridge validates visits, revisions, timeout and retry sessions',
    (tester) async {
      final sessions = <FakeSession>[];
      final selections = <int>[];
      CourseMapSession factory(
        ValueChanged<String> message,
        VoidCallback failure,
      ) {
        final session = FakeSession(message, failure);
        sessions.add(session);
        return session;
      }

      Widget panel(int? selection) => MaterialApp(
        home: Scaffold(
          body: CourseMapPanel(
            places: [
              a,
              {...b, 'lat': null},
              b,
            ],
            selectedIndex: selection,
            onSelect: selections.add,
            configuration: configuration,
            sessionFactory: factory,
            loadTimeout: const Duration(milliseconds: 100),
          ),
        ),
      );
      await tester.pumpWidget(panel(null));
      await tester.pump();
      final first = sessions.single;
      expect(first.origin, 'https://localhost');
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      first.emit('select', index: 1);
      first.emit('select', index: 2, revision: -1);
      first.onMessage('not json');
      expect(selections, isEmpty);
      first.emit('ready');
      first.emit('select', index: 2);
      await tester.pump();
      expect(selections, [2]);
      expect(find.byType(CircularProgressIndicator), findsNothing);
      final previousRevision = first.payload['revision'] as int;
      await tester.pumpWidget(panel(0));
      await tester.pump();
      expect(first.payload['selectedIndex'], 0);
      expect(first.payload['revision'], greaterThan(previousRevision));
      first.emit('error', revision: previousRevision);
      await tester.pump();
      expect(find.text('지도 다시 시도'), findsNothing);
      first.onFailure();
      await tester.pump();
      expect(first.closed, isTrue);
      expect(find.text('지도 다시 시도'), findsOneWidget);
      first.emit('ready');
      await tester.pump();
      expect(find.text('지도 다시 시도'), findsOneWidget);
      await tester.tap(find.text('지도 다시 시도'));
      await tester.pump();
      expect(first.closed, isTrue);
      expect(sessions.length, 2);
      first.emit('select', index: 0);
      expect(selections, [2]);
      await tester.pump(const Duration(milliseconds: 101));
      expect(find.text('지도 다시 시도'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      sessions.last.emit('ready');
      expect(sessions.last.closed, isTrue);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('map and cards synchronize per course without altering saves', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final third = {...a, 'place_id': 'test:c', 'name': '세 번째 장소', 'lat': 36.77};
    final nextCourse = [
      {
        ...a,
        'place_id': 'test:d',
        'name': '다른 코스 첫 장소',
        'lat': 36.81,
        'lng': 127.14,
      },
      {
        ...a,
        'place_id': 'test:e',
        'name': '다른 코스 둘째 장소',
        'lat': 36.82,
        'lng': 127.15,
      },
      {
        ...a,
        'place_id': 'test:f',
        'name': '다른 코스 셋째 장소',
        'lat': 36.83,
        'lng': 127.16,
      },
    ];
    final sessions = <FakeSession>[];
    CourseMapSession factory(
      ValueChanged<String> message,
      VoidCallback failure,
    ) {
      final session = FakeSession(message, failure, readyOnLoad: true);
      sessions.add(session);
      return session;
    }

    await tester.pumpWidget(
      MaterialApp(
        home: CourseResultScreen(
          courses: [
            [a, b, third],
            nextCourse,
          ],
          requestedCount: 2,
          courseMetrics: const [
            {'estimated_distance_km': 1.9},
            {'estimated_distance_km': 2.4},
          ],
          region: '아산',
          mapConfiguration: configuration,
          mapSessionFactory: factory,
        ),
      ),
    );
    await tester.pump();
    final first = sessions.first;
    for (final session in sessions) {
      session.emit('ready');
    }
    await tester.pumpAndSettle();
    expect(sessions.where((session) => !session.closed).length, 1);
    expect(
      tester.getRect(find.byKey(const ValueKey('fake-map')).first).width,
      390,
    );
    expect(find.text('출발점 포함 · 직선거리 추정'), findsNothing);
    final distanceRect = tester.getRect(find.text('약 1.9 km'));
    final compareRect = tester.getRect(find.text('코스 비교').first);
    expect((distanceRect.center.dy - compareRect.center.dy).abs(), lessThan(8));

    first.emit('select', index: 1);
    await tester.pumpAndSettle();
    var timeline = tester.widget<CourseTimeline>(
      find.byType(CourseTimeline).first,
    );
    expect(timeline.selectedIndex, 1);
    await tester.tap(find.text('첫 장소'));
    await tester.pumpAndSettle();
    expect(first.payload['selectedIndex'], 0);
    await tester.tap(find.byIcon(Icons.bookmark_outline_rounded));
    await tester.pumpAndSettle();
    final saved = (await LocalStorageService.getSavedCourses()).single;
    expect((saved['spots'] as List).map((p) => p['place_id']), [
      'test:a',
      'test:b',
      'test:c',
    ]);
    expect(saved['spots'][0].containsKey('selectedIndex'), isFalse);
    await tester.tap(find.text('코스 2'));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump();
    for (final session in sessions) {
      session.emit('ready');
    }
    await tester.pumpAndSettle();
    timeline = tester.widget<CourseTimeline>(find.byType(CourseTimeline).last);
    expect(timeline.places.map((p) => p['place_id']), [
      'test:d',
      'test:e',
      'test:f',
    ]);
    expect(timeline.selectedIndex, isNull);
    expect(sessions.last.payload['stops'].length, 3);
    expect(sessions.last.payload['stops'].map((p) => p['name']), [
      '다른 코스 첫 장소',
      '다른 코스 둘째 장소',
      '다른 코스 셋째 장소',
    ]);
    expect(first.closed, isTrue);
    expect(sessions.where((session) => !session.closed).length, 1);
    final second = sessions.last;
    first.emit('select', index: 1);
    first.emit('error');
    first.emit('ready');
    await tester.pumpAndSettle();
    expect(second.payload['selectedIndex'], isNull);
    expect(find.text('지도 다시 시도'), findsNothing);
    await tester.tap(find.text('코스 1'));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump();
    sessions.last.emit('ready');
    await tester.pumpAndSettle();
    expect(second.closed, isTrue);
    expect(sessions.where((session) => !session.closed).length, 1);
    expect(sessions.last, isNot(same(first)));
    expect(sessions.last.payload['stops'].length, 3);
    expect(sessions.last.payload['selectedIndex'], 0);
    second.emit('select', index: 0);
    first.emit('select', index: 1);
    await tester.pumpAndSettle();
    expect(sessions.last.payload['selectedIndex'], 0);
    expect(find.text('이 순서로 들러보세요'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'whole course preserves all pins and rejects stale events without another route request',
    (tester) async {
      final sessions = <FakeSession>[];
      final selections = <int>[];
      var requests = 0;
      final places = [
        a,
        b,
        {...a, 'name': '셋째 장소', 'lat': 36.82},
      ];
      CourseMapSession factory(
        ValueChanged<String> message,
        VoidCallback failure,
      ) {
        final session = FakeSession(message, failure, readyOnLoad: true);
        sessions.add(session);
        return session;
      }

      Future<CourseRouteData> loader({
        required String mode,
        required List<CourseMapStop> stops,
        required RequestCancellation cancellation,
      }) async {
        requests++;
        return CourseRouteData.unavailable(mode);
      }

      Widget panel(int? selection) => MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: CourseMapPanel(
              places: places,
              selectedIndex: selection,
              onSelect: selections.add,
              configuration: configuration,
              sessionFactory: factory,
              routeLoader: loader,
            ),
          ),
        ),
      );
      await tester.pumpWidget(panel(null));
      await tester.pumpAndSettle();
      final session = sessions.single;
      expect(find.byKey(const ValueKey('course-map-leg-all')), findsNothing);
      expect(find.text('1 → 2'), findsNothing);
      expect(find.text('2 → 3'), findsNothing);
      expect(session.payload['selectedLeg'], isNull);
      session.emit('select', index: 2);
      expect(selections, [2]);
      final revision = session.payload['revision'] as int;
      await tester.pumpWidget(panel(2));
      await tester.pump();
      session.emit('select', index: 0, revision: revision);
      expect(selections, [2]);
      session.emit('select', index: 0);
      expect(selections, [2, 0]);
      session.emit('overview');
      await tester.pump();
      expect(session.payload['selectedLeg'], isNull);
      expect(session.payload['selectedIndex'], 2);
      expect(session.payload['stops'].length, 3);
      expect(requests, 1);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'five visits remain together without leg controls at 320 with large text',
    (tester) async {
      tester.view.physicalSize = const Size(320, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      late FakeSession session;
      final places = [
        for (var index = 0; index < 5; index++)
          {...a, 'name': '방문 ${index + 1}'},
      ];
      Future<CourseRouteData> loader({
        required String mode,
        required List<CourseMapStop> stops,
        required RequestCancellation cancellation,
      }) async => CourseRouteData.unavailable(mode);
      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(
              context,
            ).copyWith(textScaler: const TextScaler.linear(2.2)),
            child: child!,
          ),
          home: Scaffold(
            body: SingleChildScrollView(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: CourseMapPanel(
                  places: places,
                  selectedIndex: 2,
                  onSelect: (_) {},
                  configuration: configuration,
                  sessionFactory: (message, failure) => session = FakeSession(
                    message,
                    failure,
                    readyOnLoad: true,
                  ),
                  routeLoader: loader,
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester.getSize(find.byKey(const ValueKey('fake-map'))).height,
        240,
      );
      expect(find.byKey(const ValueKey('course-map-leg-all')), findsNothing);
      expect(find.text('1 → 2'), findsNothing);
      expect(session.payload['selectedLeg'], isNull);
      expect(session.payload['selectedIndex'], 2);
      expect(session.payload['stops'].length, 5);
      expect(session.payload['stops'].map((stop) => stop['sequence']), [
        1,
        2,
        3,
        4,
        5,
      ]);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'missing coordinates preserve numbering and old events cannot select a replacement course',
    (tester) async {
      final sessions = <FakeSession>[];
      CourseMapSession factory(
        ValueChanged<String> message,
        VoidCallback failure,
      ) {
        final session = FakeSession(message, failure, readyOnLoad: true);
        sessions.add(session);
        return session;
      }

      Future<CourseRouteData> loader({
        required String mode,
        required List<CourseMapStop> stops,
        required RequestCancellation cancellation,
      }) async => CourseRouteData.unavailable(mode);
      Widget panel(List<Map<String, dynamic>> places) => MaterialApp(
        home: Scaffold(
          body: CourseMapPanel(
            places: places,
            selectedIndex: null,
            onSelect: (_) {},
            configuration: configuration,
            sessionFactory: factory,
            routeLoader: loader,
          ),
        ),
      );
      final places = [
        a,
        {...b, 'lat': null},
        b,
        {...a, 'name': '넷째'},
      ];
      await tester.pumpWidget(panel(places));
      await tester.pumpAndSettle();
      expect(sessions.single.payload['stops'].map((stop) => stop['sequence']), [
        1,
        3,
        4,
      ]);
      expect(sessions.single.payload['selectedLeg'], isNull);
      final revision = sessions.single.payload['revision'] as int;
      await tester.pumpWidget(
        panel([
          a,
          b,
          {...a, 'name': '새 셋째'},
          {...b, 'name': '새 넷째'},
        ]),
      );
      await tester.pumpAndSettle();
      expect(sessions.single.payload['selectedLeg'], isNull);
      sessions.single.emit('select', index: 2, revision: revision);
      await tester.pump();
      expect(sessions.single.payload['selectedLeg'], isNull);
      expect(courseMapHasLeg(courseMapStops(places), 0), false);
      expect(courseMapHasLeg(courseMapStops(places), 2), true);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'whole course keeps partial route failure visible and retries without losing pins',
    (tester) async {
      final places = [
        a,
        b,
        {...a, 'name': '셋째', 'lat': 36.82},
      ];
      final stops = courseMapStops(places);
      final route = CourseRouteData.parse(
        {
          'success': true,
          'data': {
            'mode': 'transit',
            'status': 'partial',
            'segments': [
              {
                'fromIndex': 0,
                'toIndex': 1,
                'status': 'ready',
                'paths': [
                  {
                    'mode': 'walk',
                    'points': [
                      [stops[0].lng, stops[0].lat],
                      [stops[1].lng, stops[1].lat],
                    ],
                  },
                ],
              },
              {
                'fromIndex': 1,
                'toIndex': 2,
                'status': 'unavailable',
                'reason': 'no_route',
                'paths': [],
              },
            ],
          },
        },
        mode: 'transit',
        stops: stops,
      );
      late FakeSession session;
      var requests = 0;
      Future<CourseRouteData> loader({
        required String mode,
        required List<CourseMapStop> stops,
        required RequestCancellation cancellation,
      }) async {
        requests++;
        return route;
      }

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CourseMapPanel(
              places: places,
              selectedIndex: null,
              onSelect: (_) {},
              configuration: configuration,
              sessionFactory: (message, failure) =>
                  session = FakeSession(message, failure, readyOnLoad: true),
              routeLoader: loader,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('경로 다시 시도'), findsOneWidget);
      expect(session.payload['selectedLeg'], isNull);
      expect(session.payload['stops'].length, 3);
      expect(session.payload['route']['segments'][1]['paths'], isEmpty);
      expect(requests, 1);
      await tester.tap(find.text('경로 다시 시도'));
      await tester.pumpAndSettle();
      expect(requests, 2);
      expect(session.payload['stops'].length, 3);
      expect(find.text('경로 다시 시도'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'a single visit keeps its map without empty leg controls or route requests',
    (tester) async {
      var requests = 0;
      Future<CourseRouteData> loader({
        required String mode,
        required List<CourseMapStop> stops,
        required RequestCancellation cancellation,
      }) async {
        requests++;
        return CourseRouteData.unavailable(mode);
      }

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CourseMapPanel(
              places: [a],
              selectedIndex: 0,
              onSelect: (_) {},
              configuration: configuration,
              sessionFactory: (message, failure) =>
                  FakeSession(message, failure, readyOnLoad: true),
              routeLoader: loader,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('course-map-leg-all')), findsNothing);
      expect(
        tester.getSize(find.byKey(const ValueKey('fake-map'))).height,
        320,
      );
      expect(requests, 0);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'first visible WebView gets one viewport reconciliation after ready, never on normal controls or duplicate ready',
    (tester) async {
      final sessions = <FakeSession>[];
      var requests = 0;
      CourseMapSession factory(
        ValueChanged<String> message,
        VoidCallback failure,
      ) {
        final session = FakeSession(message, failure);
        sessions.add(session);
        return session;
      }

      Future<CourseRouteData> loader({
        required String mode,
        required List<CourseMapStop> stops,
        required RequestCancellation cancellation,
      }) async {
        requests++;
        return CourseRouteData.unavailable(mode);
      }

      Widget panel(int? selection) => MaterialApp(
        home: Scaffold(
          body: CourseMapPanel(
            places: [a, b],
            selectedIndex: selection,
            onSelect: (_) {},
            configuration: configuration,
            sessionFactory: factory,
            routeLoader: loader,
          ),
        ),
      );
      await tester.pumpWidget(panel(null));
      await tester.pump();
      final first = sessions.single;
      expect(first.viewportReconciliations, 0);
      first.emit('ready');
      expect(first.viewportReconciliations, 0);
      await tester.pump();
      expect(first.viewportReconciliations, 1);
      first.emit('ready');
      first.emit('document');
      await tester.pump();
      await tester.pumpWidget(panel(1));
      await tester.pump();
      first.emit('overview');
      await tester.pump();
      expect(first.viewportReconciliations, 1);
      expect(requests, 1);
      first.emit('error');
      await tester.pump();
      await tester.tap(find.text('지도 다시 시도'));
      await tester.pump();
      final second = sessions.last;
      expect(second, isNot(same(first)));
      expect(second.viewportReconciliations, 0);
      second.emit('ready');
      await tester.pump();
      expect(second.viewportReconciliations, 1);
      first.emit('ready');
      await tester.pump();
      expect(first.viewportReconciliations, 1);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'a discarded ready session cannot send its queued viewport recovery',
    (tester) async {
      late FakeSession session;
      Future<CourseRouteData> loader({
        required String mode,
        required List<CourseMapStop> stops,
        required RequestCancellation cancellation,
      }) async => CourseRouteData.unavailable(mode);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CourseMapPanel(
              places: [a, b],
              selectedIndex: null,
              onSelect: (_) {},
              configuration: configuration,
              sessionFactory: (message, failure) =>
                  session = FakeSession(message, failure),
              routeLoader: loader,
            ),
          ),
        ),
      );
      await tester.pump();
      session.emit('ready');
      await tester.pumpWidget(const SizedBox());
      expect(session.viewportReconciliations, 0);
      expect(session.closed, true);
      expect(tester.takeException(), isNull);
    },
  );
}
