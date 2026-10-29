import 'dart:convert';
import 'dart:io';
import 'package:ai_travel_app/local_storage_service.dart';
import 'package:ai_travel_app/course_result_screen.dart';
import 'package:ai_travel_app/spot_result_screen.dart';
import 'package:ai_travel_app/saved_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  final cases = Map<String, dynamic>.from(
    jsonDecode(
          File('../tests/fixtures/place_alias_cases.json').readAsStringSync(),
        )
        as Map,
  );
  Map<String, dynamic> place(String key) =>
      Map<String, dynamic>.from(cases[key] as Map);
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test(
    'server historical alias joins an old saved place after address change',
    () async {
      final legacy = place('legacy'), canonical = place('canonical');
      await LocalStorageService.saveSpot(legacy);
      expect(await LocalStorageService.isSpotSaved(canonical), true);
      await LocalStorageService.saveSpot(canonical);
      await LocalStorageService.saveSpot(legacy);
      final saved = await LocalStorageService.getSavedSpots();
      expect(saved.length, 1);
      expect(saved.single['place_id'], 'naver:123');
      expect(saved.single['identity_aliases'], contains(legacy['place_id']));
      await LocalStorageService.saveCourse('천안', [legacy]);
      expect(await LocalStorageService.isCourseSaved([canonical]), true);
      await LocalStorageService.saveCourse('천안', [canonical]);
      expect((await LocalStorageService.getSavedCourses()).length, 1);
    },
  );

  test('historically conflicted aliases never identify a provider', () {
    expect(
      LocalStorageService.samePlace(place('legacy'), place('conflicted')),
      false,
    );
    final other = {
      ...place('canonical'),
      'place_id': 'naver:456',
      'identity_origin': 'legacy_coordinates',
    };
    expect(LocalStorageService.samePlace(place('canonical'), other), false);
  });

  test(
    'stored conflict history survives a later response without conflicts',
    () async {
      await LocalStorageService.saveSpot(place('conflicted'));
      await LocalStorageService.saveSpot(place('canonical'));
      expect(await LocalStorageService.isSpotSaved(place('legacy')), false);
      await LocalStorageService.deleteSpot(place('legacy'));
      final saved = await LocalStorageService.getSavedSpots();
      expect(saved.length, 1);
      expect(
        (saved.single['identity_alias_conflicts'] as Map).keys,
        contains(place('legacy')['place_id']),
      );
    },
  );

  testWidgets(
    'internal metadata survives saving without appearing in results or saved detail',
    (tester) async {
      const notice = '검증 태그가 없어 취향 일치 근거가 없습니다.';
      const metadata = {
        'preference_evidence': 'unavailable',
        'preference_limitation': notice,
      };
      tester.view.physicalSize = const Size(320, 480);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      Widget app(Widget child) => MaterialApp(
        home: child,
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(textScaler: TextScaler.linear(1.8)),
          child: child!,
        ),
      );
      await tester.pumpWidget(
        app(
          SpotResultScreen(
            places: [place('canonical')],
            requestedCount: 1,
            metadata: metadata,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('취향 일치 미확인'), findsNothing);
      expect(find.text(notice), findsNothing);
      await tester.pumpAndSettle();
      expect(find.text(notice), findsNothing);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(
        app(
          CourseResultScreen(
            courses: [
              [place('canonical')],
            ],
            requestedCount: 1,
            metadata: metadata,
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.pumpAndSettle();
      expect(find.text(notice), findsNothing);
      expect(tester.takeException(), isNull);
      await LocalStorageService.saveCourse('통합 검증', [
        place('canonical'),
      ], metadata: metadata);
      expect(
        (await LocalStorageService.getSavedCourses()).single['metadata'],
        metadata,
      );
      await tester.pumpWidget(app(const SavedScreen()));
      await tester.pumpAndSettle();
      await tester.tap(find.text('코스 (1)'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('통합 검증'));
      await tester.pumpAndSettle();
      expect(find.text(notice), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
}
