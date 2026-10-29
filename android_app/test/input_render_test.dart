import 'dart:io';
import 'dart:ui' as ui;
import 'package:ai_travel_app/input_screen.dart';
import 'package:ai_travel_app/location_service.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

class _Location implements LocationSource {
  @override
  Future<LocationFix> locate() async => const LocationFix(36.8, 127.1);
}

class _Source implements RecommendationSource {
  @override
  Future<List<String>> suggestTags(String text) async => [];
  @override
  Future<Map<String, dynamic>?> recommend(RecommendationRequest r) async => {};
}

void main() {
  final output = Platform.environment['INPUT_EVIDENCE_DIR'];
  final font = Platform.environment['INPUT_EVIDENCE_FONT'];
  final icons = Platform.environment['INPUT_EVIDENCE_ICONS'];
  setUpAll(() async {
    if (font != null) {
      for (final family in ['InputEvidence', 'Ahem', 'Roboto']) {
        await (FontLoader(
          family,
        )..addFont(File(font).readAsBytes().then(ByteData.sublistView))).load();
      }
    }
    if (icons != null) {
      await (FontLoader(
        'MaterialIcons',
      )..addFont(File(icons).readAsBytes().then(ByteData.sublistView))).load();
    }
  });
  testWidgets(
    'offline input evidence renders sentence, one question, and visit order',
    (t) async {
      t.view.physicalSize = const Size(390, 844);
      t.view.devicePixelRatio = 1;
      addTearDown(t.view.resetPhysicalSize);
      addTearDown(t.view.resetDevicePixelRatio);
      Future<void> tap(String label) async {
        final f = find.text(label).last;
        await t.ensureVisible(f);
        await t.tap(f);
        await t.pumpAndSettle();
      }

      Future<void> mount(String mode) async {
        await t.pumpWidget(
          RepaintBoundary(
            key: const ValueKey('input-evidence'),
            child: MaterialApp(
              debugShowCheckedModeBanner: false,
              theme: ThemeData(
                useMaterial3: true,
                fontFamily: font == null ? null : 'InputEvidence',
              ),
              home: InputScreen(
                key: ValueKey(mode),
                mode: mode,
                source: _Source(),
                locationSource: _Location(),
              ),
            ),
          ),
        );
        await t.pumpAndSettle();
        await tap('천안');
        await tap('봉명역');
        await tap('다음');
        await t.enterText(find.byType(TextField), '여자친구와 100일 기념 데이트');
        FocusManager.instance.primaryFocus?.unfocus();
        await t.pumpAndSettle();
      }

      Future<void> capture(String name) async {
        if (output == null) return;
        final boundary = t.renderObject<RenderRepaintBoundary>(
          find.byKey(const ValueKey('input-evidence')),
        );
        await t.runAsync(() async {
          final bitmap = await boundary.toImage(pixelRatio: 1);
          final data = await bitmap.toByteData(format: ui.ImageByteFormat.png);
          await Directory(output).create(recursive: true);
          await File(
            '$output/$name.png',
          ).writeAsBytes(data!.buffer.asUint8List());
          bitmap.dispose();
        });
      }

      await mount('spot');
      expect(find.byType(TextField), findsOneWidget);
      expect(find.text('친구와'), findsNothing);
      await capture('input-sentence');
      await tap('직접 태그 선택하기');
      await tap('연인과');
      expect(find.text('누구와 함께하나요?'), findsOneWidget);
      expect(find.text('활동적인'), findsNothing);
      await capture('input-one-question');
      await mount('course');
      await tap('다음');
      expect(find.text('방문 순서'), findsOneWidget);
      expect(find.byType(SwitchListTile), findsNothing);
      await capture('input-visit-order');
      expect(t.takeException(), isNull);
    },
  );
}
