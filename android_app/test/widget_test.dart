import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:ai_travel_app/main.dart';
import 'package:ai_travel_app/course_result_screen.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  testWidgets('home and saved tab work on small screens without overflow', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(360, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const MyApp());
    await tester.pumpAndSettle();
    expect(find.text('오늘 충남'), findsOneWidget);
    expect(find.text('스팟 추천'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('코스 추천'),
      100,
      scrollable: find.byType(Scrollable).first,
    );
    expect(tester.takeException(), isNull);
    await tester.tap(find.byIcon(Icons.bookmark_rounded));
    await tester.pumpAndSettle();
    expect(find.text('저장된 스팟이 없어요'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  testWidgets(
    'course save retains identity-address and labels estimated distance',
    (tester) async {
      final place = {
        'place_id': 'naver:1',
        'identity_key': 'alias1',
        'name': '아지트',
        'address': '충남 천안시 테스트로 1',
        'lat': 36.8151,
        'lng': 127.11,
        'category': '카페',
      };
      await tester.pumpWidget(
        MaterialApp(
          home: CourseResultScreen(
            courses: [
              [place],
            ],
            requestedCount: 5,
            region: '천안',
            courseMetrics: const [
              {'estimated_distance_km': 1.2},
            ],
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.textContaining('직선거리 추정'), findsOneWidget);
      await tester.tap(find.byIcon(Icons.bookmark_outline_rounded));
      await tester.pumpAndSettle();
      final raw = (await SharedPreferences.getInstance()).getString(
        'saved_courses',
      );
      expect(raw, contains('naver:1'));
      expect(raw, contains('충남 천안시 테스트로 1'));
      expect(tester.takeException(), isNull);
    },
  );
}
