import 'package:ai_travel_app/input_screen.dart';
import 'package:ai_travel_app/location_service.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _Location implements LocationSource {
  @override
  Future<LocationFix> locate() async => const LocationFix(36.8, 127.1);
}

class _Source implements IntentRecommendationSource {
  final interpretations = <RecommendationRequest>[];
  final recommendations = <RecommendationRequest>[];
  @override
  Future<List<String>> suggestTags(String text) async => [];
  @override
  Future<Map<String, dynamic>?> interpret(RecommendationRequest r) async {
    interpretations.add(r);
    return {
      'data': {
        'intent_token': 'token',
        'target_mode': r.mode,
        'target_count': r.count,
        'travel_request': {'ambiguities': [], 'unsupported': []},
      },
    };
  }

  @override
  Future<Map<String, dynamic>?> recommend(RecommendationRequest r) async {
    recommendations.add(r);
    return r.mode == 'spot' ? {'places': []} : {'courses': []};
  }
}

Future<void> tap(WidgetTester t, String text) async {
  final label = find.text(text).last;
  final chips = find.ancestor(of: label, matching: find.byType(ChoiceChip));
  final target = chips.evaluate().isEmpty ? label : chips;
  await t.ensureVisible(target);
  await t.pump();
  await t.tap(target);
  await t.pumpAndSettle();
}

