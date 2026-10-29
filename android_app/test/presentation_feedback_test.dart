import 'dart:io';
import 'dart:ui' as ui;

import 'package:ai_travel_app/course_comparison.dart';
import 'package:ai_travel_app/course_result_screen.dart';
import 'package:ai_travel_app/local_storage_service.dart';
import 'package:ai_travel_app/place_map_button.dart';
import 'package:ai_travel_app/result_entrance.dart';
import 'package:ai_travel_app/saved_screen.dart';
import 'package:ai_travel_app/spot_result_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

const stops = [
  {
    'place_id': 'fixture:1',
    'name': '느긋한 카페',
    'category': '카페,디저트',
    'address': '충남 천안시 동남구 봉명로 12',
    'lat': 36.8,
    'lng': 127.1,
  },
  {
    'place_id': 'fixture:2',
    'name': '함께 걷는 공원',
    'category': '도시공원',
    'address': '충남 천안시 동남구 산책로 34',
    'lat': 36.81,
    'lng': 127.11,
  },
];

void main() {
  final evidenceDirectory = Platform.environment['PRESENTATION_EVIDENCE_DIR'];
  final fontPath = Platform.environment['PRESENTATION_EVIDENCE_FONT'];
  setUpAll(() async {
    if (fontPath != null) {
      final loader = FontLoader('PresentationEvidence')
        ..addFont(File(fontPath).readAsBytes().then(ByteData.sublistView));
      await loader.load();
      for (final family in ['Ahem', 'Roboto']) {
        await (FontLoader(
              family,
            )..addFont(File(fontPath).readAsBytes().then(ByteData.sublistView)))
            .load();
      }
      final icons = Platform.environment['PRESENTATION_EVIDENCE_ICONS'];
      if (icons != null) {
        await (FontLoader('MaterialIcons')
              ..addFont(File(icons).readAsBytes().then(ByteData.sublistView)))
            .load();
      }
    }
  });
  setUp(() => SharedPreferences.setMockInitialValues({}));

  Future<void> mount(
    WidgetTester tester,
    Widget screen, {
    double width = 390,
    double scale = 1,
    bool reducedMotion = false,
  }) async {
    tester.view.physicalSize = Size(width, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      RepaintBoundary(
        key: const ValueKey('presentation-capture'),
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: ThemeData(
            useMaterial3: true,
            fontFamily: fontPath == null ? null : 'PresentationEvidence',
          ),
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context).copyWith(
              textScaler: TextScaler.linear(scale),
              disableAnimations: reducedMotion,
            ),
            child: child!,
          ),
          home: screen,
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> capture(WidgetTester tester, String name) async {
    if (evidenceDirectory == null) return;
    final boundary = tester.renderObject<RenderRepaintBoundary>(
      find.byKey(const ValueKey('presentation-capture')),
    );
    await tester.runAsync(() async {
      final image = await boundary.toImage(pixelRatio: 1);
      final data = await image.toByteData(format: ui.ImageByteFormat.png);
      await Directory(evidenceDirectory).create(recursive: true);
      await File(
        '$evidenceDirectory/$name.png',
      ).writeAsBytes(data!.buffer.asUint8List());
      image.dispose();
    });
  }

  testWidgets('spot card exposes address and a prominent map target', (
    tester,
  ) async {
    await mount(
      tester,
      const SpotResultScreen(places: stops, requestedCount: 2),
    );
    expect(find.text(stops.first['address'] as String), findsOneWidget);
    final map = find.descendant(
      of: find.byType(PlaceMapButton).first,
      matching: find.byType(FilledButton),
    );
    final button = tester.widget<FilledButton>(map);
    final background = button.style!.backgroundColor!.resolve({})!;
    final foreground = button.style!.foregroundColor!.resolve({})!;
    final contrast =
        (background.computeLuminance() + 0.05) /
        (foreground.computeLuminance() + 0.05);
    expect(contrast, greaterThanOrEqualTo(4.5));
    expect(tester.getSize(map).height, greaterThanOrEqualTo(48));
    expect(find.byType(Image), findsNothing);
    expect(tester.takeException(), isNull);
    await capture(tester, 'spot-result');
  });

  testWidgets('course keeps address visible and distance prominent', (
    tester,
  ) async {
    await mount(
      tester,
      const CourseResultScreen(
        courses: [stops],
        requestedCount: 1,
        courseMetrics: [
          {'estimated_distance_km': 2.6},
        ],
      ),
    );
    expect(find.text('약 2.6 km'), findsOneWidget);
    expect(find.text(stops.first['address'] as String), findsOneWidget);
    expect(find.byType(ExpansionTile), findsNothing);
    expect(find.text('자세히 보기'), findsNothing);
    expect(tester.takeException(), isNull);
    await capture(tester, 'course-result');
  });

  testWidgets('comparison keeps names and distance without repeated details', (
    tester,
  ) async {
    await mount(
      tester,
      Scaffold(
        body: CourseComparison(
          courses: [
            stops,
            [stops[1]],
          ],
          metrics: [
            {'estimated_distance_km': 2.6},
            {'estimated_distance_km': 1.2},
          ],
          selected: 0,
        ),
      ),
    );
    expect(find.text('코스 1'), findsOneWidget);
    expect(find.text('2.6 km', findRichText: true), findsOneWidget);
    expect(find.text(stops.first['name'] as String), findsOneWidget);
    expect(find.text(stops.first['address'] as String), findsNothing);
    expect(find.text('코스 1 보기'), findsOneWidget);
    expect(find.textContaining('2곳'), findsNothing);
    expect(find.textContaining('다른 장소'), findsNothing);
    expect(tester.takeException(), isNull);
    await capture(tester, 'course-comparison');
  });

  testWidgets('saved spots and routes retain direct addresses', (tester) async {
    await LocalStorageService.saveSpot(stops.first);
    await LocalStorageService.saveCourse('천안', stops);
    await mount(tester, const SavedScreen());
    expect(find.text(stops.first['address'] as String), findsOneWidget);
    expect(find.text('카카오맵에서 보기'), findsOneWidget);
    await capture(tester, 'saved-spot');
    await tester.tap(find.text('코스 (1)'));
    await tester.pumpAndSettle();
    expect(find.text(stops.first['address'] as String), findsOneWidget);
    expect(find.text(stops.last['address'] as String), findsOneWidget);
    expect(tester.takeException(), isNull);
    await capture(tester, 'saved-course');
  });

  testWidgets(
    '320px and large text keep all result actions usable with reduced motion',
    (tester) async {
      await mount(
        tester,
        const SpotResultScreen(places: stops, requestedCount: 2),
        width: 320,
        scale: 1.8,
        reducedMotion: true,
      );
      final entrance = find.byType(ResultEntrance).first;
      expect(
        find.descendant(
          of: entrance,
          matching: find.byType(TweenAnimationBuilder<double>),
        ),
        findsNothing,
      );
      await tester.ensureVisible(find.byType(PlaceMapButton).first);
      expect(tester.takeException(), isNull);
      await capture(tester, 'spot-large-text-reduced-motion');
    },
  );
  testWidgets(
    '200 percent text on 320px supports course comparison and saved cards',
    (tester) async {
      final screens = <String, Widget>{
        'course-200-percent': const CourseResultScreen(
          courses: [stops],
          requestedCount: 1,
          courseMetrics: [
            {'estimated_distance_km': 2.6},
          ],
        ),
        'comparison-200-percent': const Scaffold(
          body: CourseComparison(
            courses: [stops],
            metrics: [
              {'estimated_distance_km': 2.6},
            ],
            selected: 0,
          ),
        ),
      };
      for (final entry in screens.entries) {
        await mount(
          tester,
          entry.value,
          width: 320,
          scale: 2,
          reducedMotion: true,
        );
        if (entry.key.startsWith('comparison')) {
          expect(find.text(stops.first['name'] as String), findsOneWidget);
          final confirm = find.text('코스 1 보기');
          expect(confirm, findsOneWidget);
          expect(
            tester.getBottomRight(confirm).dy,
            lessThanOrEqualTo(
              tester.view.physicalSize.height / tester.view.devicePixelRatio,
            ),
          );
        } else {
          expect(find.text(stops.first['address'] as String), findsOneWidget);
        }
        expect(tester.takeException(), isNull);
        await capture(tester, entry.key);
      }
      await LocalStorageService.saveSpot(stops.first);
      await LocalStorageService.saveCourse('천안', stops);
      await mount(
        tester,
        const SavedScreen(),
        width: 320,
        scale: 2,
        reducedMotion: true,
      );
      expect(find.text(stops.first['address'] as String), findsOneWidget);
      expect(tester.takeException(), isNull);
      await capture(tester, 'saved-200-percent');
      await tester.tap(find.text('코스 (1)'));
      await tester.pumpAndSettle();
      expect(find.text(stops.first['address'] as String), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('reduced motion course selector jumps to the chosen route', (
    tester,
  ) async {
    await mount(
      tester,
      const CourseResultScreen(courses: [stops, stops], requestedCount: 2),
      reducedMotion: true,
    );
    await tester.tap(find.byTooltip('코스 2 보기').first);
    await tester.pump();
    expect(tester.widget<PageView>(find.byType(PageView)).controller!.page, 1);
    expect(find.text('코스 2'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
