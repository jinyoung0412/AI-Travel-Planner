import 'package:ai_travel_app/input_screen.dart';
import 'package:ai_travel_app/location_service.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class FixedLocation implements LocationSource {
  @override
  Future<LocationFix> locate() async => const LocationFix(36.76979, 126.95182);
}

class MissingMiddle implements RecommendationSource {
  final bool limited;
  MissingMiddle({this.limited = false});
  final requests = <RecommendationRequest>[];
  @override
  Future<List<String>> suggestTags(String text) async => [];
  @override
  Future<Map<String, dynamic>?> recommend(RecommendationRequest request) async {
    requests.add(request);
    return {
      'error': '후보 부족',
      'metadata': {
        'reason': limited
            ? 'insufficient_distinct_places'
            : 'missing_slot_candidates',
        'slot_types': request.slotTypes,
        'slot_candidate_counts': limited ? [2, 2, 2] : [354, 0, 118],
        'radius_km': 4.5,
      },
    };
  }
}

void main() {
  for (final testCase in [
    ('출발점·교통 수정', false),
    ('방문 순서 수정', false),
    ('방문 순서 수정', true),
  ]) {
    final (action, manualWithText) = testCase;
    testWidgets(
      'shortage returns to chosen controls: $action, manual text=$manualWithText',
      (tester) async {
        final source = MissingMiddle();
        await tester.pumpWidget(
          MaterialApp(
            home: InputScreen(
              mode: 'course',
              source: source,
              locationSource: FixedLocation(),
            ),
          ),
        );
        await tester.pumpAndSettle();
        Future<void> tap(String label) async {
          final f = find.text(label).last;
          await tester.ensureVisible(f);
          await tester.pump(const Duration(milliseconds: 300));
          await tester.tap(f);
          // The submit spinner continues behind the shortage dialog until it closes.
          await tester.pump(const Duration(milliseconds: 500));
        }

        await tap('다음');
        if (manualWithText) {
          await tester.enterText(find.byType(TextField), '카페');
        }
        await tap('직접 태그 선택하기');
        expect(find.text('누구와 함께하나요?'), findsOneWidget);
        await tap('친구와');
        for (
          var i = 0;
          i < 5 && find.text('선택 완료').evaluate().isNotEmpty;
          i++
        ) {
          await tap('선택 완료');
        }
        await tap('다음');
        expect(find.text('방문 순서'), findsOneWidget);
        await tap('코스 추천받기');
        expect(find.text('2번째 산책·자연 장소를 찾지 못했어요'), findsOneWidget);
        expect(find.text('활동이나 출발점·이동수단을 바꿔주세요.'), findsOneWidget);
        await tap(action);
        expect(source.requests.length, 1);
        expect(source.requests.single.slotTypes, ['음식', '자연·산책', '카페']);
        expect(source.requests.single.tags, contains('친구와'));
        expect(source.requests.single.transport, '대중교통');
        expect(
          find.text(action == '출발점·교통 수정' ? '어디서 놀까요?' : '방문 순서'),
          findsOneWidget,
        );
        expect(source.requests.single.userText, manualWithText ? '카페' : '');
        expect(source.requests.single.naturalPlan, isFalse);
        if (action == '출발점·교통 수정') {
          await tap('차');
          await tap('다음');
          expect(find.text('친구와'), findsOneWidget);
          await tap('다음');
        } else {
          await tap('산책·자연');
          await tap('카페·디저트');
        }
        await tap('코스 추천받기');
        expect(source.requests, hasLength(2));
        expect(source.requests.last.tags, contains('친구와'));
        expect(source.requests.last.userText, manualWithText ? '카페' : '');
        expect(
          source.requests.last.transport,
          action == '출발점·교통 수정' ? '차' : '대중교통',
        );
        expect(
          source.requests.last.slotTypes,
          action == '출발점·교통 수정' ? ['음식', '자연·산책', '카페'] : ['음식', '카페', '카페'],
        );
        expect(tester.takeException(), isNull);
      },
    );
  }
  testWidgets(
    'culture shortage offers control changes and preserves repeated activities',
    (tester) async {
      final source = MissingMiddle(limited: true);
      await tester.pumpWidget(
        MaterialApp(
          home: InputScreen(
            mode: 'course',
            source: source,
            locationSource: FixedLocation(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      Future<void> tap(String label) async {
        final f = find.text(label).last;
        await tester.ensureVisible(f);
        await tester.pump(const Duration(milliseconds: 300));
        await tester.tap(f);
        // A shortage dialog intentionally keeps the submit operation pending.
        await tester.pump(const Duration(milliseconds: 500));
      }

      await tap('다음');
      await tap('직접 태그 선택하기');
      await tap('친구와');
      for (var i = 0; i < 5 && find.text('선택 완료').evaluate().isNotEmpty; i++) {
        await tap('선택 완료');
      }
      await tap('다음');
      for (final slot in ['식사', '산책·자연', '카페·디저트']) {
        await tap(slot);
        await tap('전시·문화관람');
      }
      await tap('코스 추천받기');
      expect(find.text('코스를 만들 장소가 부족해요'), findsOneWidget);
      expect(find.text('활동이나 출발점·이동수단을 바꿔주세요.'), findsOneWidget);
      await tap('방문 순서 수정');
      expect(source.requests.single.slotTypes, ['문화·역사', '문화·역사', '문화·역사']);
      expect(find.text('방문 순서'), findsOneWidget);
      expect(find.text('전시·문화관람'), findsNWidgets(3));
      await tap('전시·문화관람');
      await tap('카페·디저트');
      await tap('코스 추천받기');
      expect(source.requests, hasLength(2));
      expect(source.requests.last.slotTypes, ['문화·역사', '문화·역사', '카페']);
      expect(source.requests.last.tags, contains('친구와'));
      expect(tester.takeException(), isNull);
    },
  );
}
