import 'package:ai_travel_app/course_shortage.dart';
import 'package:ai_travel_app/recommendation_source.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  RecommendationRequest request({
    List<String> slots = const ['음식', '쇼핑', '카페'],
    String text = '',
  }) => RecommendationRequest(
    mode: 'course',
    userText: text,
    transport: '대중교통',
    region: '아산',
    lat: 36.76979,
    lng: 126.95182,
    tags: const ['친구와'],
    count: 3,
    slotTypes: slots,
    seed: 1,
  );
  test(
    'exact shopping shortage identifies its slot and keeps the original controls',
    () {
      final r = request();
      final notice = CourseShortage.fromResponse({
        'error': '부족',
        'metadata': {
          'reason': 'missing_slot_candidates',
          'slot_candidate_counts': [354, 0, 118],
          'slot_types': r.slotTypes,
          'radius_km': 4.5,
        },
      }, r)!;
      expect(notice.title, '2번째 쇼핑 장소를 찾지 못했어요');
      expect(notice.message, '활동이나 출발점·이동수단을 바꿔주세요.');
      expect(r.slotTypes, ['음식', '쇼핑', '카페']);
      expect(r.transport, '대중교통');
    },
  );
  test('natural stages and multiple missing slots are preserved', () {
    final notice = CourseShortage.fromResponse({
      'reason': 'insufficient_candidates',
      'metadata': {
        'reason': 'missing_slot_candidates',
        'candidate_counts': [0, 0],
        'travel_request': {
          'stages': [
            {'activity': '산책'},
            {'activity': '야장'},
          ],
        },
      },
    }, request(slots: const [], text: '산책 후 야장'))!;
    expect(notice.title, '1번째 산책, 2번째 야장 장소를 찾지 못했어요');
  });
  test(
    'collective distinctness shortage is different from an empty activity',
    () {
      final notice = CourseShortage.fromResponse({
        'metadata': {
          'reason': 'insufficient_distinct_places',
          'slot_candidate_counts': [1, 1, 1],
        },
      }, request())!;
      expect(notice.title, '코스를 만들 장소가 부족해요');
      expect(
        CourseShortage.fromResponse({'reason': 'network_timeout'}, request()),
        isNull,
      );
    },
  );
  test(
    'culture shortage keeps the next action brief without exposing pool counts',
    () {
      final notice = CourseShortage.fromResponse(
        {
          'metadata': {
            'reason': 'insufficient_distinct_places',
            'slot_candidate_counts': [2, 2, 2],
            'slot_types': ['문화·역사', '문화·역사', '문화·역사'],
            'radius_km': 4.5,
          },
        },
        request(slots: ['문화·역사', '문화·역사', '문화·역사']),
        labels: {'문화·역사': '전시·문화관람'},
      )!;
      expect(notice.message, '활동이나 출발점·이동수단을 바꿔주세요.');
      expect(notice.message, isNot(contains('6곳')));
    },
  );
  test(
    'natural shortage does not expose invalid counts or internal diagnostics',
    () {
      final notice = CourseShortage.fromResponse({
        'metadata': {
          'reason': 'insufficient_distinct_places',
          'candidate_counts': [2, 'NaN', -1],
          'travel_request': {
            'stages': [
              {'activity': '전시'},
              {'activity': '역사관'},
              {'activity': '미술관'},
            ],
          },
        },
      }, request(slots: [], text: '전시 세 곳'))!;
      expect(notice.title, '코스를 만들 장소가 부족해요');
      expect(notice.message, '활동이나 출발점·이동수단을 바꿔주세요.');
      expect(notice.message, isNot(contains('NaN')));
    },
  );
}
