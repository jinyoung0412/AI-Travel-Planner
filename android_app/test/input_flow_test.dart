import 'dart:async';
import 'package:ai_travel_app/transit_hubs.dart';
import 'package:ai_travel_app/input_screen.dart';
import 'package:ai_travel_app/location_service.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'package:ai_travel_app/spot_result_screen.dart';
import 'package:ai_travel_app/course_result_screen.dart';
import 'package:ai_travel_app/network/tag_suggestion_exception.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class FakeLocation implements LocationSource {
  Future<LocationFix> Function() next;
  FakeLocation(this.next);
  @override
  Future<LocationFix> locate() => next();
}

class CancellableFakeLocation extends FakeLocation
    implements CancellableLocationSource {
  final Completer<LocationFix> pending;
  int cancels = 0;
  CancellableFakeLocation() : this._(Completer<LocationFix>());
  CancellableFakeLocation._(this.pending) : super(() => pending.future);
  @override
  Future<void> cancel() async {
    cancels++;
    if (!pending.isCompleted) {
      pending.completeError(const LocationException(LocationFailure.cancelled));
    }
  }
}

class FakeRecommendations implements RecommendationSource {
  final requests = <RecommendationRequest>[];
  final responses = <Completer<Map<String, dynamic>?>>[];
  final suggestions = <Completer<List<String>>>[];
  @override
  Future<Map<String, dynamic>?> recommend(RecommendationRequest request) {
    requests.add(request);
    final response = Completer<Map<String, dynamic>?>();
    responses.add(response);
    return response.future;
  }

