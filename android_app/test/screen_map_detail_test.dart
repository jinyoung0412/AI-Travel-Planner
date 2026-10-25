import 'dart:convert';

import 'package:ai_travel_app/course_result_screen.dart';
import 'package:ai_travel_app/local_storage_service.dart';
import 'package:ai_travel_app/saved_screen.dart';
import 'package:ai_travel_app/spot_result_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  const channel = MethodChannel('plugins.flutter.io/url_launcher');
  final requests = <http.Request>[];
  final launches = <String>[];
  String? resolvedUrl;
  var responseStatus = 200;
  final client = MockClient((request) async {
    requests.add(request);
    return http.Response(
      jsonEncode({'place_url': resolvedUrl}),
      responseStatus,
    );
  });

  setUp(() {
    requests.clear();
    launches.clear();
    resolvedUrl = 'https://place.map.kakao.com/117300047';
    responseStatus = 200;
    SharedPreferences.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method == 'launch') {
            launches.add((call.arguments as Map)['url'] as String);
            return true;
          }
          return false;
        });
  });
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  Map<String, dynamic> stop({bool blocked = false, String? storedUrl}) => {
    'place_id': 'naver:detail-regression',
    'name': '천안삼거리공원',
    'address': '충남 천안시 동남구 충절로 410',
    'lat': 36.81083006,
    'lng': 127.1488888,
    if (storedUrl != null) 'kakao_url': storedUrl,
    if (blocked)
      'coordinate_quality': {
        'status': 'blocked',
        'map_coordinate_eligible': false,
      },
  };

  Future<Finder> mount(
    WidgetTester tester,
    String screen,
    Map<String, dynamic> place,
  ) async {
    late Widget home;
    switch (screen) {
      case 'spot result':
        home = SpotResultScreen(places: [place], requestedCount: 1);
      case 'course result':
        home = CourseResultScreen(
          courses: [
            [place],
          ],
          requestedCount: 1,
        );
      case 'saved spot':
        await LocalStorageService.saveSpot(place);
        home = const SavedScreen();
      case 'saved course':
        await LocalStorageService.saveCourse('천안 회귀 코스', [place]);
        home = const SavedScreen();
    }
    await tester.pumpWidget(MaterialApp(home: home));
    await tester.pumpAndSettle();
    if (screen == 'saved course') {
      await tester.tap(find.text('코스 (1)'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('천안 회귀 코스'));
      await tester.pumpAndSettle();
    }
    final target = screen == 'saved spot'
        ? find.text(place['name'] as String)
        : find.text('카카오맵에서 보기');
    await tester.ensureVisible(target);
    await tester.pumpAndSettle();
    return target;
  }

  Future<String> storedData() async {
    final prefs = await SharedPreferences.getInstance();
    return jsonEncode({for (final key in prefs.getKeys()) key: prefs.get(key)});
  }

  Future<void> finishLaunch(WidgetTester tester) async {
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
  }

  for (final screen in [
    'spot result',
    'course result',
    'saved spot',
    'saved course',
  ]) {
    testWidgets(
      '$screen resolves a Kakao identity before blocked coordinates',
      (tester) async {
        await http.runWithClient(() async {
          final place = stop(blocked: true);
          final original = jsonEncode(place);
          final target = await mount(tester, screen, place);
          final before = await storedData();
          await tester.tap(target);
          await finishLaunch(tester);
          expect(requests, hasLength(1));
          expect(requests.single.method, 'GET');
          expect(requests.single.url.path, '/kakao/place');
          expect(requests.single.url.queryParameters, {
            'name': place['name'],
            'address': place['address'],
            'lat': place['lat'].toString(),
            'lng': place['lng'].toString(),
          });
          expect(launches, ['https://place.map.kakao.com/117300047']);
          expect(find.byType(AlertDialog), findsNothing);
          expect(await storedData(), before);
          expect(jsonEncode(place), original);
          expect(tester.takeException(), isNull);
        }, () => client);
      },
    );

    testWidgets('$screen preserves stored detail without a network lookup', (
      tester,
    ) async {
      await http.runWithClient(() async {
        // A provider outage must not discard a known destination.
        resolvedUrl = null;
        responseStatus = 503;
        final place = stop(
          blocked: true,
          storedUrl: 'http://place.map.kakao.com/12345',
        );
        final target = await mount(tester, screen, place);
        final before = await storedData();
        await tester.tap(target);
        await finishLaunch(tester);
        expect(requests, isEmpty);
        expect(launches, ['https://place.map.kakao.com/12345']);
        expect(find.byType(AlertDialog), findsNothing);
        expect(await storedData(), before);
        expect(tester.takeException(), isNull);
      }, () => client);
    });

    testWidgets('$screen requires cancellable consent after lookup failure', (
      tester,
    ) async {
      await http.runWithClient(() async {
        resolvedUrl = null;
        responseStatus = 503;
        final target = await mount(tester, screen, stop());
        final before = await storedData();
        await tester.tap(target);
        // The map button keeps its busy indicator while consent is pending.
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));
        expect(requests, hasLength(1));
        expect(find.byType(AlertDialog), findsOneWidget);
        expect(launches, isEmpty);
        await tester.tap(find.text('취소'));
        await tester.pumpAndSettle();
        expect(launches, isEmpty);
        expect(await storedData(), before);
        // Cancelling releases the shared lock so the same screen can retry.
        resolvedUrl = 'https://place.map.kakao.com/42';
        responseStatus = 200;
        await tester.tap(target);
        await finishLaunch(tester);
        expect(requests, hasLength(2));
        expect(launches, ['https://place.map.kakao.com/42']);
        expect(tester.takeException(), isNull);
      }, () => client);
    });
  }
}
