import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'package:ai_travel_app/choice_condition_notice.dart';

void main() {
  test('scoped grant keeps signed controls and immutable selected IDs', () {
    final initial = RecommendationRequest(
      mode: 'spot',
      userText: '실내 카페 또는 공원',
      transport: '대중교통',
      region: '천안',
      lat: 36.8,
      lng: 127.1,
      tags: [],
      count: 3,
      slotTypes: [],
      seed: 123,
    );
    final reviewed = initial.reviewed(token: 'fixture-token');
    final ids = ['s1.a1.c2', 's1.a1.c1', 's1.a1.c1'];
    final granted = reviewed.reviewed(
      token: reviewed.intentToken!,
      unverified: true,
      consentPlanId: 'plan-fixture',
      acceptedConditionIds: ids,
    );
    ids.clear();
    expect(granted.intentFields['accepted_condition_ids'], [
      's1.a1.c1',
      's1.a1.c2',
    ]);
    expect(granted.intentFields['consent_plan_id'], 'plan-fixture');
    expect(granted.intentFields['accept_unverified'], true);
    expect(granted.seed, reviewed.seed);
    expect(granted.userText, initial.userText);
    expect(granted.count, 3);
    expect(granted.mode, 'spot');
    expect(reviewed.intentFields.containsKey('accepted_condition_ids'), false);
    expect(
      () => granted.acceptedConditionIds.add('other'),
      throwsUnsupportedError,
    );
    final fresh = initial.reviewed(token: 'new-plan');
    expect(fresh.acceptedConditionIds, isEmpty);
    expect(fresh.acceptUnverified, false);
  });

  const offer = ChoiceConsentOffer('plan-fixture', [
    ChoiceConditionOption('s1.a1.c1', '카페', '실내'),
    ChoiceConditionOption('s1.a2.c1', '공원', '야외'),
  ]);
  testWidgets(
    'separate branches require explicit selection; cancel grants none',
    (t) async {
      List<String>? selected;
      await t.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => TextButton(
              onPressed: () async {
                selected = await chooseUnverifiedConditions(context, offer);
              },
              child: const Text('열기'),
            ),
          ),
        ),
      );
      await t.tap(find.text('열기'));
      await t.pumpAndSettle();
      expect(
        t
            .widget<TextButton>(
              find.widgetWithText(TextButton, '선택한 미확인 대안도 보기'),
            )
            .onPressed,
        isNull,
      );
      await t.tap(find.text('카페: 실내 미확인'));
      await t.pump();
      await t.tap(find.text('선택한 미확인 대안도 보기'));
      await t.pumpAndSettle();
      expect(selected, ['s1.a1.c1']);
      selected = null;
      await t.tap(find.text('열기'));
      await t.pumpAndSettle();
      await t.tap(find.text('공원: 야외 미확인'));
      await t.pump();
      await t.tap(find.text('취소'));
      await t.pumpAndSettle();
      expect(selected, isNull);
    },
  );

  testWidgets('offer action prevents repeated taps while pending', (t) async {
    var calls = 0;
    await t.pumpWidget(
      MaterialApp(
        home: ChoiceOfferNotice(
          offer: offer,
          onInclude: (_) async {
            calls++;
            await Future<void>.delayed(const Duration(seconds: 1));
          },
        ),
      ),
    );
    await t.tap(find.text('미확인 대안도 보기'));
    await t.pump();
    expect(find.text('확인 중…'), findsOneWidget);
    await t.tap(find.text('확인 중…'));
    await t.pump();
    expect(calls, 1);
    await t.pump(const Duration(seconds: 1));
    expect(find.text('미확인 대안도 보기'), findsOneWidget);
  });
}
