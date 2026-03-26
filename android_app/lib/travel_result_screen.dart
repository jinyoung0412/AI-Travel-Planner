import 'package:flutter/material.dart';

class TravelResultScreen extends StatelessWidget {
  final String region;
  final List<String> themes;
  final String duration;
  final Map<String, dynamic> aiData;

  const TravelResultScreen({
    super.key,
    required this.region,
    required this.themes,
    required this.duration,
    required this.aiData,
  });

  @override
  Widget build(BuildContext context) {
    String reason = aiData['reason'] ?? '이유를 불러올 수 없습니다.';
    List<dynamic> course = aiData['recommended_course'] ?? [];
    String time = aiData['total_time'] ?? '시간 정보 없음';

    return Scaffold(
      backgroundColor: Colors.grey.shade100,
      appBar: AppBar(
        title: const Text('AI 맞춤 여행 코스', style: TextStyle(fontWeight: FontWeight.bold)),
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        elevation: 0,
        centerTitle: true,
      ),
      body: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              height: 200,
              width: double.infinity,
              color: Colors.blue.shade50,
              child: const Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.map_outlined, size: 50, color: Colors.blue),
                  SizedBox(height: 8),
                  Text('지도 API 연동 대기중', style: TextStyle(color: Colors.blue, fontWeight: FontWeight.bold)),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    spacing: 8.0,
                    children: [
                      Chip(
                        label: Text(region),
                        backgroundColor: Colors.white,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                      Chip(
                        label: Text(duration),
                        backgroundColor: Colors.white,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                      ...themes.map((theme) => Chip(
                        label: Text(theme, style: const TextStyle(color: Colors.white)),
                        backgroundColor: Colors.blue,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      )),
                    ],
                  ),
                  const SizedBox(height: 20),
                  Card(
                    color: Colors.white,
                    elevation: 2,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    child: Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Row(
                            children: [
                              Icon(Icons.auto_awesome, color: Colors.amber),
                              SizedBox(width: 8),
                              Text('AI의 추천 코멘트', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                            ],
                          ),
                          const Divider(),
                          Text(reason, style: const TextStyle(fontSize: 15, height: 1.5, color: Colors.black87)),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),
                  const Text('이동 동선', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 16),
                  Card(
                    color: Colors.white,
                    elevation: 2,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    child: Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: Column(
                        children: List.generate(course.length, (index) {
                          bool isLast = index == course.length - 1;
                          return _buildTimelineItem(course[index] as Map<String, dynamic>, isLast, index + 1);
                        }),
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),
                  Card(
                    color: Colors.white,
                    elevation: 2,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    child: ListTile(
                      leading: const Icon(Icons.timer, color: Colors.blue, size: 30),
                      title: const Text('총 예상 소요 시간', style: TextStyle(fontWeight: FontWeight.bold)),
                      trailing: Text(time, style: const TextStyle(fontSize: 16, color: Colors.blue, fontWeight: FontWeight.bold)),
                    ),
                  ),
                  const SizedBox(height: 30),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTimelineItem(Map<String, dynamic> place, bool isLast, int stepNumber) {
    String name = place['name'] ?? '이름 없음';
    String address = place['address'] ?? '주소 없음';
    String category = place['category'] ?? '';

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Column(
            children: [
              Container(
                width: 24,
                height: 24,
                decoration: const BoxDecoration(
                  color: Colors.blue,
                  shape: BoxShape.circle,
                ),
                child: Center(
                  child: Text(
                    stepNumber.toString(),
                    style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold),
                  ),
                ),
              ),
              if (!isLast)
                Expanded(
                  child: Container(
                    width: 2,
                    color: Colors.blue.shade200,
                  ),
                ),
            ],
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(bottom: 24.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          name,
                          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, height: 1.2),
                        ),
                      ),
                      if (category.isNotEmpty)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: Colors.grey.shade200,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            category,
                            style: const TextStyle(fontSize: 12, color: Colors.black54),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    address,
                    style: const TextStyle(fontSize: 13, color: Colors.grey),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}