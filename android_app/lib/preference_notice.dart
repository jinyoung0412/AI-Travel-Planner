import 'package:flutter/material.dart';

/// Shows independent recommendation limits without claiming unsupported matches.
class PreferenceNotice extends StatelessWidget {
  final Map<String, dynamic> metadata;
  const PreferenceNotice({super.key, required this.metadata});

  static String? _spatialLimitation(Map<String, dynamic> metadata) {
    final value = metadata['spatial_relation_limitation'];
    return value is String && value.trim().isNotEmpty ? value.trim() : null;
  }

  static bool hasNotice(Map<String, dynamic> metadata) =>
      metadata['preference_evidence'] == 'unavailable' ||
      _spatialLimitation(metadata) != null;

  @override
  Widget build(BuildContext context) {
    if (!hasNotice(metadata)) return const SizedBox.shrink();
    final preferenceMessage = metadata['preference_limitation'];
    final spatialMessage = _spatialLimitation(metadata);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (metadata['preference_evidence'] == 'unavailable')
          _notice(
            preferenceMessage is String && preferenceMessage.trim().isNotEmpty
                ? preferenceMessage
                : '검증된 블로그 태그가 없어 취향 일치 근거가 없습니다. 카테고리·인기도·거리로 추천합니다.',
          ),
        if (spatialMessage != null)
          _notice(spatialMessage, title: '주변 거리 조건 안내'),
      ],
    );
  }

  Widget _notice(String message, {String? title}) => Container(
    margin: const EdgeInsets.only(bottom: 12),
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: const Color(0xFFFFF3E0),
      borderRadius: BorderRadius.circular(10),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (title != null) ...[
          Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
        ],
        Text(
          message,
          style: const TextStyle(fontSize: 12, color: Color(0xFF795548)),
        ),
      ],
    ),
  );
}
