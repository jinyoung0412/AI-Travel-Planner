import 'dart:async';
import 'package:ai_travel_app/place_map_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const channel = MethodChannel('plugins.flutter.io/url_launcher');
  final calls = <MethodCall>[];
  late bool appAvailable;
  late bool launchSucceeds;
  setUp(() {
    appAvailable = false;
    launchSucceeds = true;
    calls.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          if (call.method == 'canLaunch') return appAvailable;
          return launchSucceeds;
        });
  });
  tearDown(
    () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null),
  );
  Future<void> mount(
    WidgetTester tester, {
    PlaceDetailLookup? lookup,
    Map<String, dynamic>? place,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PlaceMapButton(
            place:
                place ??
                {
                  'name': '선택한 지점',
                  'address': '충남 천안시 1',
                  'lat': '36.8',
                  'lng': '127.1',
                },
            lookupDetail: lookup != null,
            detailLookup: lookup,
          ),
        ),
      ),
    );
  }

  String url(MethodCall call) => (call.arguments as Map)['url'] as String;
  testWidgets(
    'unresolved detail falls back to selected coordinates and web map',
    (tester) async {
      await mount(
        tester,
        lookup: (place) async {
          expect(place.address, '충남 천안시 1');
          return null;
        },
      );
      await tester.tap(find.byType(TextButton));
      await tester.pumpAndSettle();
      expect(url(calls.first), 'kakaomap://look?p=36.8,127.1');
      expect(calls.last.method, 'launch');
      expect(url(calls.last), contains('https://map.kakao.com/link/map/'));
      expect(url(calls.last), endsWith(',36.8,127.1'));
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets('existing map app opens selected pin without a web launch', (
    tester,
  ) async {
    appAvailable = true;
    await mount(tester);
    await tester.tap(find.byType(TextButton));
    await tester.pumpAndSettle();
    expect(calls.where((c) => c.method == 'launch').length, 1);
    expect(url(calls.last), startsWith('kakaomap:'));
  });
  testWidgets(
    'double tap and disposed detail completion do not launch another map',
    (tester) async {
      final detail = Completer<String?>();
      var lookups = 0;
      await mount(
        tester,
        lookup: (_) {
          lookups++;
          return detail.future;
        },
      );
      await tester.tap(find.byType(TextButton));
      await tester.tap(find.byType(TextButton));
      expect(lookups, 1);
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      detail.complete('https://place.map.kakao.com/1');
      await tester.pumpAndSettle();
      expect(calls, isEmpty);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets('launch refusal and missing coordinates show a handled error', (
    tester,
  ) async {
    launchSucceeds = false;
    await mount(tester);
    await tester.tap(find.byType(TextButton));
    await tester.pumpAndSettle();
    expect(find.textContaining('지도를 열 수 없어요'), findsOneWidget);
    expect(tester.takeException(), isNull);
    calls.clear();
    await mount(tester, place: {'name': '위치 없음'});
    await tester.tap(find.byType(TextButton));
    await tester.pumpAndSettle();
    expect(calls, isEmpty);
    expect(tester.takeException(), isNull);
  });
}
