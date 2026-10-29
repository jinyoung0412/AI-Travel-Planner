import 'package:ai_travel_app/recommendation_source.dart';
import 'package:ai_travel_app/transit_hubs.dart';
import 'package:flutter_test/flutter_test.dart';

// Python matrix extracts and compares these wire choices to actual UI/API values.
const activities = ['음식', '카페', '자연·산책', '문화·역사', '체험', '실내 오락'];

Iterable<List<String>> sequences(int length) sync* {
  if (length == 0) {
    yield <String>[];
    return;
  }
  for (final first in activities) {
    for (final rest in sequences(length - 1)) {
      yield [first, ...rest];
    }
  }
}

void main() {
  test('all 9288 direct course sequences preserve order through review', () {
    var checked = 0;
    for (final length in [3, 4, 5]) {
      for (final slots in sequences(length)) {
        final original = RecommendationRequest(
          mode: 'course', userText: '100일 기념 데이트', transport: '대중교통',
          region: '천안', lat: 36.8013, lng: 127.13587,
          tags: const ['연인과', '로맨틱한', '기념일'], count: 3,
          slotTypes: slots, seed: 11, recentPlaceIds: const ['place:prior'],
        );
        final reviewed = original.reviewed(token: 'signed-review');
        expect(reviewed.interpretationBody['slot_types'], slots);
        expect(reviewed.interpretationBody['spot_count'], length);
        expect(reviewed.interpretationBody['plan_mode'], 'manual');
        expect(reviewed.selectionFields['recent_place_ids'], ['place:prior']);
        expect(reviewed.intentFields['seed'], 11);
        checked++;
      }
    }
    expect(checked, 9288);
  });

  test('every named hub and count keeps region and coordinates through activity clarification', () {
    var checked = 0;
    for (final entry in transitHubs.entries) {
      for (final hub in entry.value) {
        for (final count in [3, 5, 7, 10]) {
          for (final activity in activities) {
            final original = RecommendationRequest(
              mode: 'spot', userText: '여자친구랑 100일기념 데이트',
              transport: '대중교통', region: entry.key, lat: hub.lat, lng: hub.lng,
              tags: const ['연인과', '로맨틱한', '기념일'], count: count,
              slotTypes: const [], naturalPlan: true, seed: 29,
              recentPlaceIds: const ['place:prior'],
            );
            final ready = original
                .clarified(activity: activity, token: 'activity-review')
                .reviewed(token: 'intent-review');
            final body = ready.interpretationBody;
            expect(body['region'], entry.key);
            expect(body['transport'], '대중교통');
            expect(body['user_lat'], hub.lat);
            expect(body['user_lng'], hub.lng);
            expect(body['count'], count);
            expect(body['activity_choice'], activity);
            expect(body['persona_tags'], original.tags);
            expect(body['recent_place_ids'], ['place:prior']);
            expect(body['seed'], original.seed);
            checked++;
          }
        }
      }
    }
    expect(checked, transitHubs.values.expand((hubs) => hubs).length * 4 * 6);
  });
}
