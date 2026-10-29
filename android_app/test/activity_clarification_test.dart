import 'dart:async';
import 'dart:convert';
import 'package:ai_travel_app/input_screen.dart';
import 'package:ai_travel_app/location_service.dart';
import 'package:ai_travel_app/network/api_client.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'package:ai_travel_app/spot_result_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

const original = '연인이랑 데이트 할 곳을 찾고있어요';
const options = [
  {'value': '음식', 'label': '식사'},
  {'value': '카페', 'label': '카페·디저트'},
  {'value': '자연·산책', 'label': '산책·자연'},
  {'value': '문화·역사', 'label': '전시·문화관람'},
  {'value': '체험', 'label': '체험·만들기'},
  {'value': '실내 오락', 'label': '실내 놀거리'},
];
Map<String, dynamic> clarification() => {
  'clarification_required': true,
  'clarification': {
    'kind': 'activity',
    'message': '어떤 활동을 할지 골라주세요.',
    'options': options,
    'token': 'signed-choice',
  },
  'travel_request': {
    'source_text': original,
    'companion': {'value': '연인과'},
    'ambiguities': [
      {'quote': '데이트', 'reason': '활동 미정'},
    ],
  },
};

class FixedLocation implements LocationSource {
  @override
  Future<LocationFix> locate() async => const LocationFix(36.8151, 127.1139);
}

class ClarifyingSource implements IntentRecommendationSource {
  final interpreted = <RecommendationRequest>[];
  final recommended = <RecommendationRequest>[];
  bool repeat = false;
  Completer<Map<String, dynamic>?>? pendingSelection;
  @override
  Future<List<String>> suggestTags(String text) async => [];
  @override
  Future<Map<String, dynamic>?> interpret(RecommendationRequest request) async {
    interpreted.add(request);
    if (request.activityChoice == null || repeat) {
      return {'success': true, 'data': clarification()};
    }
    if (pendingSelection != null) return pendingSelection!.future;
    return {
      'success': true,
      'data': {
        'clarification_required': false,
        'intent_token': 'confirmed-intent',
        'target_mode': request.mode,
        'target_count': request.count,
        'mode_switch_required': false,
        'travel_request': {
          'source_text': request.userText,
          'summary': '연인과 · 선택한 카페',
          'manual_overrides': ['직접 선택한 활동: 카페·디저트'],
          'stages': [],
          'ambiguities': [],
          'unsupported': [],
          'exclusions': [],
        },
      },
    };
  }

  @override
  Future<Map<String, dynamic>?> recommend(RecommendationRequest request) async {
    recommended.add(request);
    return {
      'places': [
        {
          'place_id': 'test:cafe',
          'name': '선택 범위의 카페',
          'address': '충남 천안시',
          'lat': 36.8,
          'lng': 127.1,
        },
      ],
    };
  }
}

Future<void> tap(WidgetTester tester, String label) async {
  final f = find.text(label).last;
  await tester.ensureVisible(f);
  await tester.pump(const Duration(milliseconds: 100));
  await tester.tap(f);
  await tester.pump(const Duration(milliseconds: 400));
}

