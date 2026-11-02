import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:ai_travel_app/input_screen.dart';
import 'package:ai_travel_app/location_service.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'package:ai_travel_app/spot_result_screen.dart';
import 'package:ai_travel_app/course_result_screen.dart';
import 'package:ai_travel_app/saved_screen.dart';
import 'package:ai_travel_app/local_storage_service.dart';
import 'package:ai_travel_app/network/api_client.dart';
import 'package:ai_travel_app/choice_condition_notice.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Map<String, dynamic> copy(Object value) =>
    jsonDecode(jsonEncode(value)) as Map<String, dynamic>;
final contract =
    jsonDecode(
          File(
            Platform.environment['COMPOUND_CHOICE_V5_WIRE'] ??
                '../tests/fixtures/compound_choice_v5_wire.json',
          ).readAsStringSync(),
        )
        as Map;
Map<String, dynamic> fixture(String id) => copy(
  (contract['fixtures'] as List).firstWhere((f) => f['id'] == id)['flask_body'],
);

class Location implements LocationSource {
  @override
  Future<LocationFix> locate() async => const LocationFix(36.8066, 127.1469);
}

class Source implements IntentRecommendationSource {
  final interpretations = <RecommendationRequest>[];
  final requests = <RecommendationRequest>[];
  String initial = 'F01-safe-park-200';
  String scoped = 'F03-cafe-scoped-200';
  Map<String, dynamic>? previewOverride;
  Map<String, dynamic>? initialOverride;
  bool fail = false;
  Completer<Map<String, dynamic>?>? pending;
  @override
  Future<List<String>> suggestTags(String _) async => [];
  @override
  Future<Map<String, dynamic>?> interpret(RecommendationRequest request) async {
    interpretations.add(request);
    if (previewOverride != null) return previewOverride;
    final preview = fixture('F05-preview-one-visit');
    if (scoped == 'F04-partial-grant-200') {
      preview['travel_request']['stages'][0]['alternatives'][1]['conditions'] =
          fixture(
            'F04-partial-grant-200',
          )['metadata']['consent_offer']['alternatives'][0]['conditions'];
    }
    return preview;
  }

  @override
  Future<Map<String, dynamic>?> recommend(RecommendationRequest request) async {
    requests.add(request);
    if (requests.length == 1) return initialOverride ?? fixture(initial);
    if (pending != null) return pending!.future;
    if (fail) return {'error': '합성 서버 오류', 'reason': 'intent_expired'};
    return fixture(scoped);
  }
}

Future<void> tap(WidgetTester t, String text) async {
  final f = find.text(text).last;
  await t.ensureVisible(f);
  await t.tap(f);
  await t.pump();
  await t.pump(const Duration(milliseconds: 400));
  await t.pump();
  if (find.byType(AlertDialog).evaluate().isEmpty) await t.pumpAndSettle();
}

Future<void> start(WidgetTester t, Source source) async {
  t.view.physicalSize = const Size(440, 1100);
  t.view.devicePixelRatio = 1;
  addTearDown(t.view.resetPhysicalSize);
  addTearDown(t.view.resetDevicePixelRatio);
  await t.pumpWidget(
    MaterialApp(
      home: InputScreen(
        mode: 'spot',
        source: source,
        locationSource: Location(),
      ),
    ),
  );
  await t.pumpAndSettle();
  await tap(t, '다음');
  await t.enterText(find.byType(TextField), '실내 카페 또는 공원');
  await tap(t, '장소 추천받기');
}

Future<void> select(WidgetTester t, String id) async {
  final f = find.byKey(ValueKey(id));
  await t.ensureVisible(f);
  await t.tap(f);
  await t.pump();
}

