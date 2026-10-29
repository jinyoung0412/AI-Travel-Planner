import 'package:ai_travel_app/course_result_screen.dart';
import 'package:ai_travel_app/course_summary_card.dart';
import 'package:ai_travel_app/course_timeline.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

const stop = <String, dynamic>{
  'place_id': 'local:compact-course',
  'name': '쉬어가는 카페',
  'category': '카페,디저트',
  'address': '충남 천안시 시험로 12',
  'lat': 36.81,
  'lng': 127.15,
  'travel_explanation': {
    'activity': '카페',
    'reason': '카페 분류와 출발점 기준 거리로 선택했어요.',
    'unverified_conditions': ['조용함'],
  },
};
const taste = '검증된 블로그 태그가 없어 취향 일치 근거가 없습니다.';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  Future<void> mount(
    WidgetTester tester, {
    Map<String, dynamic> metadata = const {
      'preference_evidence': 'unavailable',
      'preference_limitation': taste,
    },
    Object distance = 1.2,
    Map<String, dynamic> place = stop,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: CourseResultScreen(
          courses: [
            [place],
          ],
          requestedCount: 1,
          courseMetrics: [
            {'estimated_distance_km': distance},
          ],
          metadata: metadata,
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets(
    'distance and route stay visible without diagnostic explanations',
    (tester) async {
      await mount(tester);
      expect(find.text('약 1.2 km'), findsOneWidget);
      expect(find.text('출발점 포함 · 직선거리 추정'), findsNothing);
      expect(find.text(stop['name'] as String), findsOneWidget);
      expect(find.text('01'), findsOneWidget);
      expect(find.text('카카오맵에서 보기'), findsOneWidget);
      expect(find.text(taste), findsNothing);
      expect(find.text(stop['address'] as String), findsOneWidget);
      expect(find.textContaining('자료 근거:'), findsNothing);
      expect(find.text('자세히 보기'), findsNothing);
      expect(find.byType(ExpansionTile), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('internal condition and fallback metadata stay off result UI', (
    tester,
  ) async {
    await mount(
      tester,
      metadata: {
        'travel_request': {'summary': '친구와 조용한 카페'},
        'intent_status': 'unverified_alternative',
        'selection_method': 'rules_fallback',
        'spatial_relation_limitation': '주변 장소와의 거리는 적용하지 않았습니다.',
      },
    );
    expect(find.text('필수 조건 미확인'), findsNothing);
    expect(find.text('AI 비교 미완료 · 기본 추천'), findsNothing);
    expect(find.text('주변 거리 조건 미적용'), findsNothing);
    expect(find.text('요청과 추천 근거'), findsNothing);
    expect(find.text('요청과 추천 근거'), findsNothing);
    expect(find.text('주변 장소와의 거리는 적용하지 않았습니다.'), findsNothing);
  });

  testWidgets('course comparison diagnostics stay off result UI', (
    tester,
  ) async {
    await mount(
      tester,
      metadata: const {
        'course_diversity': {
          'similar_pair_count': 2,
          'limitation': '이동 부담을 고려해 일부 장소가 겹칠 수 있어요.',
        },
      },
    );
    expect(find.text('일부 코스의 방문 장소가 많이 겹쳐요'), findsNothing);
    expect(find.text('이동 부담을 고려해 일부 장소가 겹칠 수 있어요.'), findsNothing);
    expect(find.text('이동 부담을 고려해 일부 장소가 겹칠 수 있어요.'), findsNothing);
  });

  testWidgets(
    'blocked coordinates and invalid metrics never become prominent distances',
    (tester) async {
      for (final distance in ['NaN', double.infinity, -2]) {
        await mount(tester, distance: distance);
        expect(find.text('거리 정보가 없어요'), findsNothing);
        expect(find.textContaining(' km'), findsNothing);
      }
      await mount(
        tester,
        place: {
          ...stop,
          'coordinate_quality': {
            'status': 'blocked',
            'distance_eligible': false,
          },
        },
      );
      expect(find.text('코스 거리를 표시하지 않아요'), findsNothing);
      expect(find.text('약 1.2 km'), findsNothing);
      expect(find.textContaining('좌표 품질 확인'), findsNothing);
      expect(find.textContaining('1.2'), findsNothing);
    },
  );

  testWidgets(
    'large text on a narrow screen keeps details and distance accessible',
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
          home: const Scaffold(
            body: SingleChildScrollView(
              child: Column(
                children: [
                  CourseSummaryCard(
                    metric: {'estimated_distance_km': 12345.6},
                    quiet: true,
                    metadata: {},
                    places: [stop],
                  ),
                  CourseTimeline(places: [stop], compact: true, quiet: true),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text(stop['address'] as String),
        150,
      );
      await tester.pumpAndSettle();
      expect(find.text(stop['address'] as String), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'reviewed area metadata does not expose internal comparison explanations',
    (tester) async {
      const message = '서로 다른 등록 장소여도 신정호 관광 권역의 겹침을 고려했어요.';
      await mount(
        tester,
        metadata: {
          'course_diversity': {
            'comparison_basis': 'reviewed_tourism_areas_and_exact_visits',
            'reviewed_area_groups': [
              {
                'id': 'sinjeong_lake_park_area',
                'basis': 'same_tourism_area_not_same_venue',
                'label': '신정호 호수 관광 권역',
              },
            ],
          },
        },
      );
      expect(find.text(message), findsNothing);
      expect(find.text(message), findsNothing);
      await mount(
        tester,
        metadata: {
          'course_diversity': {
            'comparison_basis': 'exact_visits',
            'reviewed_area_groups': [],
          },
        },
      );
      await tester.pumpAndSettle();
      expect(find.text(message), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
}
