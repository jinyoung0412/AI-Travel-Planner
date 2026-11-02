import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ai_travel_app/input_screen.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'package:ai_travel_app/network/api_client.dart';
import 'package:ai_travel_app/travel_data.dart';
import 'compound_choice_flow_test.dart' as support;

final capture =
    jsonDecode(
          File(
            'test/fixtures/compound_choice_v5_single_plan.json',
          ).readAsStringSync(),
        )
        as Map;
Map<String, dynamic> event(String phase) => support.copy(
  (capture['events'] as List).firstWhere((e) => e['phase'] == phase),
);
Map<String, dynamic> plainPlan() =>
    support.copy(event('preview')['body']['data']['travel_request']);

class ActualSingleSource implements IntentRecommendationSource {
  final bodies = <Map<String, dynamic>>[];
  late final ApiClient client = ApiClient(
    client: MockClient((request) async {
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      bodies.add(body);
      final phase = request.url.path == '/travel/interpret'
          ? 'preview'
          : body['accept_unverified'] == true
          ? 'accepted'
          : 'base';
      final reply = event(phase);
      return http.Response(
        jsonEncode(reply['body']),
        reply['status'] as int,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    }),
  );
  @override
  Future<List<String>> suggestTags(String _) async => [];
  @override
  Future<Map<String, dynamic>> interpret(RecommendationRequest request) =>
      client.post('/travel/interpret', request.interpretationBody);
  @override
  Future<Map<String, dynamic>> recommend(RecommendationRequest request) =>
      client.post('/recommend/spot', {
        'user_text': request.userText,
        'region': request.region,
        'transport': request.transport,
        'user_lat': request.lat,
        'user_lng': request.lng,
        'persona_tags': request.tags,
        'count': request.count,
        ...request.intentFields,
      });
}

Future<void> startActual(WidgetTester t, ActualSingleSource source) async {
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
  await t.enterText(find.byType(TextField), '반드시 실내 카페');
  await support.tap(t, '장소 추천받기');
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  testWidgets(
    'J04 actual v13 single422 keeps legacy bool dialog and reaches actual accepted200',
    (t) async {
      final source = ActualSingleSource();
      await startActual(t, source);
      expect(find.text('조건을 바꿔볼까요?'), findsOneWidget);
      expect(find.textContaining('대안의 동의 범위를 확인하지 못했어요'), findsNothing);
      expect(source.bodies.length, 2);
      await support.tap(t, '다시 찾기');
      expect(source.bodies.length, 3);
      expect(source.bodies.last['accept_unverified'], true);
      expect(source.bodies.last.containsKey('consent_plan_id'), false);
      expect(source.bodies.last.containsKey('accepted_condition_ids'), false);
      expect(
        source.bodies.last['intent_token'],
        source.bodies[1]['intent_token'],
      );
      expect(source.bodies.last['seed'], source.bodies[1]['seed']);
      expect(find.text('연동합성 카페0'), findsOneWidget);
      expect(find.textContaining('미확인 조건에 동의하고 포함'), findsOneWidget);
    },
  );
  for (final action in ['decline', 'dismiss']) {
    testWidgets('single plan $action sends no acceptance', (t) async {
      final source = ActualSingleSource();
      await startActual(t, source);
      if (action == 'decline') {
        await support.tap(t, '조건 유지');
      } else {
        await t.tapAt(const Offset(5, 5));
        await t.pumpAndSettle();
      }
      expect(source.bodies.length, 2);
      expect(source.bodies.last['accept_unverified'], false);
      expect(find.text('연동합성 카페0'), findsNothing);
    });
  }
  test('normal canonical single plan is classifiable without a plan ID', () {
    final p = plainPlan();
    expect(p.containsKey('plan_id'), false);
    expect(classifyTravelConsentPlan(p), TravelConsentPlanKind.plain);
    p['plan_id'] = 'unnecessary-for-legacy-bool';
    expect(classifyTravelConsentPlan(p), TravelConsentPlanKind.plain);
    final request = RecommendationRequest(
      mode: 'spot',
      userText: '반드시 실내 카페',
      transport: '차',
      region: '천안',
      lat: 36.8,
      lng: 127.1,
      tags: [],
      count: 3,
      slotTypes: [],
    ).reviewed(token: 'opaque', travelRequest: p);
    p['stages'].clear();
    expect(
      classifyTravelConsentPlan(request.travelRequest),
      TravelConsentPlanKind.plain,
    );
    expect(request.intentFields.containsKey('travel_request'), false);
  });
  for (final offer in ['null', 'empty', 'malformed', 'no_version']) {
    testWidgets('explicit OR with $offer scope never grants blanket bool', (
      t,
    ) async {
      final source = support.Source();
      final body = support.fixture('F02-only-unknown-422');
      if (offer == 'null') body['metadata']['consent_offer'] = null;
      if (offer == 'empty') {
        body['metadata']['consent_offer']['alternatives'] = [];
      }
      if (offer == 'malformed') {
        body['metadata']['consent_offer']['alternatives'] = false;
      }
      if (offer == 'no_version') {
        body['metadata'].remove('choice_contract_version');
      }
      source.initialOverride = body;
      await support.start(t, source);
      expect(source.requests.length, 1);
      expect(find.text('조건을 바꿔볼까요?'), findsNothing);
      expect(find.textContaining('대안의 동의 범위를 확인하지 못했어요'), findsOneWidget);
    });
  }
  testWidgets('unknown preview cannot downgrade new-contract422 to bool', (
    t,
  ) async {
    final source = support.Source();
    final preview = support.fixture('F05-preview-one-visit');
    preview['travel_request'] = {};
    source.previewOverride = preview;
    source.initialOverride = support.copy(event('base')['body']['error']);
    await support.start(t, source);
    expect(source.requests.length, 1);
    expect(find.text('조건을 바꿔볼까요?'), findsNothing);
    expect(find.textContaining('대안의 동의 범위를 확인하지 못했어요'), findsOneWidget);
  });
  testWidgets(
    'unknown hierarchy is not proof of plain plan even without a version marker',
    (t) async {
      final source = support.Source();
      final preview = support.fixture('F05-preview-one-visit');
      preview['travel_request'] = {};
      source.previewOverride = preview;
      final body = support.copy(event('base')['body']['error']);
      body['metadata'].remove('choice_contract_version');
      source.initialOverride = body;
      await support.start(t, source);
      expect(source.requests.length, 1);
      expect(find.text('조건을 바꿔볼까요?'), findsNothing);
      expect(find.textContaining('대안의 동의 범위를 확인하지 못했어요'), findsOneWidget);
    },
  );
  for (final bad in [
    'empty_stages',
    'bad_stage',
    'empty_choice',
    'wrong_choice',
    'bad_conditions',
    'future_schema',
  ]) {
    testWidgets('malformed preview $bad never reaches recommendation or bool', (
      t,
    ) async {
      final source = support.Source();
      final preview = support.fixture('F05-preview-one-visit');
      final p = preview['travel_request'];
      if (bad == 'empty_stages') p['stages'] = [];
      if (bad == 'bad_stage') p['stages'][0] = false;
      if (bad == 'empty_choice') p['stages'][0]['alternatives'] = [];
      if (bad == 'wrong_choice') p['stages'][0]['alternatives'] = false;
      if (bad == 'bad_conditions') p['stages'][0]['conditions'] = null;
      if (bad == 'future_schema') p['schema_version'] = 2;
      source.previewOverride = preview;
      await support.start(t, source);
      expect(source.requests, isEmpty);
      expect(find.text('조건을 바꿔볼까요?'), findsNothing);
    });
  }
  test('one explicit choice anywhere in course keeps scoped consent', () {
    final p = plainPlan();
    final second = support.copy(
      support.fixture('F05-preview-one-visit')['travel_request']['stages'][0],
    );
    second['id'] = 's2';
    for (var i = 0; i < (second['alternatives'] as List).length; i++) {
      second['alternatives'][i]['id'] = 's2.a${i + 1}';
    }
    p['stages'].add(second);
    expect(classifyTravelConsentPlan(p), TravelConsentPlanKind.choice);
  });
  testWidgets('choice course common condition still uses scoped IDs', (
    t,
  ) async {
    final source = MixedSource();
    await support.start(t, source);
    await support.tap(t, '코스로 전환해 추천');
    expect(find.text('조건을 바꿔볼까요?'), findsNothing);
    expect(find.text('미확인 상태로 이 대안도 볼까요?'), findsOneWidget);
    await support.select(t, 's2.c1');
    await support.tap(t, '선택한 미확인 대안도 보기');
    expect(source.requests.last.acceptedConditionIds, ['s2.c1']);
    expect(source.requests.last.consentPlanId, 'example-v13-plan-nonce');
    expect(source.interpretations.length, 1);
  });
}

class MixedSource extends support.Source {
  MixedSource() {
    final preview = support.fixture('F05-preview-one-visit');
    final stage = support.copy(plainPlan()['stages'][0]);
    stage['id'] = 's2';
    stage['conditions'][0]['id'] = 's2.c1';
    preview['travel_request']['stages'].add(stage);
    preview['target_mode'] = 'course';
    preview['target_count'] = 1;
    preview['mode_switch_required'] = true;
    previewOverride = preview;
    final reply = support.fixture('F02-only-unknown-422');
    final a = reply['metadata']['consent_offer']['alternatives'][0];
    a['stage_id'] = 's2';
    a['alternative_id'] = 's2.a1';
    a['conditions'][0]['id'] = 's2.c1';
    a['conditions'][0].remove('source_span');
    initialOverride = reply;
  }
  @override
  Future<Map<String, dynamic>?> recommend(RecommendationRequest request) async {
    requests.add(request);
    if (requests.length == 1) return initialOverride;
    return {
      'courses': [
        [
          support.fixture('F01-safe-park-200')['places'][0],
          support.fixture('F03-cafe-scoped-200')['places'][0],
        ],
      ],
      'course_metrics': [],
      'metadata': {'choice_contract_version': 1, 'consent_offer': null},
    };
  }
}
