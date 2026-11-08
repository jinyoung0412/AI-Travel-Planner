import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:ai_travel_app/input_screen.dart';
import 'package:ai_travel_app/spot_result_screen.dart';
import 'package:ai_travel_app/travel_data.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'compound_choice_flow_test.dart' as support;

final capture =
    jsonDecode(
          File(
            'test/fixtures/compound_choice_v5_manual_atoms.json',
          ).readAsStringSync(),
        )
        as Map;
Map<String, dynamic> actual(String label, String phase) => support.copy(
  (capture['trace'] as List).firstWhere(
    (e) => e['case'] == label && e['phase'] == phase,
  )['body'],
);
Map<String, dynamic> plan(String label) =>
    support.copy(actual(label, 'preview')['travel_request']);
Map manualAtom(Map p) =>
    [
          for (final stage in p['stages'])
            for (final key in ['conditions', 'preferences'])
              for (final atom in stage[key])
                if (atom['source'] == 'manual') atom,
        ].single
        as Map;

class ManualSource extends support.Source {
  final String label;
  ManualSource(this.label);
  @override
  Future<Map<String, dynamic>?> interpret(RecommendationRequest r) async {
    interpretations.add(r);
    return actual(label, 'preview');
  }

  @override
  Future<Map<String, dynamic>?> recommend(RecommendationRequest r) async {
    requests.add(r);
    return actual(label, r.acceptUnverified ? 'accepted' : 'base');
  }
}

Future<void> start(WidgetTester t, ManualSource source) async {
  t.view.physicalSize = const Size(440, 1100);
  t.view.devicePixelRatio = 1;
  addTearDown(t.view.resetPhysicalSize);
  addTearDown(t.view.resetDevicePixelRatio);
  await t.pumpWidget(
    MaterialApp(
      home: InputScreen(
        mode: 'spot',
        source: source,
        locationSource: support.Location(),
      ),
    ),
  );
  await t.pumpAndSettle();
  await support.tap(t, '다음');
  await t.enterText(
    find.byType(TextField),
    plan(source.label)['source_text'] as String,
  );
  await support.tap(t, '장소 추천받기');
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  for (final label in ['manual_plain', 'manual_choice']) {
    final expected = label == 'manual_plain'
        ? TravelConsentPlanKind.plain
        : TravelConsentPlanKind.choice;
    test('J09 fixed: actual manual null quote canonical is valid $label', () {
      final p = plan(label);
      expect(manualAtom(p)['quote'], isNull);
      expect(classifyTravelConsentPlan(p), expected);
    });
    testWidgets(
      'J10 fixed: actual manual canonical reaches recommendation $label',
      (t) async {
        final source = ManualSource(label);
        await start(t, source);
        expect(source.requests.length, 1);
        expect(find.textContaining('여행 문장의 방문 구성을 확인하지 못했어요.'), findsNothing);
        final stored = source.requests.single.travelRequest!;
        expect(manualAtom(stored)['source'], 'manual');
        expect(manualAtom(stored)['quote'], isNull);
        if (label == 'manual_plain') {
          expect(find.text('조건을 바꿔볼까요?'), findsOneWidget);
          await support.tap(t, '다시 찾기');
          expect(source.requests.length, 2);
          expect(source.requests.last.acceptUnverified, true);
          expect(source.requests.last.acceptedConditionIds, isEmpty);
        } else {
          expect(find.text('조건을 바꿔볼까요?'), findsNothing);
        }
        final result = actual(
          label,
          label == 'manual_plain' ? 'accepted' : 'base',
        );
        final firstPlace = support.copy((result['places'] as List).first);
        expect(find.byType(SpotResultScreen), findsOneWidget);
        expect(find.text(firstPlace['name'] as String), findsOneWidget);
        support.expectNoResultExplanation(firstPlace);
      },
    );
    test('J11 control: removing only manual atom leaves normal $label', () {
      final p = plan(label);
      for (final st in p['stages']) {
        for (final k in ['conditions', 'preferences']) {
          st[k] = (st[k] as List)
              .where((a) => a['source'] != 'manual')
              .toList();
        }
      }
      expect(classifyTravelConsentPlan(p), expected);
    });
    for (final attack in [
      'sentence_null',
      'sentence_missing',
      'sentence_empty',
      'sentence_number',
      'missing_source_null',
      'manual_missing_quote',
      'manual_empty_quote',
    ]) {
      test(
        'non-manual/missing/corrupt quote cannot bypass classifier $label $attack',
        () {
          final p = plan(label);
          final atom = manualAtom(p);
          if (attack.startsWith('sentence')) atom['source'] = 'sentence';
          if (attack == 'sentence_missing' || attack == 'manual_missing_quote') {
            atom.remove('quote');
          }
          if (attack == 'sentence_empty' || attack == 'manual_empty_quote') {
            atom['quote'] = '';
          }
          if (attack == 'sentence_number') atom['quote'] = 42;
          if (attack == 'missing_source_null') atom.remove('source');
          expect(classifyTravelConsentPlan(p), TravelConsentPlanKind.invalid);
        },
      );
    }
  }
}
