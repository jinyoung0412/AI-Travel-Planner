import 'dart:async';
import 'package:ai_travel_app/input_screen.dart';
import 'package:ai_travel_app/location_service.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Location implements LocationSource {
  @override
  Future<LocationFix> locate() async => const LocationFix(36.8, 127.1);
}

class _Source implements RecommendationSource {
  final tags = Completer<List<String>>();
  @override
  Future<List<String>> suggestTags(String text) => tags.future;
  @override
  Future<Map<String, dynamic>?> recommend(
    RecommendationRequest request,
  ) async => {'places': []};
}

Future<TextEditingController> _start(WidgetTester t, _Source source) async {
  await t.pumpWidget(
    MaterialApp(
      home: InputScreen(
        mode: 'spot',
        source: source,
        locationSource: _Location(),
      ),
    ),
  );
  await t.pumpAndSettle();
  await t.tap(find.text('다음'));
  await t.pumpAndSettle();
  await t.tap(find.text('직접 태그 선택하기'));
  await t.pumpAndSettle();
  await t.ensureVisible(find.text('친구와'));
  await t.tap(find.text('친구와'));
  await t.pumpAndSettle();
  for (var i = 0; i < 5; i++) {
    await t.tap(find.text('선택 완료'));
    await t.pumpAndSettle();
  }
  await t.enterText(find.byType(TextField), '여자친구와 100일 기념 데이트');
  final controller = t.widget<TextField>(find.byType(TextField)).controller!;
  expect(t.testTextInput.isVisible, true);
  await t.ensureVisible(find.text('문장으로 태그 고르기'));
  await t.tap(find.text('문장으로 태그 고르기'));
  await t.pump();
  return controller;
}

void main() {
  for (final phase in ['loading', 'confirmation', 'accepted']) {
    for (final event in ['selection', 'composing']) {
      testWidgets(
        'U12 $event-only IME update at $phase preserves approved tags',
        (t) async {
          final source = _Source();
          final controller = await _start(t, source);
          void updateIme() => controller.value = controller.value.copyWith(
            selection: event == 'selection'
                ? const TextSelection.collapsed(offset: 2)
                : controller.selection,
            composing: event == 'composing'
                ? const TextRange(start: 0, end: 2)
                : TextRange.empty,
          );
          if (phase == 'loading') updateIme();
          source.tags.complete(['연인과', '로맨틱한', '기념일']);
          await t.pumpAndSettle();
          expect(find.text('선택을 이렇게 바꿀까요?'), findsOneWidget);
          if (phase == 'confirmation') updateIme();
          await t.tap(find.text('변경 적용'));
          if (phase == 'accepted') updateIme();
          await t.pumpAndSettle();
          final chip = t.widget<ChoiceChip>(
            find.ancestor(
              of: find.text('연인과'),
              matching: find.byType(ChoiceChip),
            ),
          );
          expect(
            chip.selected,
            true,
            reason: 'same sentence IME metadata must preserve approval',
          );
          expect(find.text('친구와'), findsNothing);
          expect(controller.text, '여자친구와 100일 기념 데이트');
          expect(t.takeException(), isNull);
        },
      );
    }
  }
  testWidgets(
    'U12 actual sentence edit during confirmation rejects late approval',
    (t) async {
      final source = _Source();
      final controller = await _start(t, source);
      source.tags.complete(['연인과', '기념일']);
      await t.pumpAndSettle();
      controller.text = '친구와 산책';
      await t.tap(find.text('변경 적용'));
      await t.pumpAndSettle();
      expect(find.text('친구와'), findsOneWidget);
      expect(find.text('연인과'), findsNothing);
      expect(controller.text, '친구와 산책');
      expect(t.takeException(), isNull);
    },
  );
}
