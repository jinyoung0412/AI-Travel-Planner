// Independent nearby-location QA. No device, native settings or real storage.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:ai_travel_app/input_screen.dart';
import 'package:ai_travel_app/location_service.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'package:ai_travel_app/network/api_client.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

class QaLocation implements LocationSource {
  Future<LocationFix> Function() next;
  int calls = 0;
  QaLocation(this.next);
  @override
  Future<LocationFix> locate() {
    calls++;
    return next();
  }
}

class QaSource implements RecommendationSource {
  final requests = <RecommendationRequest>[];
  @override
  Future<List<String>> suggestTags(String text) async => [];
  @override
  Future<Map<String, dynamic>> recommend(RecommendationRequest r) async {
    requests.add(r);
    return r.mode == 'spot' ? {'places': []} : {'courses': []};
  }
}

final evidence = <Map<String, dynamic>>[];
const exportEvidence = bool.fromEnvironment('NEARBY_QA_EXPORT');
Future<void> tap(WidgetTester t, String label) async {
  final text = find.text(label).last;
  final chip = find.ancestor(of: text, matching: find.byType(ChoiceChip));
  final target = chip.evaluate().isEmpty ? text : chip;
  await t.ensureVisible(target);
  await t.pump();
  await t.tap(target);
  if (label == '장소 추천받기' || label == '코스 추천받기') {
    await t.pump(const Duration(milliseconds: 350));
  } else {
    await t.pumpAndSettle();
  }
}

Future<void> mount(
  WidgetTester t,
  String mode,
  QaSource source,
  QaLocation location,
) async {
  await t.pumpWidget(
    MaterialApp(
      home: InputScreen(mode: mode, source: source, locationSource: location),
    ),
  );
  await t.pumpAndSettle();
}

Future<void> submit(WidgetTester t, String mode) async {
  await tap(t, '다음');
  await tap(t, '직접 태그 선택하기');
  final companion = find.ancestor(
    of: find.text('친구와'),
    matching: find.byType(ChoiceChip),
  );
  if (!t.widget<ChoiceChip>(companion).selected) await tap(t, '친구와');
  for (var i = 0; i < 5 && find.text('선택 완료').evaluate().isNotEmpty; i++) {
    await tap(t, '선택 완료');
  }
  if (mode == 'course') await tap(t, '다음');
  await tap(t, mode == 'spot' ? '장소 추천받기' : '코스 추천받기');
}

Future<void> returnToLocation(WidgetTester t, String mode) async {
  await t.pumpAndSettle();
  await t.pageBack();
  await t.pumpAndSettle();
  await tap(t, '이전');
  if (mode == 'course') await tap(t, '이전');
}