Future<void> _mount(
  WidgetTester t,
  _Source source, {
  String mode = 'spot',
  bool reduceMotion = false,
}) async {
  await t.pumpWidget(
    MaterialApp(
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(
          disableAnimations: reduceMotion,
          textScaler: TextScaler.linear(reduceMotion ? 2.0 : 1),
        ),
        child: child!,
      ),
      home: InputScreen(
        mode: mode,
        source: source,
        locationSource: _Location(),
      ),
    ),
  );
  await t.pumpAndSettle();
  await tap(t, '다음');
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  testWidgets(
    'sentence comes first, tag questions show one group and retain selections',
    (t) async {
      final source = _Source();
      await _mount(t, source);
      expect(find.byType(TextField), findsOneWidget);
      expect(find.text('친구와'), findsNothing);
      expect(find.textContaining('문장은 추천에 그대로'), findsNothing);
      await t.enterText(find.byType(TextField), '친구와 놀 곳');
      await tap(t, '직접 태그 선택하기');
      expect(find.byType(TextField), findsNothing);
      expect(find.text('누구와 함께하나요?'), findsOneWidget);
      expect(find.text('누구와'), findsNothing);
      expect(find.text('문장 없이 추천받을 때 선택'), findsNothing);
      final questionTitle = t.widget<Text>(find.text('누구와 함께하나요?'));
      expect(questionTitle.style!.fontSize, 24);
      expect(questionTitle.style!.fontWeight, FontWeight.w600);
      expect(find.text('활동적인'), findsNothing);
      expect(find.text('선택 완료'), findsOneWidget);
      expect(find.text('다음 질문'), findsNothing);
      await tap(t, '친구와');
      await tap(t, '선택 완료');
      expect(find.text('어떤 분위기를 원하나요?'), findsOneWidget);
      expect(find.text('기념일'), findsNothing);
      await tap(t, '활동적인');
      await tap(t, '선택 완료');
      expect(find.text('특별한 날인가요?'), findsOneWidget);
      await tap(t, '선택 완료');
      expect(find.text('실내와 야외 중 어디가 좋나요?'), findsOneWidget);
      await tap(t, '실내 위주');
      await tap(t, '선택 완료');
      expect(find.text('어떤 활동을 원하나요?'), findsOneWidget);
      await tap(t, '체험·만들기');
      await tap(t, '선택 완료');
      expect(
        t.widget<TextField>(find.byType(TextField)).controller!.text,
        '친구와 놀 곳',
      );
      for (final tag in ['친구와', '활동적인', '실내 위주', '체험·만들기']) {
        expect(find.text(tag), findsOneWidget);
      }
      await tap(t, '장소 추천받기');
      expect(source.recommendations.single.tags, [
        '친구와',
        '활동적인',
        '실내 위주',
        '체험 공방',
      ]);
      expect(t.takeException(), isNull);
    },
  );
  testWidgets(
    'completion advances each question and back preserves selected tags',
    (t) async {
      await _mount(t, _Source());
      await tap(t, '직접 태그 선택하기');
      await tap(t, '혼자');
      await tap(t, '선택 완료');
      expect(find.text('어떤 분위기를 원하나요?'), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
      await tap(t, '활동적인');
      await tap(t, '이전');
      expect(find.text('누구와 함께하나요?'), findsOneWidget);
      final solo = find.ancestor(
        of: find.text('혼자'),
        matching: find.byType(ChoiceChip),
      );
      expect(t.widget<ChoiceChip>(solo).selected, true);
      await tap(t, '선택 완료');
      final mood = find.ancestor(
        of: find.text('활동적인'),
        matching: find.byType(ChoiceChip),
      );
      expect(t.widget<ChoiceChip>(mood).selected, true);
      for (final title in [
        '어떤 분위기를 원하나요?',
        '특별한 날인가요?',
        '실내와 야외 중 어디가 좋나요?',
        '어떤 활동을 원하나요?',
      ]) {
        expect(find.text(title), findsOneWidget);
        expect(find.text('선택 완료'), findsOneWidget);
        await tap(t, '선택 완료');
      }
      expect(find.byType(TextField), findsOneWidget);
      expect(find.text('혼자'), findsOneWidget);
      expect(find.text('활동적인'), findsOneWidget);
      await tap(t, '혼자');
      await tap(t, '연인과');
      for (var i = 0; i < 5; i++) {
        await tap(t, '선택 완료');
      }
      expect(find.text('혼자'), findsNothing);
      expect(find.text('연인과'), findsOneWidget);
      expect(find.text('활동적인'), findsOneWidget);
      expect(t.takeException(), isNull);
    },
  );
  testWidgets(
    'course confirms shown visit order without switch or repeated activity question',
    (t) async {
      final source = _Source();
      await _mount(t, source, mode: 'course');
      await t.enterText(find.byType(TextField), '여자친구와 100일 기념 데이트');
      await tap(t, '다음');
      expect(find.text('방문 순서'), findsOneWidget);
      expect(find.byType(SwitchListTile), findsNothing);
      await tap(t, '산책·자연');
      await tap(t, '체험·만들기');
      await tap(t, '코스 추천받기');
      final request = source.interpretations.single;
      expect(request.slotTypes, ['음식', '체험', '카페']);
      expect(request.naturalPlan, false);
      expect(request.interpretationBody['plan_mode'], 'manual');
      expect(source.recommendations.single.slotTypes, request.slotTypes);
      expect(find.text('어떤 활동을 원하세요?'), findsNothing);
      expect(t.takeException(), isNull);
    },
  );
  testWidgets(
    'small screen, large text and reduced motion preserve question navigation',
    (t) async {
      t.view.physicalSize = const Size(320, 568);
      t.view.devicePixelRatio = 1;
      addTearDown(t.view.resetPhysicalSize);
      addTearDown(t.view.resetDevicePixelRatio);
      await _mount(t, _Source(), reduceMotion: true);
      final switcher = t.widget<AnimatedSwitcher>(
        find.byType(AnimatedSwitcher).first,
      );
      expect(switcher.duration, Duration.zero);
      await tap(t, '직접 태그 선택하기');
      await tap(t, '소개팅/첫만남');
      final chip = t.widget<ChoiceChip>(
        find.ancestor(
          of: find.text('소개팅/첫만남'),
          matching: find.byType(ChoiceChip),
        ),
      );
      expect(chip.selected, true);
      expect(chip.chipAnimationStyle!.selectAnimation!.duration, Duration.zero);
      for (var i = 0; i < 5; i++) {
        await tap(t, '선택 완료');
        expect(t.takeException(), isNull);
      }
      expect(find.byType(TextField), findsOneWidget);
      expect(find.text('소개팅/첫만남'), findsOneWidget);
      expect(t.takeException(), isNull);
    },
  );
  testWidgets('beer visit is selectable without changing normal meal defaults', (t) async {
    final source = _Source();
    await _mount(t, source, mode: 'course');
    await t.enterText(find.byType(TextField), '기념일에 야장 가고 싶어');
    await tap(t, '다음');
    await tap(t, '식사');
    await tap(t, '맥주·호프');
    await tap(t, '코스 추천받기');
    expect(source.interpretations.single.slotTypes, ['맥주·호프', '자연·산책', '카페']);
    expect(source.recommendations.single.slotTypes, ['맥주·호프', '자연·산책', '카페']);
    expect(t.takeException(), isNull);
  });
  testWidgets('course visit cards wrap without clipping at 200 percent text', (
    t,
  ) async {
    t.view.physicalSize = const Size(320, 568);
    t.view.devicePixelRatio = 1;
    addTearDown(t.view.resetPhysicalSize);
    addTearDown(t.view.resetDevicePixelRatio);
    final source = _Source();
    await _mount(t, source, mode: 'course', reduceMotion: true);
    expect(t.takeException(), isNull, reason: 'sentence');
    await t.enterText(find.byType(TextField), '100일 기념 데이트');
    await tap(t, '다음');
    expect(t.takeException(), isNull, reason: 'visit order');
    await tap(t, '식사');
    expect(t.takeException(), isNull, reason: 'slot picker');
    await tap(t, '전시·문화관람');
    expect(t.takeException(), isNull, reason: 'edited order');
    expect(t.widget<Text>(find.text('전시·문화관람')).maxLines, isNull);
    await tap(t, '코스 추천받기');
    expect(source.recommendations.single.slotTypes, ['문화·역사', '자연·산책', '카페']);
    expect(t.takeException(), isNull);
  });
}