Future<void> mount(
  WidgetTester tester,
  ClarifyingSource source, {
  double scale = 1,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(
          context,
        ).copyWith(textScaler: TextScaler.linear(scale)),
        child: child!,
      ),
      home: InputScreen(
        mode: 'spot',
        source: source,
        locationSource: FixedLocation(),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tap(tester, '다음');
  await tester.enterText(find.byType(TextField), original);
  await tap(tester, '장소 추천받기');
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  testWidgets('confirmed activity keeps text and controls, then recommends', (
    tester,
  ) async {
    final source = ClarifyingSource();
    await mount(tester, source);
    expect(find.text('어떤 활동을 원하세요?'), findsOneWidget);
    for (final option in options) {
      expect(
        find.text(option['value'] == '문화·역사' ? '전시·문화' : option['label']!),
        findsWidgets,
      );
    }
    expect(source.recommended, isEmpty);
    expect(source.interpreted.single.activityChoice, isNull);
    expect(source.interpreted.single.tags, isEmpty);
    await tap(tester, '식사');
    await tap(tester, '카페·디저트');
    expect(source.interpreted.length, 1);
    expect(source.recommended, isEmpty);
    await tap(tester, '카페·디저트 추천받기');
    expect(source.interpreted.length, 2);
    final first = source.interpreted.first, chosen = source.interpreted.last;
    expect(chosen.userText, original);
    expect(chosen.seed, first.seed);
    expect(chosen.tags, first.tags);
    expect(chosen.lat, first.lat);
    expect(chosen.lng, first.lng);
    expect(chosen.count, first.count);
    expect(chosen.slotTypes, first.slotTypes);
    expect(chosen.activityChoice, '카페');
    expect(chosen.clarificationToken, 'signed-choice');
    expect(chosen.interpretationBody['activity_choice'], '카페');
    expect(chosen.interpretationBody['clarification_token'], 'signed-choice');
    expect(find.text('이렇게 이해했어요'), findsNothing);
    expect(source.recommended.length, 1);
    await tester.pumpAndSettle();
    expect(find.byType(SpotResultScreen), findsOneWidget);
    final recommended = source.recommended.single;
    expect(recommended.userText, original);
    expect(recommended.activityChoice, '카페');
    expect(recommended.intentToken, 'confirmed-intent');
    expect(recommended.intentFields['activity_choice'], '카페');
    expect(recommended.intentFields.containsKey('clarification_token'), false);
    expect(recommended.tags, isNot(contains('소개팅/첫만남')));
    await tap(tester, '같은 조건으로 새 추천');
    await tester.pumpAndSettle();
    expect(find.text('어떤 활동을 원하세요?'), findsNothing);
    expect(source.interpreted.last.seed, isNot(first.seed));
    expect(
      source.interpreted[source.interpreted.length - 2].clarificationToken,
      isNull,
    );
    expect(source.interpreted.last.activityChoice, '카페');
    expect(source.interpreted.last.clarificationToken, 'signed-choice');
    expect(source.recommended.length, 2);
    expect(source.recommended.last.acceptUnverified, false);
    await tap(tester, '조건 수정');
    await tap(tester, '다음');
    expect(find.byType(TextField), findsOneWidget);
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller!.text,
      original,
    );
    await tap(tester, '장소 추천받기');
    expect(find.text('어떤 활동을 원하세요?'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  testWidgets(
    'cancel activity selection keeps original input without choosing a default',
    (tester) async {
      final source = ClarifyingSource();
      await mount(tester, source);
      await tap(tester, '식사');
      await tap(tester, '입력한 문장 수정');
      await tester.pumpAndSettle();
      expect(source.interpreted.length, 1);
      expect(source.recommended, isEmpty);
      expect(
        tester.widget<TextField>(find.byType(TextField)).controller!.text,
        original,
      );
      await tester.enterText(find.byType(TextField), '원문을 수정했어요');
      await tap(tester, '장소 추천받기');
      expect(source.interpreted.last.userText, '원문을 수정했어요');
      expect(source.interpreted.last.activityChoice, isNull);
      expect(source.interpreted.last.clarificationToken, isNull);
    },
  );
  testWidgets(
    'repeated clarification stops instead of looping or recommending',
    (tester) async {
      final source = ClarifyingSource()..repeat = true;
      await mount(tester, source);
      await tap(tester, '산책·자연');
      await tap(tester, '산책·자연 추천받기');
      await tester.pumpAndSettle();
      expect(source.interpreted.length, 2);
      expect(source.recommended, isEmpty);
      expect(find.textContaining('고른 활동으로 요청을 확정하지 못했어요.'), findsOneWidget);
    },
  );
  testWidgets('late selected interpretation after leaving screen is ignored', (
    tester,
  ) async {
    final source = ClarifyingSource()
      ..pendingSelection = Completer<Map<String, dynamic>?>();
    await mount(tester, source);
    await tap(tester, '체험·만들기');
    await tap(tester, '체험·만들기 추천받기');
    expect(source.interpreted.length, 2);
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    source.pendingSelection!.complete({'error': 'late'});
    await tester.pumpAndSettle();
    expect(source.recommended, isEmpty);
    expect(source.interpreted.last.cancellation!.isCancelled, true);
    expect(tester.takeException(), isNull);
  });
  test(
    'HTTP boundary accepts signed clarification without intent token and rejects malformed choices',
    () async {
      var payload = clarification();
      final client = ApiClient(
        client: MockClient(
          (request) async => http.Response(
            jsonEncode({'success': true, 'data': payload}),
            200,
            headers: {'content-type': 'application/json'},
          ),
        ),
      );
      final accepted = await client.post('/travel/interpret', {
        'user_text': original,
      });
      expect(accepted.containsKey('error'), false);
      expect((accepted['data'] as Map)['clarification_required'], true);
      for (final invalid in [
        {
          ...clarification(),
          'clarification': {
            ...(clarification()['clarification'] as Map),
            'token': '',
          },
        },
        {
          ...clarification(),
          'clarification': {
            ...(clarification()['clarification'] as Map),
            'options': [
              {'value': 'unknown', 'label': '임의 활동'},
            ],
          },
        },
        {
          ...clarification(),
          'clarification': {
            ...(clarification()['clarification'] as Map),
            'options': [options.first, options.first],
          },
        },
      ]) {
        payload = Map<String, dynamic>.from(invalid);
        expect(
          (await client.post('/travel/interpret', {}))['reason'],
          'invalid_response',
        );
      }
      client.close();
    },
  );
  testWidgets('sixth activity remains selectable on narrow large-text screen', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final source = ClarifyingSource();
    await mount(tester, source, scale: 1.6);
    await tap(tester, '실내 놀거리');
    await tap(tester, '실내 놀거리 추천받기');
    expect(source.interpreted.last.activityChoice, '실내 오락');
    expect(find.text('이렇게 이해했어요'), findsNothing);
    expect(source.recommended.length, 1);
    await tester.pumpAndSettle();
    expect(find.byType(SpotResultScreen), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
