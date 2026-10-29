import 'package:ai_travel_app/recommendation_source.dart';
import 'package:flutter_test/flutter_test.dart';

RecommendationRequest request({int? seed}) => RecommendationRequest(
  mode: 'spot',
  userText: '산책 후 카페',
  transport: '대중교통',
  region: '아산',
  lat: 36.76979,
  lng: 126.95182,
  tags: const ['친구와'],
  count: 3,
  slotTypes: const [],
  seed: seed,
);

void main() {
  test('new recommendations get new bounded seeds', () {
    final first = request();
    final second = request();
    expect(first.seed, inInclusiveRange(0, 2147483647));
    expect(second.seed, isNot(first.seed));
    expect(first.interpretationBody['seed'], first.seed);
    expect(first.selectionFields['randomize'], true);
  });

  test('confirmation, course switch and unknown alternative keep one seed', () {
    final original = request(seed: 12345);
    final reviewed = original.reviewed(
      token: 't',
      targetMode: 'course',
      targetCount: 1,
    );
    final accepted = reviewed.reviewed(token: 't', unverified: true);
    expect(reviewed.seed, original.seed);
    expect(accepted.seed, original.seed);
    expect(reviewed.selectionFields, original.selectionFields);
    expect(accepted.intentFields['seed'], 12345);
    expect(accepted.intentFields['randomize'], true);
    expect(accepted.acceptUnverified, true);
  });
  test('history is bounded, unique, immutable and survives request stages', () {
    final ids = [
      ' a ',
      'a',
      '',
      ' ',
      'x' * 201,
      ...List.generate(120, (i) => 'id:$i'),
    ];
    final original = RecommendationRequest(
      mode: 'course',
      userText: '기념일 데이트',
      transport: '차',
      region: '천안',
      lat: 36.8,
      lng: 127.1,
      tags: const ['연인과'],
      count: 3,
      slotTypes: const ['음식', '자연·산책', '카페'],
      recentPlaceIds: ids,
    );
    ids.clear();
    expect(original.recentPlaceIds.length, 100);
    expect(original.recentPlaceIds.first, 'a');
    expect(original.recentPlaceIds.toSet().length, 100);
    expect(
      original.interpretationBody['recent_place_ids'],
      original.recentPlaceIds,
    );
    final clarified = original.clarified(activity: '체험', token: 'choice');
    final reviewed = clarified.reviewed(token: 'intent');
    expect(reviewed.intentFields['recent_place_ids'], original.recentPlaceIds);
    expect(reviewed.seed, original.seed);
    expect(reviewed.slotTypes, original.slotTypes);
    expect(() => original.recentPlaceIds.add('bad'), throwsUnsupportedError);
    expect(request().selectionFields.containsKey('recent_place_ids'), false);
  });
}
