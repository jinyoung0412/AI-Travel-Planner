import 'package:ai_travel_app/spot_result_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

const spatial = '주변 장소와의 거리는 적용하지 않았습니다. 출발 위치 반경 안에서 요청한 종류를 추천합니다.';
const taste = '검증된 블로그 태그가 없어 취향 일치 근거가 없습니다.';
const place = {
  'place_id': 'naver:spatial-test',
  'name': '요청한 카페',
  'address': '충남 천안시 시험로 1',
  'lat': 36.81,
  'lng': 127.15,
};
void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  Future<void> mount(
    WidgetTester tester,
    Map<String, dynamic> metadata, {
    int requested = 1,
    double scale = 1,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(textScaler: TextScaler.linear(scale)),
          child: child!,
        ),
        home: SpotResultScreen(
          places: const [place],
          requestedCount: requested,
          metadata: metadata,
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('spatial metadata stays internal while place remains visible', (
    tester,
  ) async {
    await mount(tester, {'spatial_relation_limitation': spatial});
    expect(find.text('주변 거리 조건 미적용'), findsNothing);
    expect(find.text(spatial), findsNothing);
    await tester.pumpAndSettle();
    expect(find.text('주변 거리 조건 안내'), findsNothing);
    expect(find.text(spatial), findsNothing);
    expect(find.text(taste), findsNothing);
    expect(find.text('요청한 카페'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  testWidgets(
    'partial results remain usable without spatial or taste diagnostics',
    (tester) async {
      tester.view.physicalSize = const Size(320, 480);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await mount(
        tester,
        {
          'spatial_relation_limitation': spatial,
          'preference_evidence': 'unavailable',
          'preference_limitation': taste,
        },
        requested: 5,
        scale: 1.8,
      );
      expect(find.text('취향 일치 미확인'), findsNothing);
      expect(find.text('주변 거리 조건 미적용'), findsNothing);
      expect(find.text(taste), findsNothing);
      await tester.pumpAndSettle();
      expect(find.text(taste), findsNothing);
      expect(find.text(spatial), findsNothing);
      await tester.scrollUntilVisible(
        find.text('요청한 카페'),
        150,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('요청한 카페'), findsOneWidget);
      expect(find.textContaining('1곳만 추천'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'missing blank and malformed optional spatial values leave normal UI unchanged',
    (tester) async {
      for (final value in [null, '', '  ', 3, <String>[]]) {
        final metadata = <String, dynamic>{
          if (value != null) 'spatial_relation_limitation': value,
        };
        await mount(tester, metadata);
        expect(find.text('주변 거리 조건 안내'), findsNothing);
        expect(find.text('요청한 카페'), findsOneWidget);
        expect(tester.takeException(), isNull);
      }
      await mount(tester, {
        'preference_evidence': 'unavailable',
        'preference_limitation': taste,
      });
      expect(find.text('취향 일치 미확인'), findsNothing);
      expect(find.text(taste), findsNothing);
      await tester.pumpAndSettle();
      expect(find.text(taste), findsNothing);
      expect(find.text('주변 거리 조건 안내'), findsNothing);
    },
  );
}
