import 'package:ai_travel_app/spot_result_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  testWidgets(
    'long internal metadata is hidden while first place and actions remain visible',
    (tester) async {
      tester.view.physicalSize = const Size(320, 640);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final longLimit = List.filled(
        15,
        '현장의 분위기와 적합성은 아직 확인되지 않았습니다.',
      ).join(' ');
      final overrides = List.generate(8, (i) => '직접 선택한 조건 $i의 자세한 적용 안내입니다.');
      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(
              context,
            ).copyWith(textScaler: TextScaler.linear(1.5)),
            child: child!,
          ),
          home: SpotResultScreen(
            places: const [
              {
                'place_id': 'test:compact',
                'name': '첫 번째 카페',
                'category': '카페',
                'address': '충남 아산시 예시로 1',
                'lat': 36.8,
                'lng': 127.0,
                'travel_explanation': {
                  'activity': '카페',
                  'reason': '상세한 장소 선정 이유입니다.',
                  'unverified_conditions': ['조용함'],
                  'selection_method': 'rules_fallback',
                },
              },
            ],
            requestedCount: 1,
            metadata: {
              'travel_request': {
                'summary': '혼자 카페 방문',
                'manual_overrides': overrides,
              },
              'intent_status': 'unverified_alternative',
              'selection_method': 'rules_fallback',
              'preference_evidence': 'unavailable',
              'preference_limitation': longLimit,
              'spatial_relation_limitation': '주변 장소와의 상대적 거리 조건은 적용하지 않았습니다.',
              'display_order': 'rule_quality_order',
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('취향 일치 미확인'), findsNothing);
      expect(find.text('AI 비교 미완료 · 기본 기준 추천'), findsNothing);
      expect(find.text('필수 조건 미확인 대안 · 방문 전 확인 필요'), findsNothing);
      expect(find.text('주변 거리 조건 미적용'), findsNothing);
      expect(find.text(longLimit), findsNothing);
      expect(find.textContaining(overrides.first), findsNothing);
      expect(find.textContaining('상세한 장소 선정 이유입니다.'), findsNothing);
      expect(find.text('첫 번째 카페').hitTestable(), findsOneWidget);
      expect(tester.getTopLeft(find.text('첫 번째 카페')).dy, lessThan(480));
      expect(find.text('추천 정보 자세히 보기'), findsNothing);
      expect(find.text('추천 이유·확인할 점'), findsNothing);
      expect(find.textContaining('번호:'), findsNothing);
      expect(find.text('카카오맵에서 보기'), findsOneWidget);
      expect(find.byTooltip('스팟을 저장'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets('internal fallback metadata does not add result warnings', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: SpotResultScreen(
          places: [],
          requestedCount: 0,
          metadata: {
            'intent_status': 'unverified_alternative',
            'selection_method': 'rules_fallback',
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('필수 조건 미확인 대안 · 방문 전 확인 필요'), findsNothing);
    expect(find.text('AI 비교 미완료 · 기본 기준 추천'), findsNothing);
    expect(find.text('추천 정보 자세히 보기'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
