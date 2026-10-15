import 'dart:async';
import 'dart:convert';
import 'package:ai_travel_app/bookmark_button.dart';
import 'package:ai_travel_app/course_result_screen.dart';
import 'package:ai_travel_app/local_storage_service.dart';
import 'package:ai_travel_app/saved_screen.dart';
import 'package:ai_travel_app/spot_result_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> place(int id) => {
  'place_id': 'naver:$id',
  'name': '같은 이름 $id',
  'category': '아주 긴 카테고리 이름',
  'address': '충남 천안시 $id',
  'lat': '36.8',
  'lng': '127.1',
  'tags': ['친구와'],
};

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  void smallScreen(WidgetTester tester) {
    tester.view.physicalSize = const Size(320, 480);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  Widget app(Widget child, {double scale = 1}) => MaterialApp(
    builder: (context, child) => MediaQuery(
      data: MediaQuery.of(
        context,
      ).copyWith(textScaler: TextScaler.linear(scale)),
      child: child!,
    ),
    home: child,
  );
  testWidgets('bookmark read and double tap cannot race a save', (
    tester,
  ) async {
    final read = Completer<bool>();
    final write = Completer<void>();
    var writes = 0;
    await tester.pumpWidget(
      app(
        Scaffold(
          body: BookmarkButton(
            read: () => read.future,
            save: () {
              writes++;
              return write.future;
            },
            remove: () async {},
            label: '스팟을',
            color: Colors.orange,
          ),
        ),
      ),
    );
    await tester.tap(find.byIcon(Icons.bookmark_outline_rounded));
    expect(writes, 0);
    read.complete(false);
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.bookmark_outline_rounded));
    await tester.tap(find.byIcon(Icons.bookmark_outline_rounded));
    expect(writes, 1);
    write.complete();
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.bookmark_rounded), findsOneWidget);
  });
  testWidgets(
    'saved course delete targets identity after another course is inserted',
    (tester) async {
      await LocalStorageService.saveCourse('첫 코스', [place(1)]);
      await LocalStorageService.saveCourse('둘째 코스', [place(2)]);
      await tester.pumpWidget(app(const SavedScreen()));
      await tester.pumpAndSettle();
      await tester.tap(find.text('코스 (2)'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('코스 삭제').last);
      await tester.pumpAndSettle();
      await LocalStorageService.saveCourse('새 코스', [place(3)]);
      await tester.tap(find.text('삭제'));
      await tester.pumpAndSettle();
      expect(await LocalStorageService.isCourseSaved([place(1)]), false);
      expect(await LocalStorageService.isCourseSaved([place(2)]), true);
      expect(await LocalStorageService.isCourseSaved([place(3)]), true);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'course result save and saved detail retain metrics tags and address on large text',
    (tester) async {
      smallScreen(tester);
      await tester.pumpWidget(
        app(
          CourseResultScreen(
            courses: [
              [place(1), place(2)],
            ],
            requestedCount: 3,
            region: '천안',
            courseMetrics: const [
              {'estimated_distance_km': 1.2},
            ],
            metadata: const {'distance_source': 'haversine'},
          ),
          scale: 1.8,
        ),
      );
      await tester.pumpAndSettle();
      expect(find.textContaining('직선거리 추정'), findsOneWidget);
      await tester.tap(find.byIcon(Icons.bookmark_outline_rounded));
      await tester.pumpAndSettle();
      final saved = (await LocalStorageService.getSavedCourses()).single;
      expect(saved['metric'], {'estimated_distance_km': 1.2});
      expect(saved['metadata'], {'distance_source': 'haversine'});
      expect(saved['spots'][0]['tags'], ['친구와']);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(app(const SavedScreen(), scale: 1.8));
      await tester.pumpAndSettle();
      await tester.tap(find.text('코스 (1)'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('천안'));
      await tester.pumpAndSettle();
      expect(find.textContaining('직선거리 추정'), findsOneWidget);
      await tester.scrollUntilVisible(
        find.text('충남 천안시 2'),
        150,
        scrollable: find.byType(Scrollable).last,
      );
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'spot result numeric-string and missing GPS render and map failure is handled',
    (tester) async {
      smallScreen(tester);
      await tester.pumpWidget(
        app(
          const SpotResultScreen(
            places: [
              {'name': '위치 없는 장소', 'lat': 'NaN', 'lng': null, 'category': null},
            ],
            requestedCount: 5,
          ),
          scale: 1.8,
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('카카오맵에서 보기'));
      await tester.pump();
      await tester.tap(find.text('카카오맵에서 보기'));
      await tester.pumpAndSettle();
      expect(find.textContaining('지도를 열 수 없어요'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets('malformed local JSON shows retry and preserves the original', (
    tester,
  ) async {
    const raw = 'not json';
    SharedPreferences.setMockInitialValues({'saved_spots': raw});
    await tester.pumpWidget(app(const SavedScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('기존 데이터는 보존됩니다'), findsOneWidget);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('saved_spots'), raw);
    await prefs.setString('saved_spots', jsonEncode([place(1)]));
    await tester.tap(find.text('다시 읽기'));
    await tester.pumpAndSettle();
    expect(find.text('같은 이름 1'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
