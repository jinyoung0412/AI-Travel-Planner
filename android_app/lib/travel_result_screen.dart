import 'package:flutter/material.dart';

class TravelResultScreen extends StatelessWidget {
  final String region;
  final List<String> themes;
  final String duration;
  final Map<String, dynamic> aiData; // 서버에서 넘겨받은 AI 결과 데이터

  const TravelResultScreen({
    super.key,
    required this.region,
    required this.themes,
    required this.duration,
    required this.aiData,
  });

  @override
  Widget build(BuildContext context) {
    // 서버에서 받은 데이터 안전하게 추출
    String reason = aiData['reason'] ?? '이유를 불러올 수 없습니다.';
    List<dynamic> course = aiData['recommended_course'] ?? [];
    String time = aiData['total_time'] ?? '시간 정보 없음';

    return Scaffold(
      appBar: AppBar(
        title: const Text('AI 추천 코스 결과'),
        backgroundColor: Colors.blue.shade100,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '📍 선택하신 정보\n - 지역: $region\n - 기간: $duration\n - 테마: ${themes.join(", ")}',
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.black54),
            ),
            const Divider(height: 30, thickness: 2),

            const Text('💡 AI 추천 이유', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(reason, style: const TextStyle(fontSize: 16)),

            const SizedBox(height: 24),

            const Text('🗺️ 추천 여행 코스', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            // 배열로 온 코스를 보기 좋게 나열
            ...course.map((place) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 4.0),
              child: Row(
                children: [
                  const Icon(Icons.check_circle, color: Colors.blue, size: 20),
                  const SizedBox(width: 8),
                  Text(place.toString(), style: const TextStyle(fontSize: 16)),
                ],
              ),
            )),

            const SizedBox(height: 24),

            const Text('⏱️ 예상 소요 시간', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(time, style: const TextStyle(fontSize: 16)),
          ],
        ),
      ),
    );
  }
}