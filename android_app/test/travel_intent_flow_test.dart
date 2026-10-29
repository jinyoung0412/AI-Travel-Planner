import 'dart:async';
import 'dart:convert';
import 'package:ai_travel_app/input_screen.dart';
import 'package:ai_travel_app/location_service.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'package:ai_travel_app/network/api_client.dart';
import 'package:ai_travel_app/network/request_cancellation.dart';
import 'package:ai_travel_app/course_result_screen.dart';
import 'package:ai_travel_app/spot_result_screen.dart';
import 'package:ai_travel_app/local_storage_service.dart';
import 'package:ai_travel_app/saved_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

const text = '연인과 산책하다가 시끌벅적한 야장에 가고 싶다';

class FixedLocation implements LocationSource {
  @override
  Future<LocationFix> locate() async => const LocationFix(36.8151, 127.1139);
}

Map<String, dynamic> place(String id, String activity) => {
  'place_id': id,
  'name': '장소 $id',
  'lat': 36.8151,
  'lng': 127.1139,
  'address': '충남 천안시 테스트로 1',
  'category': activity,
  'travel_explanation': {
    'activity': activity,
    'reason': '요청한 장소 종류에 해당합니다.',
    'unverified_conditions': ['야외 좌석', '활기찬 분위기'],
    'selection_method': 'rules_fallback',
  },
};

class FakeIntentSource implements IntentRecommendationSource {
  bool multiple;
  bool unknown;
  bool negativeIndoor = false;
  bool ambiguous = false;
  bool unsupported = false;
  Completer<Map<String, dynamic>?>? pending;
  Completer<Map<String, dynamic>?>? pendingRecommendation;
  final interpretations = <RecommendationRequest>[];
  final recommendations = <RecommendationRequest>[];
  FakeIntentSource({this.multiple = false, this.unknown = false});
  @override
  Future<List<String>> suggestTags(String text) async => [];
  @override
  Future<Map<String, dynamic>?> interpret(RecommendationRequest request) async {
    interpretations.add(request);
    if (pending != null) return pending!.future;
    return {
      'success': true,
      'data': {
        'intent_token': 'reviewed-token',
        'target_mode': multiple ? 'course' : request.mode,
        'target_count': multiple ? 1 : request.count,
        'mode_switch_required': multiple,
        'travel_request': {
          'summary': multiple ? '연인과 · 산책 → 야외 맥주' : '카페',
          'stages': [
            {
              'conditions': negativeIndoor
                  ? [
                      {
                        'field': 'indoor',
                        'value': false,
                        'quote': '실내 말고',
                        'required': true,
                      },
                    ]
                  : multiple
                  ? [
                      {'quote': '야장', 'required': true},
                    ]
                  : [],
            },
          ],
          'manual_overrides': [],
          'ambiguities': ambiguous
              ? [
                  {'quote': '그곳', 'reason': '장소를 알려주세요'},
                ]
              : [],
          'unsupported': unsupported
              ? [
                  {'quote': '기타 요청', 'reason': '지원하지 않는 요청'},
                ]
              : [],
          'exclusions': [],
        },
      },
    };
  }

  @override
  Future<Map<String, dynamic>?> recommend(RecommendationRequest request) async {
    recommendations.add(request);
    if (pendingRecommendation != null) return pendingRecommendation!.future;
    if (unknown && !request.acceptUnverified) {
      return {
        'error': '필수 조건 미확인',
        'reason': 'unverified_conditions',
        'metadata': {
          'unverified_conditions': [
            {'label': '야외 좌석'},
          ],
        },
      };
    }
    return {
      'success': true,
      'data': {
        if (request.mode == 'course')
          'courses': [
            [place('1', '공원'), place('2', '맥주')],
          ],
        if (request.mode == 'spot') 'places': [place('1', '카페')],
        'course_metrics': [],
        'metadata': {
          'travel_request': {'summary': '산책 → 야외 맥주'},
          'intent_status': 'unverified_alternative',
          'selection_method': 'rules_fallback',
        },
      },
    };
  }
}

Future<void> tap(WidgetTester tester, String label) async {
  final finder = find.text(label).last;
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pump(const Duration(milliseconds: 300));
}