  @override
  Future<List<String>> suggestTags(String text) {
    final response = Completer<List<String>>();
    suggestions.add(response);
    return response.future;
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  Future<void> mount(
    WidgetTester tester,
    FakeRecommendations source, {
    String mode = 'spot',
    FakeLocation? location,
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
          mode: mode,
          source: source,
          locationSource:
              location ??
              FakeLocation(() async => const LocationFix(36.8151, 127.1139)),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> tap(WidgetTester tester, String text) async {
    final label = find.text(text).last;
    final choices = find.ancestor(of: label, matching: find.byType(ChoiceChip));
    final finder = choices.evaluate().isEmpty ? label : choices;
    await tester.ensureVisible(finder);
    await tester.pump();
    await tester.tap(finder);
    await tester.pumpAndSettle();
  }

  bool selected(WidgetTester tester, String label) => tester
      .widget<ChoiceChip>(
        find.ancestor(of: find.text(label), matching: find.byType(ChoiceChip)),
      )
      .selected;

  testWidgets(
    'GPS failure is recoverable and region selection works without permission',
    (tester) async {
      final location = FakeLocation(
        () async =>
            throw const LocationException(LocationFailure.serviceDisabled),
      );
      await mount(tester, FakeRecommendations(), location: location);
      expect(find.textContaining('위치 서비스가 꺼져'), findsOneWidget);
      await tap(tester, '다음');
      expect(find.text('어디서 놀까요?'), findsOneWidget);
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
      await tap(tester, '천안');
      await tap(tester, '천안역');
      await tap(tester, '다음');
      expect(find.byType(TextField), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'GPS retry restores current location and late completion after dispose is ignored',
    (tester) async {
      final location = FakeLocation(
        () async =>
            throw const LocationException(LocationFailure.deniedForever),
      );
      await mount(tester, FakeRecommendations(), location: location);
      final completion = Completer<LocationFix>();
      location.next = () => completion.future;
      await tester.tap(find.text('위치 다시 확인'));
      await tester.pump();
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      completion.complete(const LocationFix(36.8, 127.1));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets('double submit is locked and back cancels an old response', (
    tester,
  ) async {
    final source = FakeRecommendations();
    await mount(tester, source);
    await tap(tester, '다음');
    await tap(tester, '친구와');
    await tester.tap(find.text('장소 추천받기'));
    await tester.tap(find.text('장소 추천받기'));
    await tester.pump();
    expect(source.requests.length, 1);
    await tap(tester, '이전');
    source.responses.single.complete({
      'places': [
        {'name': '이전 요청'},
      ],
    });
    await tester.pumpAndSettle();
    expect(find.byType(SpotResultScreen), findsNothing);
    await tap(tester, '다음');
    await tester.tap(find.text('장소 추천받기'));
    await tester.pump();
    source.responses.last.complete({
      'data': {
        'places': [
          {
            'place_id': 'naver:1',
            'name': '새 요청',
            'lat': '36.8',
            'lng': '127.1',
            'tags': ['친구와'],
          },
        ],
      },
    });
    await tester.pumpAndSettle();
    expect(find.text('새 요청'), findsOneWidget);
    expect(source.requests.last.tags, ['친구와']);
    expect(tester.takeException(), isNull);
  });
  testWidgets(
    'manual tag changes and edited text reject stale AI suggestions',
    (tester) async {
      final source = FakeRecommendations();
      await mount(tester, source);
      await tap(tester, '다음');
      await tester.enterText(find.byType(TextField), '첫 요청');
      await tester.tap(find.text('AI 태그 자동 선택'));
      await tester.pump();
      await tester.ensureVisible(find.text('친구와'));
      await tester.tap(find.text('친구와'));
      await tester.pump();
      source.suggestions.single.complete(['혼자']);
      await tester.pumpAndSettle();
      expect(selected(tester, '친구와'), true);
      expect(selected(tester, '혼자'), false);
      await tester.enterText(find.byType(TextField), '둘째 요청');
      await tester.ensureVisible(find.text('AI 태그 자동 선택'));
      await tester.tap(find.text('AI 태그 자동 선택'));
      await tester.pump();
      await tester.enterText(find.byType(TextField), '셋째 요청');
      source.suggestions.last.complete(['연인과']);
      await tester.pumpAndSettle();
      expect(selected(tester, '친구와'), true);
      expect(selected(tester, '연인과'), false);
    },
  );
  testWidgets(
    'small-screen course keeps slot edits and filters invisible AI tags',
    (tester) async {
      tester.view.physicalSize = const Size(320, 568);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final source = FakeRecommendations();
      await mount(tester, source, mode: 'course', scale: 1.5);
      await tap(tester, '다음');
      await tester.enterText(find.byType(TextField), '친구와 쇼핑');
      await tester.ensureVisible(find.text('AI 태그 자동 선택'));
      await tester.tap(find.text('AI 태그 자동 선택'));
      await tester.pump();
      source.suggestions.single.complete([
        '친구와',
        '혼자',
        '조용한',
        '감성적인',
        '쇼핑',
        '실내 위주',
        '모르는 태그',
      ]);
      await tester.pumpAndSettle();
      expect(selected(tester, '친구와'), true);
      expect(selected(tester, '혼자'), false);
      await tap(tester, '다음');
      await tap(tester, '자연·산책');
      await tap(tester, '쇼핑');
      await tap(tester, '이전');
      await tap(tester, '이전');
      await tap(tester, '3곳');
      await tap(tester, '다음');
      await tap(tester, '다음');
      await tester.tap(find.text('코스 추천받기'));
      await tester.pump();
      final request = source.requests.single;
      expect(request.slotTypes, ['음식', '쇼핑', '카페']);
      expect(request.tags, ['친구와', '조용한', '감성적인']);
      expect(request.count, 3);
      source.responses.single.complete({
        'courses': [],
        'metadata': {},
        'course_metrics': [],
      });
      await tester.pumpAndSettle();
      expect(find.byType(CourseResultScreen), findsOneWidget);
      expect(find.textContaining('조건에 맞는 코스가 없어요'), findsOneWidget);
      expect(find.byTooltip('코스를 저장'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'out-of-area cancel unlocks submit and malformed response is recoverable',
    (tester) async {
      final source = FakeRecommendations();
      await mount(
        tester,
        source,
        location: FakeLocation(() async => const LocationFix(37.5, 127)),
      );
      await tap(tester, '다음');
      await tap(tester, '친구와');
      await tester.tap(find.text('장소 추천받기'));
      await tester.pump(const Duration(milliseconds: 350));
      await tap(tester, '취소');
      expect(source.requests, isEmpty);
      await tester.tap(find.text('장소 추천받기'));
      await tester.pump(const Duration(milliseconds: 350));
      await tester.tap(find.text('천안으로 추천'));
      await tester.pump(const Duration(milliseconds: 350));
      await tester.pump();
      expect(source.requests.single.lat, 36.8151);
      source.responses.single.complete({
        'places': [null],
      });
      await tester.pumpAndSettle();
      expect(find.text('추천 결과를 불러오지 못했어요. 다시 시도해주세요.'), findsOneWidget);
      expect(find.byType(SpotResultScreen), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets('empty AI suggestions preserve manually selected tags', (
    tester,
  ) async {
    final source = FakeRecommendations();
    await mount(tester, source);
    await tap(tester, '다음');
    await tap(tester, '친구와');
    await tester.enterText(find.byType(TextField), '알 수 없는 설명');
    await tester.ensureVisible(find.text('AI 태그 자동 선택'));
    await tester.tap(find.text('AI 태그 자동 선택'));
    await tester.pump();
    source.suggestions.single.complete([]);
    await tester.pumpAndSettle();
    expect(selected(tester, '친구와'), true);
    expect(find.textContaining('선택할 태그를 찾지 못했어요'), findsOneWidget);
  });

  for (final reason in [
    'network_unavailable',
    'network_timeout',
    'tags_unavailable',
    'invalid_response',
  ]) {
    testWidgets('AI $reason preserves tags and permits a successful retry', (
      tester,
    ) async {
      final source = FakeRecommendations();
      await mount(tester, source);
      await tap(tester, '다음');
      await tap(tester, '친구와');
      await tester.enterText(find.byType(TextField), '조용한 카페');
      await tester.ensureVisible(find.text('AI 태그 자동 선택'));
      await tester.tap(find.text('AI 태그 자동 선택'));
      await tester.pump();
      source.suggestions.single.completeError(TagSuggestionException(reason));
      await tester.pumpAndSettle();
      expect(find.text(TagSuggestionException(reason).message), findsOneWidget);
      expect(find.textContaining('선택할 태그를 찾지 못했어요'), findsNothing);
      expect(selected(tester, '친구와'), true);
      expect(
        tester.widget<TextField>(find.byType(TextField)).controller!.text,
        '조용한 카페',
      );
      await tester.tap(find.text('AI 태그 자동 선택'));
      await tester.pump();
      source.suggestions.last.complete(['연인과', '조용한']);
      await tester.pumpAndSettle();
      expect(selected(tester, '연인과'), true);
      expect(selected(tester, '친구와'), false);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('late AI failure after edit and dispose is ignored', (
    tester,
  ) async {
    final source = FakeRecommendations();
    await mount(tester, source);
    await tap(tester, '다음');
    await tester.enterText(find.byType(TextField), '첫 요청');
    await tester.tap(find.text('AI 태그 자동 선택'));
    await tester.pump();
    await tester.enterText(find.byType(TextField), '새 요청');
    source.suggestions.single.completeError(
      const TagSuggestionException('network_unavailable'),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('서버에 연결하지 못했어요'), findsNothing);
    await tester.tap(find.text('AI 태그 자동 선택'));
    await tester.pump();
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    source.suggestions.last.completeError(
      const TagSuggestionException('network_timeout'),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
  testWidgets(
    'manual region change and screen disposal cancel pending location',
    (tester) async {
      final location = CancellableFakeLocation();
      await tester.pumpWidget(
        MaterialApp(
          home: InputScreen(
            mode: 'spot',
            source: FakeRecommendations(),
            locationSource: location,
          ),
        ),
      );
      await tester.pump();
      await tester.tap(find.text('천안'));
      await tester.pumpAndSettle();
      expect(location.cancels, 1);
      expect(find.textContaining('위치 확인을 취소'), findsNothing);
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      await tester.pumpAndSettle();
      expect(location.cancels, 2);
      expect(tester.takeException(), isNull);
    },
  );
  for (final region in transitHubs.entries) {
    for (final hub in region.value) {
      testWidgets(
        '${region.key} ${hub.name} uses its public-map origin in both recommendation modes',
        (tester) async {
          for (final mode in ['spot', 'course']) {
            final source = FakeRecommendations();
            await tester.pumpWidget(const SizedBox());
            await tester.pumpAndSettle();
            await mount(tester, source, mode: mode);
            await tap(tester, region.key);
            await tap(tester, hub.name);
            expect(find.textContaining('대표 위치 기준'), findsOneWidget);
            await tap(tester, '다음');
            await tap(tester, '친구와');
            if (mode == 'course') await tap(tester, '다음');
            await tester.tap(find.text(mode == 'spot' ? '장소 추천받기' : '코스 추천받기'));
            await tester.pump();
            expect(source.requests.single.region, region.key);
            expect(source.requests.single.transport, '대중교통');
            expect(source.requests.single.lat, hub.lat);
            expect(source.requests.single.lng, hub.lng);
            source.responses.single.complete(
              mode == 'spot' ? {'places': []} : {'courses': []},
            );
            await tester.pumpAndSettle();
            expect(tester.takeException(), isNull);
          }
        },
      );
    }
  }
}
