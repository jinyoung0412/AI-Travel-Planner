import 'package:ai_travel_app/course_comparison.dart';
import 'package:ai_travel_app/spot_result_screen.dart';
import 'package:ai_travel_app/result_notice.dart';
import 'package:ai_travel_app/course_result_screen.dart';
import 'package:ai_travel_app/input_screen.dart';
import 'package:ai_travel_app/location_service.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> place(String id) => {
  'place_id': 'provider:$id',
  'name': '장소 $id',
  'address': '충남 아산시 $id',
  'lat': 36.8,
  'lng': 127.0,
};

class FixedLocation implements LocationSource {
  @override
  Future<LocationFix> locate() async => const LocationFix(36.76979, 126.95182);
}

class Results implements RecommendationSource {
  final requests = <RecommendationRequest>[];
  bool failNext = false;
  @override
  Future<List<String>> suggestTags(String text) async => [];
  @override
  Future<Map<String, dynamic>?> recommend(RecommendationRequest request) async {
    requests.add(request);
    if (failNext) {
      failNext = false;
      return {
        'error': '서버에 연결하지 못했습니다. 연결 상태를 확인해주세요.',
        'reason': 'network_unavailable',
      };
    }
    return {
      if (request.mode == 'spot')
        'places': [place('a'), place('b'), place('c')],
      if (request.mode == 'course')
        'courses': [
          [place('a'), place('b'), place('c')],
        ],
    };
  }
}

Future<void> tap(WidgetTester tester, String text) async {
  final f = find.text(text).last;
  await tester.ensureVisible(f);
  await tester.pumpAndSettle();
  await tester.tap(f);
  await tester.pumpAndSettle();
}

