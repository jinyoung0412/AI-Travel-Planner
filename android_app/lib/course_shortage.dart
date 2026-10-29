import 'recommendation_source.dart';
import 'travel_data.dart';

/// Constraint failures return users to the controls they explicitly choose.
class CourseShortage {
  final String title;
  final String message;
  const CourseShortage(this.title, this.message);

  static CourseShortage? fromResponse(
    Map<String, dynamic>? response,
    RecommendationRequest request, {
    Map<String, String> labels = const {},
  }) {
    if (response == null || request.mode != 'course') return null;
    final metadata = response['metadata'] is Map
        ? jsonObject(response['metadata'])
        : <String, dynamic>{};
    final reason = metadata['reason'] ?? response['reason'];
    if (!const {
      'missing_slot_candidates',
      'insufficient_distinct_places',
      'insufficient_unique_courses',
    }.contains(reason)) {
      return null;
    }
    final rawCounts =
        metadata['slot_candidate_counts'] ?? metadata['candidate_counts'];
    final counts = rawCounts is List ? rawCounts : const [];
    final serverSlots = metadata['slot_types'];
    final reviewed = metadata['travel_request'];
    final stages = reviewed is Map ? reviewed['stages'] : null;
    final names = serverSlots is List && serverSlots.isNotEmpty
        ? serverSlots.map((s) => '$s').toList()
        : request.slotTypes.isNotEmpty
        ? request.slotTypes
        : stages is List
        ? stages
              .map((s) => s is Map ? '${s['activity'] ?? '활동'}' : '활동')
              .toList()
        : <String>[];
    if (reason == 'missing_slot_candidates') {
      final missing = <String>[
        for (var i = 0; i < counts.length; i++)
          if (counts[i] is num && counts[i] == 0)
            '${i + 1}번째 ${i < names.length ? labels[names[i]] ?? names[i] : '활동'}',
      ];
      return CourseShortage(
        missing.isEmpty
            ? '조건에 맞는 장소를 찾지 못했어요'
            : '${missing.join(', ')} 장소를 찾지 못했어요',
        '활동이나 출발점·이동수단을 바꿔주세요.',
      );
    }
    return CourseShortage(
      reason == 'insufficient_distinct_places'
          ? '코스를 만들 장소가 부족해요'
          : '요청한 수만큼 코스를 찾지 못했어요',
      '활동이나 출발점·이동수단을 바꿔주세요.',
    );
  }
}
