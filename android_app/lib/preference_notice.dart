import 'package:flutter/material.dart';

/// Explains absent recommendation evidence without claiming a taste match.
class PreferenceNotice extends StatelessWidget {
  final Map<String, dynamic> metadata;
  const PreferenceNotice({super.key, required this.metadata});

  @override
  Widget build(BuildContext context) {
    if (metadata['preference_evidence'] != 'unavailable') {
      return const SizedBox.shrink();
    }
    final message = metadata['preference_limitation'];
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF3E0),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        message is String && message.trim().isNotEmpty
            ? message
            : '검증된 블로그 태그가 없어 취향 일치 근거가 없습니다. 카테고리·인기도·거리로 추천합니다.',
        style: const TextStyle(fontSize: 12, color: Color(0xFF795548)),
      ),
    );
  }
}