Future<void> chooseCompanion(WidgetTester tester, String label) async {
  await tap(tester, '직접 태그 선택하기');
  expect(find.text('누구와 함께하나요?'), findsOneWidget);
  await tap(tester, label);
  final chip = find.ancestor(
    of: find.text(label),
    matching: find.byType(ChoiceChip),
  );
  expect(tester.widget<ChoiceChip>(chip).selected, isTrue);
  for (var i = 0; i < 5 && find.text('선택 완료').evaluate().isNotEmpty; i++) {
    await tap(tester, '선택 완료');
  }
  expect(find.text('직접 태그 선택하기'), findsOneWidget);
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  testWidgets('compare alternatives then switch to selected course', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: CourseResultScreen(
          courses: [
            [place('a'), place('b')],
            [place('c'), place('b')],
          ],
          requestedCount: 2,
          courseMetrics: const [
            {'estimated_distance_km': 2.1},
            {'estimated_distance_km': 3.2},
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tap(tester, '코스 비교');
    expect(find.byType(CourseComparison), findsOneWidget);
    expect(find.text('다른 장소 1곳'), findsNothing);
    expect(find.text('코스 1 · 2곳'), findsNothing);
    expect(
      find.descendant(
        of: find.byType(CourseComparison),
        matching: find.textContaining('충남 아산시'),
      ),
      findsNothing,
    );
    expect(find.text('3.2 km', findRichText: true), findsOneWidget);
    final alternative = find.byKey(const ValueKey('comparison-course-1'));
    final alternativeTitle = find.descendant(
      of: alternative,
      matching: find.text('코스 2'),
    );
    await tester.ensureVisible(alternativeTitle);
    await tester.pumpAndSettle();
    await tester.tap(alternativeTitle);
    await tester.pumpAndSettle();
    expect(find.byType(CourseComparison), findsOneWidget);
    await tap(tester, '코스 2 보기');
    expect(find.byType(CourseComparison), findsNothing);
    expect(find.text('코스 2'), findsOneWidget);
    expect(find.text('장소 c'), findsOneWidget);
    expect(find.text('약 3.2 km'), findsOneWidget);
    await tap(tester, '코스 비교');
    await tester.tap(find.byKey(const ValueKey('comparison-course-0')));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('비교 닫기'));
    await tester.pumpAndSettle();
    expect(find.text('코스 2'), findsOneWidget);
    expect(find.text('장소 c'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  testWidgets(
    'new request preserves controls with a fresh seed and edit restores input',
    (tester) async {
      final source = Results();
      await tester.pumpWidget(
        MaterialApp(
          home: InputScreen(
            mode: 'course',
            source: source,
            locationSource: FixedLocation(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tap(tester, '다음');
      await chooseCompanion(tester, '친구와');
      await tap(tester, '다음');
      await tap(tester, '코스 추천받기');
      expect(source.requests.length, 1);
      await tap(tester, '같은 조건으로 새 추천');
      expect(source.requests.length, 2);
      expect(find.textContaining('이전 추천과 같은 구성이에요.'), findsOneWidget);
      final a = source.requests.first;
      final b = source.requests.last;
      expect(b.seed, isNot(a.seed));
      expect(b.tags, a.tags);
      expect(b.slotTypes, a.slotTypes);
      expect(b.count, a.count);
      expect(b.lat, a.lat);
      expect(b.lng, a.lng);
      expect(a.recentPlaceIds, isEmpty);
      expect(b.recentPlaceIds, ['provider:a', 'provider:b', 'provider:c']);
      expect(find.byType(CourseResultScreen), findsOneWidget);
      await tap(tester, '조건 수정');
      expect(find.text('어디서 놀까요?'), findsOneWidget);
      await tap(tester, '다음');
      await tap(tester, '다음');
      await tap(tester, '코스 추천받기');
      expect(source.requests.last.tags, a.tags);
      expect(source.requests.last.slotTypes, a.slotTypes);
      expect(source.requests.last.recentPlaceIds, isEmpty);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets('manual diagnostic metadata stays off result screens', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: SpotResultScreen(
          places: [],
          requestedCount: 0,
          metadata: {
            'travel_request': {
              'summary': '카페',
              'manual_overrides': ['생일: 현장 적합성 미확인', '실내 위주: 실내 여부 미확인'],
            },
          },
        ),
      ),
    );
    expect(find.text('직접 선택한 조건'), findsNothing);
    expect(find.textContaining('생일: 현장 적합성 미확인'), findsNothing);
    expect(find.textContaining('실내 위주: 실내 여부 미확인'), findsNothing);
  });
  testWidgets(
    'comparison suppresses blocked distances and supports large type',
    (tester) async {
      tester.view.physicalSize = const Size(320, 640);
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
            body: CourseComparison(
              courses: [
                [place('a')],
                [
                  {
                    ...place('b'),
                    'coordinate_quality': {'distance_eligible': false},
                  },
                ],
              ],
              metrics: const [
                {'estimated_distance_km': 1},
                {'estimated_distance_km': 9},
              ],
              selected: 0,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final alternative = find.byKey(const ValueKey('comparison-course-1'));
      final alternativeTitle = find.descendant(
        of: alternative,
        matching: find.text('코스 2'),
      );
      await tester.ensureVisible(alternativeTitle);
      await tester.pumpAndSettle();
      await tester.tap(alternativeTitle);
      await tester.pumpAndSettle();
      expect(find.text('코스 2 보기'), findsOneWidget);
      expect(find.text('비교할 거리 정보가 없어요'), findsNothing);
      expect(find.textContaining('9.0 km'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'failed refresh retains unsaved result and its own original controls',
    (tester) async {
      final source = Results();
      await tester.pumpWidget(
        MaterialApp(
          home: InputScreen(
            mode: 'course',
            source: source,
            locationSource: FixedLocation(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tap(tester, '다음');
      await chooseCompanion(tester, '친구와');
      await tap(tester, '다음');
      await tap(tester, '코스 추천받기');
      source.failNext = true;
      await tap(tester, '같은 조건으로 새 추천');
      expect(find.byType(CourseResultScreen), findsNothing);
      expect(find.text('이전 추천 다시 보기'), findsOneWidget);
      await tester.pump(const Duration(seconds: 10));
      expect(find.text('추천을 완료하지 못했어요'), findsOneWidget);
      expect(find.text('서버에 연결하지 못했습니다. 연결 상태를 확인해주세요.'), findsOneWidget);
      await tap(tester, '이전 추천 다시 보기');
      expect(find.byType(CourseResultScreen), findsOneWidget);
      expect(find.text('장소 a'), findsOneWidget);
      await tap(tester, '조건 수정');
      await tap(tester, '다음');
      await chooseCompanion(tester, '혼자');
      expect(find.text('혼자'), findsOneWidget);
      expect(find.text('친구와'), findsNothing);
      // Viewing an older result must not silently relabel it with edited inputs.
      await tap(tester, '이전 추천 다시 보기');
      await tap(tester, '같은 조건으로 새 추천');
      expect(source.requests.length, 3);
      expect(source.requests.last.tags, ['친구와']);
      expect(source.requests.last.slotTypes, source.requests.first.slotTypes);
      expect(find.byType(CourseResultScreen), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'repeated spot composition is disclosed without claiming candidates exhausted',
    (tester) async {
      final source = Results();
      await tester.pumpWidget(
        MaterialApp(
          home: InputScreen(
            mode: 'spot',
            source: source,
            locationSource: FixedLocation(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tap(tester, '다음');
      await chooseCompanion(tester, '친구와');
      await tap(tester, '장소 추천받기');
      expect(find.byType(SpotResultScreen), findsOneWidget);
      expect(find.byType(RepeatedResultNotice), findsNothing);
      await tap(tester, '같은 조건으로 새 추천');
      expect(find.byType(RepeatedResultNotice), findsOneWidget);
      expect(find.textContaining('다른 후보가 없'), findsNothing);
      expect(source.requests.length, 2);
    },
  );
  test(
    'composition comparison preserves course stop order and distinct identities',
    () {
      final a = place('a'), b = place('b'), c = place('c');
      expect(samePlaceComposition([a, b], [b, a]), true);
      expect(samePlaceComposition([a, b], [a, c]), false);
      expect(samePlaceComposition([a, b], [a, a]), false);
      expect(
        sameCourseComposition(
          [
            [a, b],
            [c],
          ],
          [
            [c],
            [a, b],
          ],
        ),
        true,
      );
      expect(
        sameCourseComposition(
          [
            [a, b],
          ],
          [
            [b, a],
          ],
        ),
        false,
      );
    },
  );
  testWidgets('spot numbering does not expose sorting disclaimers', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: SpotResultScreen(
          places: [place('a')],
          requestedCount: 1,
          metadata: const {'display_order': 'nearest_neighbor_route'},
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('점수 순위 아님'), findsNothing);
  });
  testWidgets(
    'persistent recommendation error clears on text change and next request',
    (tester) async {
      final source = Results()..failNext = true;
      await tester.pumpWidget(
        MaterialApp(
          home: InputScreen(
            mode: 'spot',
            source: source,
            locationSource: FixedLocation(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tap(tester, '다음');
      await chooseCompanion(tester, '친구와');
      await tap(tester, '장소 추천받기');
      await tester.pump(const Duration(seconds: 10));
      expect(find.text('추천을 완료하지 못했어요'), findsOneWidget);
      expect(find.text('서버에 연결하지 못했습니다. 연결 상태를 확인해주세요.'), findsOneWidget);
      expect(find.text('이전 추천 다시 보기'), findsNothing);
      await tester.enterText(find.byType(TextField), '카페');
      await tester.pumpAndSettle();
      expect(find.text('추천을 완료하지 못했어요'), findsNothing);
      expect(source.requests.length, 1);
      source.failNext = true;
      await tap(tester, '장소 추천받기');
      expect(find.text('추천을 완료하지 못했어요'), findsOneWidget);
      await tap(tester, '장소 추천받기');
      expect(find.byType(SpotResultScreen), findsOneWidget);
      expect(find.text('추천을 완료하지 못했어요'), findsNothing);
      expect(source.requests.last.tags, contains('친구와'));
      expect(tester.takeException(), isNull);
    },
  );
}