Future<Map<String, dynamic>> wire(RecommendationRequest r) async {
  late Map<String, dynamic> body;
  final client = ApiClient(
    client: MockClient((request) async {
      body = jsonDecode(request.body) as Map<String, dynamic>;
      return http.Response(
        jsonEncode(r.mode == 'spot' ? {'places': []} : {'courses': []}),
        200,
      );
    }),
  );
  if (r.mode == 'spot') {
    await client.getSpotRecommendation(
      userText: r.userText,
      transport: r.transport,
      region: r.region,
      userLat: r.lat,
      userLng: r.lng,
      personaTags: r.tags,
      count: r.count,
      intentFields: r.selectionFields,
    );
  } else {
    await client.getCourseRecommendation(
      userText: r.userText,
      transport: r.transport,
      region: r.region,
      userLat: r.lat,
      userLng: r.lng,
      personaTags: r.tags,
      count: r.count,
      spotCount: r.slotTypes.length,
      slotTypes: r.slotTypes,
      intentFields: r.selectionFields,
    );
  }
  client.close();
  return body;
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  tearDownAll(() {
    if (exportEvidence) {
      File(
        '../local_artifacts/nearby_qa/2026-10-27/ui_cases.json',
      ).writeAsStringSync(const JsonEncoder.withIndent('  ').convert(evidence));
    }
  });
  final points = <String, LocationFix>{
    '천안 내부': const LocationFix(36.8151, 127.1139),
    '아산 내부': const LocationFix(36.7898, 127.0043),
    '남서 경계': const LocationFix(36.55, 126.80),
    '북동 경계': const LocationFix(37.05, 127.35),
    '남 경계 밖': const LocationFix(36.549999, 127.1),
    '북 경계 밖': const LocationFix(37.050001, 127.1),
    '서 경계 밖': const LocationFix(36.8, 126.799999),
    '동 경계 밖': const LocationFix(36.8, 127.350001),
    '서울 외부': const LocationFix(37.5, 127),
  };
  for (final mode in ['spot', 'course']) {
    for (final transport in ['대중교통', '차']) {
      for (final point in points.entries) {
        final outside = point.key.contains('밖') || point.key.contains('외부');
        testWidgets('$mode $transport ${point.key}: 좌표와 직렬화 요청', (t) async {
          final s = QaSource();
          await mount(t, mode, s, QaLocation(() async => point.value));
          expect(find.text('현재 위치 확인됨'), findsOneWidget);
          if (transport == '차') await tap(t, '차');
          await submit(t, mode);
          if (outside) {
            expect(find.text('추천 기준을 바꿀까요?'), findsOneWidget);
            await tap(t, '돌아가기');
            expect(s.requests, isEmpty);
            await tap(t, mode == 'spot' ? '장소 추천받기' : '코스 추천받기');
            await tap(t, '천안으로 추천');
          } else {
            expect(find.text('추천 기준을 바꿀까요?'), findsNothing);
          }
          final r = s.requests.single;
          expect(r.lat, outside ? 36.8151 : point.value.lat);
          expect(r.lng, outside ? 127.1139 : point.value.lng);
          expect(r.transport, transport);
          expect(r.region, outside ? '천안' : '내 주변');
          final body = await wire(r);
          expect(body['user_lat'], r.lat);
          expect(body['user_lng'], r.lng);
          expect(body['region'], r.region);
          expect(body['transport'], transport);
          await returnToLocation(t, mode);
          final actualLabel = find.text('현재 위치 확인됨').evaluate().isNotEmpty;
          evidence.add({
            'id': '$mode-$transport-${point.key}',
            'mode': mode,
            'input': [point.value.lat, point.value.lng],
            'outside': outside,
            'cancel_sent_requests': 0,
            'body': body,
            'after_result_current_location_label': actualLabel,
            'expected': outside ? '동의 시 천안 중심 기준을 화면과 요청에 명시' : '취득 좌표와 요청 일치',
            'status': 'PASS',
          });
          expect(t.takeException(), isNull);
        });
      }
    }
    for (final reason in [
      LocationFailure.denied,
      LocationFailure.deniedForever,
      LocationFailure.serviceDisabled,
      LocationFailure.unavailable,
      LocationFailure.timeout,
    ]) {
      testWidgets('$mode ${reason.name}: 실패 안내→재시도→추천', (t) async {
        final location = QaLocation(
          () async => throw LocationException(reason),
        );
        final s = QaSource();
        await mount(t, mode, s, location);
        expect(find.text(LocationException(reason).message), findsOneWidget);
        await tap(t, '다음');
        expect(find.text('어디서 놀까요?'), findsOneWidget);
        expect(s.requests, isEmpty);
        await t.pump(const Duration(seconds: 5));
        await t.pumpAndSettle();
        location.next = () async => const LocationFix(36.7898, 127.0043);
        await tap(t, '위치 다시 확인');
        expect(find.text('현재 위치 확인됨'), findsOneWidget);
        await submit(t, mode);
        expect(s.requests.single.lat, 36.7898);
        evidence.add({
          'id': '$mode-${reason.name}',
          'status': 'PASS',
          'expected': '한국어 안내, 진행 차단, 재시도 복구',
          'actual': '안내 일치, 요청 0→1',
        });
      });
    }
    testWidgets('$mode 늦은 GPS: 수동 지역→내 주변 재진입→재시도', (t) async {
      final pending = Completer<LocationFix>();
      final loc = QaLocation(() => pending.future);
      final s = QaSource();
      await t.pumpWidget(
        MaterialApp(
          home: InputScreen(mode: mode, source: s, locationSource: loc),
        ),
      );
      await t.pump();
      await tap(t, '아산');
      await tap(t, '차');
      pending.complete(const LocationFix(37.5, 127));
      await t.pumpAndSettle();
      expect(find.text('아산 중심 출발'), findsOneWidget);
      await submit(t, mode);
      expect(s.requests.single.lat, 36.7898);
      await returnToLocation(t, mode);
      await tap(t, '내 주변');
      expect(find.text('위치를 확인해주세요'), findsOneWidget);
      loc.next = () async => const LocationFix(36.8151, 127.1139);
      await tap(t, '위치 다시 확인');
      expect(loc.calls, 2);
      await submit(t, mode);
      expect(s.requests.last.lat, 36.8151);
      evidence.add({
        'id': '$mode-late-manual-reenter',
        'status': 'PASS',
        'expected': '늦은 응답 무시, 수동 출발지 유지, 재진입 재시도 가능',
        'actual': '아산 좌표 유지, 재확인 천안 좌표 사용',
      });
    });
    testWidgets('$mode 취득 중 화면 이탈과 재진입', (t) async {
      final pending = Completer<LocationFix>();
      final s = QaSource();
      await t.pumpWidget(
        MaterialApp(
          home: InputScreen(
            mode: mode,
            source: s,
            locationSource: QaLocation(() => pending.future),
          ),
        ),
      );
      await t.pump();
      await t.pumpWidget(const MaterialApp(home: SizedBox()));
      pending.complete(const LocationFix(36.8151, 127.1139));
      await t.pumpAndSettle();
      expect(t.takeException(), isNull);
      await mount(
        t,
        mode,
        s,
        QaLocation(() async => const LocationFix(36.7898, 127.0043)),
      );
      await submit(t, mode);
      expect(s.requests.single.lat, 36.7898);
      evidence.add({
        'id': '$mode-dispose-reenter',
        'status': 'PASS',
        'expected': '폐기 후 응답 무시, 새 진입 정상',
        'actual': '오류 없음, 새 좌표 추천',
      });
    });
    testWidgets('$mode 회귀: 외부 동의 후 출발지역은 천안이어야 함', (t) async {
      final s = QaSource();
      await mount(
        t,
        mode,
        s,
        QaLocation(() async => const LocationFix(37.5, 127)),
      );
      await submit(t, mode);
      await tap(t, '천안으로 추천');
      expect(
        s.requests.single.region,
        '천안',
        reason: '천안으로 추천 동의와 서버 지역 필터를 맞춰야 함',
      );
    });
    testWidgets('$mode 회귀: 외부 동의 후 현재 위치로 오표시 금지', (t) async {
      final s = QaSource();
      await mount(
        t,
        mode,
        s,
        QaLocation(() async => const LocationFix(37.5, 127)),
      );
      await submit(t, mode);
      await tap(t, '천안으로 추천');
      await returnToLocation(t, mode);
      expect(
        find.text('현재 위치 확인됨'),
        findsNothing,
        reason: '추천 출발지는 실제 GPS와 다름',
      );
    });
  }
  Position position(double lat, double lng, {double accuracy = 1}) => Position(
    latitude: lat,
    longitude: lng,
    timestamp: DateTime(2026),
    accuracy: accuracy,
    altitude: 0,
    altitudeAccuracy: 0,
    heading: 0,
    headingAccuracy: 0,
    speed: 0,
    speedAccuracy: 0,
  );
  for (final p in [
    position(double.nan, 127),
    position(36, double.infinity),
    position(91, 127),
    position(36, -181),
  ]) {
    test('잘못된 GPS 좌표 ${p.latitude}/${p.longitude} 차단', () async {
      final device = DeviceLocationSource(
        serviceEnabled: () async => true,
        checkPermission: () async => LocationPermission.whileInUse,
        position: () async => p,
      );
      await expectLater(
        device.locate(),
        throwsA(
          isA<LocationException>().having(
            (e) => e.failure,
            '사유',
            LocationFailure.unavailable,
          ),
        ),
      );
    });
  }
  test('대략적 위치 좌표는 수용하나 정밀도를 별도 전달하지 않음', () async {
    final device = DeviceLocationSource(
      serviceEnabled: () async => true,
      checkPermission: () async => LocationPermission.whileInUse,
      position: () async => position(36.8, 127.1, accuracy: 3000),
    );
    final fix = await device.locate();
    expect(fix.lat, 36.8);
    expect(fix.lng, 127.1);
    evidence.add({
      'id': 'approximate-injected-3000m',
      'status': 'PASS_WITH_LIMITATION',
      'expected': '유효 대략 좌표 처리',
      'actual': '좌표 수용; LocationFix에는 정밀도/시간 메타데이터 없음',
    });
  });
}
