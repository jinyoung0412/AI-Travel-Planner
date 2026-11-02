import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ai_travel_app/choice_condition_notice.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'compound_choice_flow_test.dart' as support;

Map<String, dynamic> metadata() =>
    support.copy(support.fixture('F01-safe-park-200')['metadata']);
Map<String, dynamic> plan() =>
    support.copy(support.fixture('F05-preview-one-visit')['travel_request']);
Map first(Map m) => m['consent_offer']['alternatives'][0] as Map;

void main() {
  testWidgets('APP-V5-01: single withheld s2 keeps second visit label', (
    t,
  ) async {
    final m = metadata();
    first(m)['stage_id'] = 's2';
    first(m)['alternative_id'] = 's2.a1';
    first(m)['conditions'][0]['id'] = 's2.a1.c1';
    final offer = readChoiceConsentOffer(m)!;
    expect(offer.conditions.single.scope, contains('2번째 방문'));
    await t.pumpWidget(
      MaterialApp(
        home: ChoiceOfferNotice(offer: offer, onInclude: (_) async {}),
      ),
    );
    expect(find.textContaining('2번째 방문'), findsOneWidget);
    expect(find.textContaining('1번째 방문'), findsNothing);
  });
  test('APP-V5-01: sparse s2 s3 never renumber to s1 s2', () {
    final m = metadata();
    final a = first(m);
    a['stage_id'] = 's2';
    a['alternative_id'] = 's2.a1';
    a['conditions'][0]['id'] = 's2.a1.c1';
    final b = support.copy(a);
    b['stage_id'] = 's3';
    b['alternative_id'] = 's3.a1';
    b['conditions'][0]['id'] = 's3.a1.c1';
    m['consent_offer']['alternatives'].add(b);
    final offer = readChoiceConsentOffer(m)!;
    expect(offer.conditions[0].scope, contains('2번째 방문'));
    expect(offer.conditions[1].scope, contains('3번째 방문'));
  });
  for (final bad in ['', 'stage-two', 's0', 's6', 's02']) {
    test('APP-V5-01: invalid stage $bad cannot become visit one', () {
      final m = metadata();
      first(m)['stage_id'] = bad;
      expect(readChoiceConsentOffer(m), isNull);
    });
  }
  for (final attack in [
    'foreign_condition',
    'foreign_alternative',
    'other_branch',
    'foreign_common',
  ]) {
    test('APP-V5-02: reject $attack', () {
      final m = metadata();
      final a = first(m);
      if (attack == 'foreign_condition') a['conditions'][0]['id'] = 's2.a1.c1';
      if (attack == 'foreign_alternative') a['alternative_id'] = 's2.a1';
      if (attack == 'foreign_common') a['conditions'][0]['id'] = 's2.c1';
      if (attack == 'other_branch') {
        final b = support.copy(a);
        b['alternative_id'] = 's1.a2';
        b['label'] = '공원';
        m['consent_offer']['alternatives'].add(b);
      }
      expect(readChoiceConsentOffer(m), isNull);
    });
  }
  test(
    'same-stage common ID is explicit, shared once, and bound to canonical common atom',
    () {
      final m = metadata();
      final p = plan();
      final atom = support.copy(first(m)['conditions'][0]);
      atom['id'] = 's1.c1';
      p['stages'][0]['conditions'] = [atom];
      p['stages'][0]['alternatives'][0]['conditions'] = [];
      first(m)['conditions'] = [support.copy(atom)];
      final b = support.copy(first(m));
      b['alternative_id'] = 's1.a2';
      b['label'] = '공원';
      m['consent_offer']['alternatives'].add(b);
      final offer = readChoiceConsentOffer(m, travelRequest: p)!;
      expect(offer.conditions.length, 1);
      expect(offer.conditions.single.id, 's1.c1');
      expect(offer.conditions.single.scope, contains('공통'));
      expect(offer.conditions.single.scope, contains('카페'));
      expect(offer.conditions.single.scope, contains('공원'));
      p['stages'][0]['conditions'] = [];
      expect(readChoiceConsentOffer(m, travelRequest: p), isNull);
    },
  );
  for (final field in ['field', 'value', 'required', 'quote', 'source_span']) {
    test('canonical semantics reject changed $field on the same ID', () {
      final m = metadata();
      final atom = first(m)['conditions'][0];
      atom[field] = {
        'field': 'outdoor',
        'value': false,
        'required': false,
        'quote': '야외',
        'source_span': [9, 11],
      }[field];
      expect(readChoiceConsentOffer(m, travelRequest: plan()), isNull);
    });
  }
  for (final span in [
    ["0", "2"],
    [0.0, 2.0],
  ]) {
    test(
      'source span types cannot impersonate signed integer offsets: $span',
      () {
        final m = metadata();
        first(m)['conditions'][0]['source_span'] = span;
        expect(readChoiceConsentOffer(m, travelRequest: plan()), isNull);
      },
    );
  }
  test(
    'canonical unknown atom and unknown alternative never become choices',
    () {
      final m = metadata();
      first(m)['conditions'][0]['id'] = 's1.a1.c9';
      expect(readChoiceConsentOffer(m, travelRequest: plan()), isNull);
      final n = metadata();
      first(n)['alternative_id'] = 's1.a3';
      first(n)['conditions'][0]['id'] = 's1.a3.c1';
      expect(readChoiceConsentOffer(n, travelRequest: plan()), isNull);
    },
  );
  test(
    'interpreted hierarchy is immutable and excluded from outgoing grant wire',
    () {
      final p = plan();
      final request = RecommendationRequest(
        mode: 'spot',
        userText: '실내 카페 또는 공원',
        transport: '차',
        region: '천안',
        lat: 36.8,
        lng: 127.1,
        tags: [],
        count: 3,
        slotTypes: [],
      ).reviewed(token: 'opaque', planId: p['plan_id'], travelRequest: p);
      p['stages'].clear();
      expect(request.travelRequest!['stages'], hasLength(1));
      expect(
        () => request.travelRequest!['stages'].clear(),
        throwsUnsupportedError,
      );
      final next = request.reviewed(
        token: 'opaque',
        unverified: true,
        consentPlanId: request.planId,
        acceptedConditionIds: ['s1.a1.c1'],
      );
      expect(next.travelRequest!['stages'], hasLength(1));
      expect(next.intentFields.containsKey('travel_request'), false);
      expect(next.intentFields.containsKey('plan_id'), false);
    },
  );
  for (final attack in [
    'foreign_branch',
    'meaning_flip',
    'missing_canonical_atom',
  ]) {
    testWidgets(
      'malformed $attack keeps safe result and sends no extra request',
      (t) async {
        final source = support.Source();
        final body = support.fixture('F01-safe-park-200');
        final a = body['metadata']['consent_offer']['alternatives'][0];
        if (attack == 'foreign_branch') a['conditions'][0]['id'] = 's1.a2.c1';
        if (attack == 'meaning_flip') a['conditions'][0]['value'] = false;
        if (attack == 'missing_canonical_atom') {
          a['conditions'][0]['id'] = 's1.a1.c9';
        }
        source.initialOverride = body;
        await support.start(t, source);
        expect(find.text('합성 공원'), findsOneWidget);
        expect(find.text('미확인 대안도 보기'), findsNothing);
        expect(source.requests.length, 1);
      },
    );
  }
}
