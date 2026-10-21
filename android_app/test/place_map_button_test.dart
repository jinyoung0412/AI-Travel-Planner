import 'dart:async';
import 'dart:convert';
import 'package:ai_travel_app/place_map_button.dart';
import 'package:ai_travel_app/local_storage_service.dart';
import 'package:ai_travel_app/saved_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  const channel = MethodChannel('plugins.flutter.io/url_launcher');
  final calls = <MethodCall>[];
  late bool appAvailable;
  late bool launchSucceeds;
  Future<bool> Function()? launchHandler;
  setUp(() {
    appAvailable = false;
    launchSucceeds = true;
    launchHandler = null;
    SharedPreferences.setMockInitialValues({});
    calls.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          if (call.method == 'canLaunch') return appAvailable;
          return launchHandler != null
              ? await launchHandler!()
              : launchSucceeds;
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
  Future<void> confirmCoordinates(WidgetTester tester) async {
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.textContaining('실제 장소와 일치하는지 확인되지 않았어요'), findsOneWidget);
    await tester.tap(find.text('참고 위치 열기').last);
  }

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
      await confirmCoordinates(tester);
      await tester.pumpAndSettle();
      expect(url(calls.first), 'kakaomap://look?p=36.8,127.1');
      expect(calls.last.method, 'launch');
      expect(url(calls.last), 'https://map.kakao.com/link/map/36.8,127.1');
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets('existing map app opens selected pin without a web launch', (
    tester,
  ) async {
    appAvailable = true;
    await mount(tester);
    await tester.tap(find.byType(TextButton));
    await confirmCoordinates(tester);
    await tester.pumpAndSettle();
    expect(calls.where((c) => c.method == 'launch').length, 1);
    expect(url(calls.last), startsWith('kakaomap:'));
  });

  for (final name in [
    '천안삼거리공원도시,테마공원',
    'QA 동명 장소',
    '한글 공원 / 전망대 #1?안내=참고&층=2',
    '쉼터%2C표지, 남문',
  ]) {
    testWidgets('web coordinate destination is independent of label: $name', (
      tester,
    ) async {
      final place = <String, dynamic>{
        'place_id':
            'local:v1:7d62a6f7966ee9a2f08d2e3a3236668d1123893742ce1c122d6c1a5fbfb1db44',
        'name': name,
        'source_name': name,
        'address': '충남 천안시 동남구',
        'lat': 36.81083006,
        'lng': 127.1488888,
      };
      final original = jsonEncode(place);
      await mount(
        tester,
        place: place,
        lookup: (data) async {
          expect(data.name, name);
          expect(data.address, place['address']);
          return null;
        },
      );
      await tester.tap(find.byType(TextButton));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(calls, isEmpty);
      expect(find.textContaining(name), findsOneWidget);
      await confirmCoordinates(tester);
      await tester.pumpAndSettle();
      final launches = calls.where((call) => call.method == 'launch').toList();
      expect(launches, hasLength(1));
      expect(
        url(launches.single),
        'https://map.kakao.com/link/map/36.81083006,127.1488888',
      );
      expect(jsonEncode(place), original);
      expect(tester.takeException(), isNull);
    });
  }
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
    await confirmCoordinates(tester);
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

  testWidgets(
    'rapid taps after dispatch and delayed transition issue one detail lookup and launch',
    (tester) async {
      var lookups = 0;
      await mount(
        tester,
        lookup: (_) async {
          lookups++;
          return 'https://place.map.kakao.com/117300047';
        },
      );
      await tester.tap(find.byType(TextButton));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 318));
      await tester.tap(find.byType(TextButton));
      await tester.pump(const Duration(milliseconds: 318));
      await tester.tap(find.byType(TextButton));
      expect(lookups, 1);
      expect(calls.where((call) => call.method == 'launch').length, 1);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump(const Duration(seconds: 3));
      expect(
        tester.widget<TextButton>(find.byType(TextButton)).onPressed,
        isNull,
      );
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      await tester.tap(find.byType(TextButton));
      await tester.pumpAndSettle();
      expect(lookups, 2);
      expect(calls.where((call) => call.method == 'launch').length, 2);
    },
  );

  testWidgets(
    'missing lifecycle events unlock retry after the bounded transition guard',
    (tester) async {
      await mount(tester, lookup: (_) async => 'https://place.map.kakao.com/1');
      await tester.tap(find.byType(TextButton));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(
        tester.widget<TextButton>(find.byType(TextButton)).onPressed,
        isNull,
      );
      await tester.pump(const Duration(seconds: 2));
      await tester.pump();
      expect(
        tester.widget<TextButton>(find.byType(TextButton)).onPressed,
        isNotNull,
      );
      await tester.tap(find.byType(TextButton));
      await tester.pumpAndSettle();
      expect(calls.where((call) => call.method == 'launch').length, 2);
    },
  );

  testWidgets(
    'slow launch and return before completion remain locked until completion',
    (tester) async {
      final completion = Completer<bool>();
      launchHandler = () => completion.future;
      await mount(tester, lookup: (_) async => 'https://place.map.kakao.com/1');
      await tester.tap(find.byType(TextButton));
      await tester.pump();
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.tap(find.byType(TextButton));
      expect(calls.where((call) => call.method == 'launch').length, 1);
      completion.complete(true);
      await tester.pumpAndSettle();
      expect(
        tester.widget<TextButton>(find.byType(TextButton)).onPressed,
        isNotNull,
      );
    },
  );

  testWidgets(
    'timed out platform dispatch does not launch fallback and permits retry',
    (tester) async {
      final completion = Completer<bool>();
      launchHandler = () => completion.future;
      await mount(tester, lookup: (_) async => 'https://place.map.kakao.com/1');
      await tester.tap(find.byType(TextButton));
      await tester.pump();
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
      expect(calls.where((call) => call.method == 'launch').length, 1);
      expect(find.textContaining('지도를 열 수 없어요'), findsOneWidget);
      completion.complete(true);
      launchHandler = null;
      await tester.tap(find.byType(TextButton));
      await tester.pumpAndSettle();
      expect(calls.where((call) => call.method == 'launch').length, 2);
    },
  );

  testWidgets(
    'lookup timeout shows unverified coordinate choice and cancellation unlocks',
    (tester) async {
      final detail = Completer<String?>();
      await mount(tester, lookup: (_) => detail.future);
      await tester.tap(find.byType(TextButton));
      await tester.pump(const Duration(seconds: 36));
      await tester.pump(const Duration(milliseconds: 300));
      expect(calls, isEmpty);
      await tester.tap(find.text('취소'));
      await tester.pumpAndSettle();
      detail.complete('https://place.map.kakao.com/1');
      await tester.pump();
      expect(calls, isEmpty);
      expect(
        tester.widget<TextButton>(find.byType(TextButton)).onPressed,
        isNotNull,
      );
    },
  );

  testWidgets(
    'coordinate confirmation applies to concrete addresses and never changes coordinates',
    (tester) async {
      final place = {
        'name': '기존 저장 공원',
        'address': '충남 천안시 충절로 410',
        'lat': 36.81083006,
        'lng': 127.1488888,
      };
      await mount(tester, place: place);
      await tester.tap(find.byType(TextButton));
      await confirmCoordinates(tester);
      await tester.pumpAndSettle();
      expect(
        url(calls.last),
        'https://map.kakao.com/link/map/36.81083006,127.1488888',
      );
      expect(place['lat'], 36.81083006);
    },
  );

  testWidgets(
    'saved direct card path shares launch lock across all cards and restores on resume',
    (tester) async {
      for (final id in [1, 2]) {
        await LocalStorageService.saveSpot({
          'place_id': 'naver:$id',
          'name': '저장 $id',
          'kakao_url': 'https://place.map.kakao.com/$id',
        });
      }
      await tester.pumpWidget(const MaterialApp(home: SavedScreen()));
      await tester.pumpAndSettle();
      await tester.tap(find.text('저장 1'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 318));
      await tester.tap(find.text('저장 2'));
      await tester.pump();
      expect(calls.where((call) => call.method == 'launch').length, 1);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump(const Duration(seconds: 3));
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      await tester.tap(find.text('저장 2'));
      await tester.pump(const Duration(seconds: 2));
      await tester.pumpAndSettle();
      expect(calls.where((call) => call.method == 'launch').length, 2);
    },
  );

  testWidgets('disposed pending launcher cannot block a fresh screen', (
    tester,
  ) async {
    final completion = Completer<bool>();
    launchHandler = () => completion.future;
    await mount(tester, lookup: (_) async => 'https://place.map.kakao.com/1');
    await tester.tap(find.byType(TextButton));
    await tester.pump();
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    launchHandler = null;
    await mount(tester, lookup: (_) async => 'https://place.map.kakao.com/2');
    await tester.tap(find.byType(TextButton));
    await tester.pumpAndSettle();
    completion.complete(true);
    await tester.pumpAndSettle();
    expect(calls.where((call) => call.method == 'launch').length, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'explicit false eligibility blocks the web fallback without blocked status',
    (tester) async {
      await mount(
        tester,
        lookup: (_) async => null,
        place: {
          'name': '좌표 제한, 공원',
          'lat': 36.81083006,
          'lng': 127.1488888,
          'coordinate_quality': {
            'status': 'unverified',
            'map_coordinate_eligible': false,
          },
        },
      );
      await tester.tap(find.byType(TextButton));
      await tester.pumpAndSettle();
      expect(calls, isEmpty);
      expect(find.byType(AlertDialog), findsNothing);
      expect(find.textContaining('좌표 품질 확인이 필요한 장소'), findsOneWidget);
    },
  );

  testWidgets(
    'resolved detail keeps priority over a blocked coordinate and delimiter label',
    (tester) async {
      await mount(
        tester,
        lookup: (_) async => 'https://place.map.kakao.com/117300047',
        place: {
          'name': '공원, 테마/공원#안내?',
          'lat': 36.81083006,
          'lng': 127.1488888,
          'coordinate_quality': {
            'status': 'blocked',
            'map_coordinate_eligible': false,
          },
        },
      );
      await tester.tap(find.byType(TextButton));
      await tester.pumpAndSettle();
      expect(calls, hasLength(1));
      expect(url(calls.single), 'https://place.map.kakao.com/117300047');
      expect(find.byType(AlertDialog), findsNothing);
    },
  );

  testWidgets(
    'server blocked coordinate quality stops pin launch and leaves retry enabled',
    (tester) async {
      await mount(
        tester,
        place: {
          'name': '확인 필요한 장소',
          'lat': 36.8,
          'lng': 127.1,
          'coordinate_quality': {
            'status': 'blocked',
            'map_coordinate_eligible': false,
          },
        },
      );
      await tester.tap(find.byType(TextButton));
      await tester.pumpAndSettle();
      expect(calls, isEmpty);
      expect(find.textContaining('좌표 품질 확인이 필요한 장소'), findsOneWidget);
      expect(find.byType(AlertDialog), findsNothing);
      expect(
        tester.widget<TextButton>(find.byType(TextButton)).onPressed,
        isNotNull,
      );
    },
  );

  testWidgets('injected lookup failure and launch refusal both allow retry', (
    tester,
  ) async {
    launchSucceeds = false;
    await mount(
      tester,
      lookup: (_) async => throw StateError('private provider'),
    );
    await tester.tap(find.byType(TextButton));
    await confirmCoordinates(tester);
    await tester.pumpAndSettle();
    expect(find.textContaining('지도를 열 수 없어요'), findsOneWidget);
    expect(
      tester.widget<TextButton>(find.byType(TextButton)).onPressed,
      isNotNull,
    );
    launchSucceeds = true;
    await tester.tap(find.byType(TextButton));
    await confirmCoordinates(tester);
    await tester.pumpAndSettle();
    expect(calls.where((call) => call.method == 'launch').length, 2);
  });

  testWidgets('backgrounded pending lookup cannot unexpectedly launch a map', (
    tester,
  ) async {
    final detail = Completer<String?>();
    await mount(tester, lookup: (_) => detail.future);
    await tester.tap(find.byType(TextButton));
    await tester.pump();
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    detail.complete('https://place.map.kakao.com/1');
    await tester.pump();
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(calls, isEmpty);
    expect(
      tester.widget<TextButton>(find.byType(TextButton)).onPressed,
      isNotNull,
    );
  });

  testWidgets(
    'an untrusted stored URL never launches outside the Kakao detail contract',
    (tester) async {
      await mount(
        tester,
        place: {
          'name': '저장 장소',
          'lat': 36.8,
          'lng': 127.1,
          'kakao_url': 'https://other.invalid/private',
        },
      );
      await tester.tap(find.byType(TextButton));
      await confirmCoordinates(tester);
      await tester.pumpAndSettle();
      expect(calls.any((call) => url(call).contains('other.invalid')), false);
      expect(url(calls.last), contains('https://map.kakao.com/link/map/'));
    },
  );

  testWidgets(
    'long coordinate notice is scrollable and cancellable on small large-text screens',
    (tester) async {
      tester.view.physicalSize = const Size(320, 480);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(
              context,
            ).copyWith(textScaler: TextScaler.linear(1.8)),
            child: child!,
          ),
          home: Scaffold(
            body: PlaceMapButton(
              place: {
                'name': '아주 긴 저장 장소 이름 ' * 10,
                'address': '충남 천안시 동남구 아주 긴 주소 ' * 20,
                'lat': 36.8,
                'lng': 127.1,
              },
            ),
          ),
        ),
      );
      await tester.tap(find.byType(TextButton));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(
        tester.widget<AlertDialog>(find.byType(AlertDialog)).scrollable,
        true,
      );
      expect(tester.takeException(), isNull);
      await tester.ensureVisible(find.text('취소'));
      await tester.tap(find.text('취소'));
      await tester.pumpAndSettle();
      expect(calls, isEmpty);
      expect(tester.takeException(), isNull);
    },
  );
}