Future<void> mount(
  WidgetTester tester,
  FakeIntentSource source, {
  String mode = 'spot',
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: InputScreen(
        mode: mode,
        source: source,
        locationSource: FixedLocation(),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tap(tester, '다음');
  await tester.enterText(
    find.byType(TextField),
    source.multiple ? text : '친구와 조용한 카페',
  );
  if (mode == 'course') await tap(tester, '다음');
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets(
    'multi-visit spot requires consent, then explicit unverified alternative consent',
    (tester) async {
      final source = FakeIntentSource(multiple: true, unknown: true);
      await mount(tester, source);
      await tap(tester, '장소 추천받기');
      expect(find.text('이렇게 이해했어요'), findsNothing);
      expect(find.text('코스로 추천할까요?'), findsOneWidget);
      expect(source.recommendations, isEmpty);
      await tap(tester, '문장 수정');
      expect(source.recommendations, isEmpty);
      await tap(tester, '장소 추천받기');
      await tap(tester, '코스로 전환해 추천');
      expect(find.text('조건을 바꿔볼까요?'), findsOneWidget);
      expect(source.recommendations.length, 1);
      await tap(tester, '다시 찾기');
      await tester.pumpAndSettle();
      expect(find.byType(CourseResultScreen), findsOneWidget);
      expect(source.recommendations.length, 2);
      final request = source.recommendations.last;
      expect(request.mode, 'course');
      expect(request.naturalPlan, true);
      expect(request.interpretationBody['plan_mode'], 'natural');
      expect(request.interpretationBody['spot_count'], 3);
      expect(request.count, 1);
      expect(request.userText, text);
      expect(request.acceptUnverified, true);
      expect(request.slotTypes, isEmpty);
      expect(find.text('필수 조건 미확인'), findsNothing);
      expect(find.textContaining('필수 조건을 확인하지 못한 대안'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('simple cafe stays a spot and retains the full sentence', (
    tester,
  ) async {
    final source = FakeIntentSource();
    await mount(tester, source);
    await tap(tester, '장소 추천받기');
    expect(find.text('코스로 전환해 추천'), findsNothing);
    expect(find.text('이렇게 이해했어요'), findsNothing);
    await tester.pumpAndSettle();
    expect(find.byType(SpotResultScreen), findsOneWidget);
    expect(source.recommendations.single.userText, '친구와 조용한 카페');
    expect(source.recommendations.single.intentToken, 'reviewed-token');
  });

  testWidgets(
    'double tap and previous screen invalidate a late interpretation',
    (tester) async {
      final source = FakeIntentSource()
        ..pending = Completer<Map<String, dynamic>?>();
      await mount(tester, source);
      await tap(tester, '장소 추천받기');
      await tap(tester, '이전');
      expect(source.interpretations.single.cancellation!.isCancelled, true);
      source.pending!.complete({'error': 'late'});
      await tester.pumpAndSettle();
      expect(source.recommendations, isEmpty);
      expect(find.text('이렇게 이해했어요'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'manual slots remain three while natural two-stage mode is optional',
    (tester) async {
      final source = FakeIntentSource();
      await mount(tester, source, mode: 'course');
      expect(find.byType(SwitchListTile), findsNothing);
      expect(find.text('방문 순서'), findsOneWidget);
      await tap(tester, '코스 추천받기');
      expect(source.interpretations.single.naturalPlan, false);
      expect(source.interpretations.single.slotTypes.length, 3);
      await tester.pumpAndSettle();
      expect(find.byType(CourseResultScreen), findsOneWidget);
      expect(source.recommendations.single.slotTypes.length, 3);
    },
  );

  testWidgets(
    'saved DTO keeps explanations and does not rerun recommendation',
    (tester) async {
      final p = place('saved', '맥주');
      await LocalStorageService.saveSpot(p);
      final saved = await LocalStorageService.getSavedSpots();
      expect(saved.single['travel_explanation'], p['travel_explanation']);
      await tester.pumpWidget(const MaterialApp(home: SavedScreen()));
      await tester.pumpAndSettle();
      expect(find.textContaining('확인 필요: 야외 좌석'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  test(
    'course HTTP body carries source text, controls and reviewed token',
    () async {
      late Map body;
      final client = ApiClient(
        client: MockClient((request) async {
          body = jsonDecode(request.body) as Map;
          return http.Response(
            jsonEncode({'courses': [], 'metadata': {}}),
            200,
          );
        }),
      );
      final result = await client.getCourseRecommendation(
        userText: text,
        region: '천안',
        transport: '차',
        userLat: 36.8,
        userLng: 127.1,
        personaTags: ['연인과'],
        count: 1,
        spotCount: 2,
        intentFields: {
          'intent_version': 1,
          'plan_mode': 'natural',
          'intent_token': 'token',
          'recent_place_ids': ['old:1'],
        },
      );
      expect(result.containsKey('error'), false);
      expect(body['user_text'], text);
      expect(body['spot_count'], 2);
      expect(body['intent_token'], 'token');
      expect(body['recent_place_ids'], ['old:1']);
      client.close();
    },
  );

  test('cancelled operation never sends another request', () async {
    final cancel = RequestCancellation()..cancel();
    final client = ApiClient(
      client: MockClient((_) async => throw StateError('must not send')),
    );
    final result = await client.post(
      '/travel/interpret',
      {},
      cancellation: cancel,
    );
    expect(result.containsKey('error'), true);
    client.close();
  });
  testWidgets(
    'fresh result request asks again before accepting unknown conditions',
    (tester) async {
      final source = FakeIntentSource(unknown: true);
      await mount(tester, source);
      await tap(tester, '장소 추천받기');
      await tap(tester, '다시 찾기');
      await tester.pumpAndSettle();
      final firstSeed = source.recommendations.last.seed;
      await tap(tester, '같은 조건으로 새 추천');
      expect(find.text('이렇게 이해했어요'), findsNothing);
      expect(source.interpretations.length, 2);
      expect(source.interpretations.last.seed, isNot(firstSeed));
      expect(source.interpretations.last.acceptUnverified, false);
      expect(source.interpretations.last.recentPlaceIds, ['1']);
      expect(source.recommendations.last.recentPlaceIds, ['1']);
      expect(find.text('조건을 바꿔볼까요?'), findsOneWidget);
      expect(source.recommendations.last.acceptUnverified, false);
      await tap(tester, '조건 유지');
      await tester.pumpAndSettle();
      expect(find.byType(TextField), findsOneWidget);
      expect(find.byType(SpotResultScreen), findsNothing);
      expect(source.recommendations.length, 3);
      await tap(tester, '이전 추천 다시 보기');
      await tester.pumpAndSettle();
      expect(find.byType(SpotResultScreen), findsOneWidget);
      expect(source.recommendations.length, 3);
    },
  );

  testWidgets(
    'declining unknown course conditions returns to the sentence step',
    (tester) async {
      final source = FakeIntentSource(unknown: true);
      await mount(tester, source, mode: 'course');
      await tap(tester, '코스 추천받기');
      await tap(tester, '조건 유지');
      await tester.pumpAndSettle();
      expect(find.byType(TextField), findsOneWidget);
      expect(find.text('친구와 조용한 카페'), findsOneWidget);
      expect(source.recommendations.length, 1);
    },
  );
  testWidgets('unresolved intent never proceeds to recommendation', (
    tester,
  ) async {
    final source = FakeIntentSource()..ambiguous = true;
    await mount(tester, source);
    await tap(tester, '장소 추천받기');
    expect(find.text('문장을 조금만 바꿔주세요'), findsOneWidget);
    expect(find.textContaining('장소를 알려주세요'), findsOneWidget);
    expect(source.recommendations, isEmpty);
    await tap(tester, '문장 수정');
    expect(find.byType(TextField), findsOneWidget);
    source.ambiguous = false;
    source.unsupported = true;
    await tap(tester, '장소 추천받기');
    expect(find.textContaining('지원하지 않는 요청'), findsOneWidget);
    expect(source.recommendations, isEmpty);
  });

  testWidgets(
    'direct recommendation releases text focus and does not reopen keyboard',
    (tester) async {
      final source = FakeIntentSource()
        ..pendingRecommendation = Completer<Map<String, dynamic>?>();
      await mount(tester, source);
      await tester.showKeyboard(find.byType(TextField));
      expect(
        tester
            .widget<EditableText>(find.byType(EditableText))
            .focusNode
            .hasFocus,
        true,
      );
      await tap(tester, '장소 추천받기');
      expect(find.text('이렇게 이해했어요'), findsNothing);
      expect(source.recommendations.length, 1);
      expect(
        tester
            .widget<EditableText>(find.byType(EditableText))
            .focusNode
            .hasFocus,
        false,
      );
      expect(tester.testTextInput.isVisible, false);
      source.pendingRecommendation!.complete({
        'places': [place('1', '카페')],
      });
      await tester.pumpAndSettle();
      expect(find.byType(SpotResultScreen), findsOneWidget);
      expect(tester.testTextInput.isVisible, false);
      expect(tester.takeException(), isNull);
    },
  );
  for (final mode in ['spot', 'course']) {
    testWidgets(
      '$mode reroll sends displayed IDs and editing conditions clears history',
      (tester) async {
        final source = FakeIntentSource();
        await mount(tester, source, mode: mode);
        await tap(tester, mode == 'spot' ? '장소 추천받기' : '코스 추천받기');
        await tester.pumpAndSettle();
        expect(source.recommendations.single.recentPlaceIds, isEmpty);
        await tap(tester, '같은 조건으로 새 추천');
        await tester.pumpAndSettle();
        final ids = mode == 'spot' ? ['1'] : ['1', '2'];
        expect(source.interpretations.last.recentPlaceIds, ids);
        expect(source.recommendations.last.recentPlaceIds, ids);
        expect(
          source.recommendations.last.intentFields['recent_place_ids'],
          ids,
        );
        await tap(tester, '조건 수정');
        await tester.pumpAndSettle();
        await tap(tester, '차');
        await tap(tester, '다음');
        if (mode == 'course') await tap(tester, '다음');
        await tap(tester, mode == 'spot' ? '장소 추천받기' : '코스 추천받기');
        await tester.pumpAndSettle();
        expect(source.interpretations.last.recentPlaceIds, isEmpty);
        expect(source.recommendations.last.recentPlaceIds, isEmpty);
        expect(source.recommendations.last.transport, '차');
        expect(tester.takeException(), isNull);
      },
    );
  }
}