void expectNoResultExplanation(Map<String, dynamic> place) {
  expect(find.textContaining('선택 대안:'), findsNothing);
  expect(find.textContaining('확인 필요:'), findsNothing);
  expect(find.text('미확인 조건에 동의하고 포함한 결과예요.'), findsNothing);
  final reason = (place['travel_explanation'] as Map?)?['reason'];
  if (reason is String && reason.isNotEmpty) {
    expect(find.text(reason), findsNothing);
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  testWidgets(
    'C01 C02: one choice remains spot, safe park has no cafe condition',
    (t) async {
      final s = Source();
      await start(t, s);
      expect(find.byType(SpotResultScreen), findsOneWidget);
      expect(find.byType(CourseResultScreen), findsNothing);
      expect(find.text('코스로 추천할까요?'), findsNothing);
      expect(find.text('합성 공원'), findsOneWidget);
      expectNoResultExplanation(fixture('F01-safe-park-200')['places'][0]);
      expect(find.byType(AlertDialog), findsNothing);
      expect(find.text('미확인 대안도 보기'), findsOneWidget);
      expect(s.requests.single.acceptUnverified, false);
      expect(s.requests.single.count, 3);
    },
  );
  testWidgets('C03: cancel and dismiss keep park and send no request', (
    t,
  ) async {
    final s = Source();
    await start(t, s);
    await tap(t, '미확인 대안도 보기');
    await select(t, 's1.a1.c1');
    await tap(t, '취소');
    expect(s.requests.length, 1);
    expect(find.text('합성 공원'), findsOneWidget);
    await tap(t, '미확인 대안도 보기');
    await t.tapAt(const Offset(5, 5));
    await t.pumpAndSettle();
    expect(s.requests.length, 1);
    expect(find.text('합성 공원'), findsOneWidget);
  });
  testWidgets(
    'C04: scoped opt-in reuses signed request without post-result explanations',
    (t) async {
      final s = Source();
      await start(t, s);
      await tap(t, '미확인 대안도 보기');
      await select(t, 's1.a1.c1');
      await tap(t, '선택한 미확인 대안도 보기');
      expect(s.interpretations.length, 1);
      expect(s.requests.length, 2);
      final first = s.requests.first;
      final last = s.requests.last;
      expect(last.intentToken, first.intentToken);
      expect(last.seed, first.seed);
      expect(last.lat, first.lat);
      expect(last.tags, first.tags);
      expect(last.slotTypes, first.slotTypes);
      expect(last.consentPlanId, 'example-v13-plan-nonce');
      expect(last.acceptedConditionIds, ['s1.a1.c1']);
      expect(find.text('합성 카페'), findsOneWidget);
      expectNoResultExplanation(fixture('F03-cafe-scoped-200')['places'][0]);
    },
  );
  testWidgets('C05: unknown-only 422 offers scoped consent, not legacy bool', (
    t,
  ) async {
    final s = Source()..initial = 'F02-only-unknown-422';
    await start(t, s);
    expect(find.byType(AlertDialog), findsOneWidget);
    await select(t, 's1.a1.c1');
    await tap(t, '선택한 미확인 대안도 보기');
    expect(s.requests.last.acceptedConditionIds, ['s1.a1.c1']);
    expect(s.requests.last.consentPlanId, 'example-v13-plan-nonce');
    expect(find.text('합성 카페'), findsOneWidget);
  });
  testWidgets(
    'C06: partial consent can grow without losing prior scope or reinterpreting',
    (t) async {
      final s = Source()..scoped = 'F04-partial-grant-200';
      await start(t, s);
      await tap(t, '미확인 대안도 보기');
      await select(t, 's1.a1.c1');
      await tap(t, '선택한 미확인 대안도 보기');
      expect(s.requests.last.acceptedConditionIds, ['s1.a1.c1']);
      expect(find.text('합성 카페'), findsOneWidget);
      s.scoped = 'F03-cafe-scoped-200';
      await tap(t, '미확인 대안도 보기');
      await select(t, 's1.a2.c1');
      await tap(t, '선택한 미확인 대안도 보기');
      expect(s.requests.last.acceptedConditionIds, ['s1.a1.c1', 's1.a2.c1']);
      expect(s.interpretations.length, 1);
      expect(s.requests.map((r) => r.seed).toSet().length, 1);
    },
  );
  testWidgets('C10: rejected scoped request preserves safe result', (t) async {
    final s = Source()..fail = true;
    await start(t, s);
    await tap(t, '미확인 대안도 보기');
    await select(t, 's1.a1.c1');
    await tap(t, '선택한 미확인 대안도 보기');
    expect(find.text('합성 공원'), findsOneWidget);
    expect(find.text('합성 서버 오류'), findsOneWidget);
    expect(s.requests.length, 2);
  });
  testWidgets('C11: leaving pending opt-in cancels and discards late result', (
    t,
  ) async {
    final s = Source()..pending = Completer<Map<String, dynamic>?>();
    await start(t, s);
    await tap(t, '미확인 대안도 보기');
    await select(t, 's1.a1.c1');
    await tap(t, '선택한 미확인 대안도 보기');
    expect(s.requests.length, 2);
    await t.pageBack();
    await t.pumpAndSettle();
    expect(s.requests.last.cancellation!.isCancelled, true);
    s.pending!.complete(fixture('F03-cafe-scoped-200'));
    await t.pumpAndSettle();
    expect(find.text('합성 카페'), findsNothing);
    expect(s.interpretations.length, 1);
  });
  testWidgets(
    'C11: fresh reroll renews interpretation without carrying consent',
    (t) async {
      final s = Source();
      await start(t, s);
      await tap(t, '미확인 대안도 보기');
      await select(t, 's1.a1.c1');
      await tap(t, '선택한 미확인 대안도 보기');
      await tap(t, '같은 조건으로 새 추천');
      expect(s.interpretations.length, 2);
      expect(s.interpretations.last.seed, isNot(s.interpretations.first.seed));
      expect(s.interpretations.last.acceptedConditionIds, isEmpty);
      expect(s.interpretations.last.acceptUnverified, false);
      expect(s.requests.last.acceptedConditionIds, isEmpty);
    },
  );
  testWidgets('C14: foreign plan or malformed metadata never creates opt-in', (
    t,
  ) async {
    final s = Source();
    final body = fixture('F01-safe-park-200');
    body['metadata']['consent_offer']['plan_id'] = 'other-plan';
    s.initialOverride = body;
    await start(t, s);
    expect(find.text('합성 공원'), findsOneWidget);
    expect(find.text('미확인 대안도 보기'), findsNothing);
  });
  test('C14: malformed offer disables consent safely', () {
    final m = fixture('F01-safe-park-200')['metadata'] as Map<String, dynamic>;
    expect(readChoiceConsentOffer(m), isNotNull);
    for (final change in ['version', 'type', 'status', 'count']) {
      final bad = copy(m);
      if (change == 'version') bad['choice_contract_version'] = 99;
      if (change == 'type') bad['consent_offer']['alternatives'] = false;
      if (change == 'status') {
        bad['consent_offer']['alternatives'][0]['conditions'][0]['status'] =
            'satisfied';
      }
      if (change == 'count') {
        bad['consent_offer']['alternatives'][0]['candidate_count'] = 0;
      }
      expect(readChoiceConsentOffer(bad), isNull, reason: change);
    }
    expect(readChoiceConsentOffer({}), isNull);
  });
  testWidgets(
    'C13: saved spot keeps history but no replay credentials, legacy order survives',
    (t) async {
      final park = copy(
        (fixture('F01-safe-park-200')['places'] as List).single,
      );
      final cafe = copy(
        (fixture('F03-cafe-scoped-200')['places'] as List).single,
      );
      await LocalStorageService.saveSpot(park);
      cafe['intent_token'] = 'do-not-save';
      cafe['plan_id'] = 'do-not-save';
      cafe['nested'] = {
        'clarification_token': 'do-not-save',
        'accepted_condition_ids': ['scope'],
      };
      await LocalStorageService.saveSpot(cafe);
      await LocalStorageService.saveSpot({...cafe, 'name': '합성 카페 갱신'});
      final saved = await LocalStorageService.getSavedSpots();
      expect(saved.length, 2);
      expect(saved.last['place_id'], park['place_id']);
      expect(jsonEncode(saved), isNot(contains('do-not-save')));
      expect(
        saved
            .first['travel_explanation']['conditions'][0]['accepted_as_unknown'],
        true,
      );
      await t.pumpWidget(const MaterialApp(home: SavedScreen()));
      await t.pumpAndSettle();
      expect(find.text('합성 카페 갱신'), findsOneWidget);
      expectNoResultExplanation(cafe);
    },
  );
  testWidgets(
    'C13: saved course metadata strips offer while visits retain attribution',
    (t) async {
      final body = fixture('F03-cafe-scoped-200');
      final places = (body['places'] as List).map((p) => copy(p)).toList();
      await LocalStorageService.saveCourse(
        '천안',
        places,
        metadata: {
          ...body['metadata'],
          'consent_offer': {'plan_id': 'do-not-save'},
        },
      );
      final saved = (await LocalStorageService.getSavedCourses()).single;
      expect(jsonEncode(saved), isNot(contains('do-not-save')));
      expect((saved['metadata'] as Map).containsKey('consent_offer'), false);
      expect(
        saved['spots'][0]['travel_explanation'],
        places.single['travel_explanation'],
      );
      await t.pumpWidget(const MaterialApp(home: SavedScreen()));
      await t.pumpAndSettle();
      await tap(t, '코스 (1)');
      await tap(t, '코스 보기');
      expect(find.text('합성 카페'), findsOneWidget);
      expectNoResultExplanation(places.single);
    },
  );
  test(
    'C07: shared condition deduplicates while separate branch IDs stay separate',
    () {
      final metadata =
          fixture('F01-safe-park-200')['metadata'] as Map<String, dynamic>;
      metadata['consent_offer']['alternatives'][0]['conditions'][0]['id'] =
          's1.c1';
      final alt = copy(metadata['consent_offer']['alternatives'][0]);
      alt['alternative_id'] = 's1.a2';
      alt['label'] = '박물관';
      metadata['consent_offer']['alternatives'].add(alt);
      expect(readChoiceConsentOffer(metadata)!.conditions.length, 1);
      alt['conditions'][0]['id'] = 's1.a2.c1';
      expect(readChoiceConsentOffer(metadata)!.conditions.length, 2);
    },
  );
  testWidgets(
    'C08 C09: server two-visit target asks once and renders two course visits',
    (t) async {
      final s = Source();
      final preview = fixture('F05-preview-one-visit');
      preview['mode_switch_required'] = true;
      preview['target_mode'] = 'course';
      preview['target_count'] = 1;
      preview['travel_request']['stages'].add({
        'id': 's2',
        'activity': '박물관',
        'quote': '박물관',
        'category_filters': ['박물관'],
        'conditions': [],
        'preferences': [],
      });
      s.previewOverride = preview;
      final park = fixture('F01-safe-park-200')['places'][0];
      final museum = {
        ...copy(park),
        'place_id': 'museum',
        'name': '합성 박물관',
        'category': '박물관',
      };
      s.initialOverride = {
        'courses': [
          [park, museum],
        ],
        'course_metrics': [],
        'metadata': {},
      };
      await start(t, s);
      expect(find.text('코스로 추천할까요?'), findsOneWidget);
      expect(s.requests, isEmpty);
      await tap(t, '코스로 전환해 추천');
      expect(find.byType(CourseResultScreen), findsOneWidget);
      final screen = t.widget<CourseResultScreen>(
        find.byType(CourseResultScreen),
      );
      expect(screen.courses.single.length, 2);
      expectNoResultExplanation(park);
      expect(s.requests.single.count, 1);
      expect(s.requests.single.mode, 'course');
      expect(s.requests.single.slotTypes, isEmpty);
    },
  );
  testWidgets('C14: malformed scoped 422 cannot fall back to blanket bool', (
    t,
  ) async {
    final s = Source();
    final body = fixture('F02-only-unknown-422');
    body['metadata']['consent_offer']['alternatives'] = false;
    s.initialOverride = body;
    await start(t, s);
    expect(s.requests.length, 1);
    expect(find.textContaining('대안의 동의 범위를 확인하지 못했어요.'), findsOneWidget);
    expect(find.text('다시 찾기'), findsNothing);
  });
  test(
    'real API source serializes scoped request without reinterpreting',
    () async {
      late Map wire;
      final mock = MockClient((request) async {
        expect(request.url.path, '/recommend/spot');
        wire = jsonDecode(request.body) as Map;
        return http.Response(
          jsonEncode({'success': true, 'data': fixture('F03-cafe-scoped-200')}),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });
      await http.runWithClient(() async {
        final request =
            RecommendationRequest(
                  mode: 'spot',
                  userText: '실내 카페 또는 공원',
                  transport: '대중교통',
                  region: '천안',
                  lat: 36.8066,
                  lng: 127.1469,
                  tags: [],
                  count: 3,
                  slotTypes: [],
                  seed: 101,
                )
                .reviewed(
                  token: 'fixture-token',
                  planId: 'example-v13-plan-nonce',
                )
                .reviewed(
                  token: 'fixture-token',
                  unverified: true,
                  consentPlanId: 'example-v13-plan-nonce',
                  acceptedConditionIds: ['s1.a1.c1'],
                );
        await const ApiRecommendationSource().recommend(request);
        expect(wire['consent_plan_id'], 'example-v13-plan-nonce');
        expect(wire['accepted_condition_ids'], ['s1.a1.c1']);
        expect(wire['intent_token'], 'fixture-token');
        expect(wire['seed'], 101);
      }, () => mock);
    },
  );
  test(
    'actual ApiClient accepts server-owned fixtures and preserves scoped wire',
    () async {
      for (final f in [...contract['fixtures'], ...contract['errors']]) {
        late Map wire;
        final client = ApiClient(
          client: MockClient((request) async {
            wire = jsonDecode(request.body) as Map;
            return http.Response(
              jsonEncode(f['node_body']),
              f['status'] as int,
              headers: {'content-type': 'application/json; charset=utf-8'},
            );
          }),
        );
        final path = f['id'] == 'F05-preview-one-visit'
            ? '/travel/interpret'
            : '/recommend/spot';
        final response = await client.post(path, copy(f['request']));
        expect(wire, f['request']);
        if (f['status'] == 200) {
          expect(response, f['node_body']);
        } else {
          expect(response['reason'], f['flask_body']['reason']);
        }
      }
    },
  );
}
