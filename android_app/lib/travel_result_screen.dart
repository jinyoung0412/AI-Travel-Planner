import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

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

  Future<void> _openKakaoMapRoute(BuildContext context, Map<String, dynamic>? start, Map<String, dynamic> end) async {
    final double eLat = end['lat'];
    final double eLng = end['lng'];

    String appUrlString = 'kakaomap://route?ep=$eLat,$eLng';

    if (start != null) {
      final double sLat = start['lat'];
      final double sLng = start['lng'];
      appUrlString += '&sp=$sLat,$sLng';
    }

    final Uri appUri = Uri.parse(appUrlString);

    if (await canLaunchUrl(appUri)) {
      await launchUrl(appUri);
    } else {
      final String eName = (end['name'] ?? '도착지').toString().replaceAll(',', ' ');
      final String webUrlString = 'https://map.kakao.com/link/to/$eName,$eLat,$eLng';
      final Uri webUri = Uri.parse(Uri.encodeFull(webUrlString));

      if (await canLaunchUrl(webUri)) {
        await launchUrl(webUri, mode: LaunchMode.externalApplication);
      } else {
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('지도를 열 수 없습니다.')),
          );
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    String reason = aiData['reason'] ?? '이유를 불러올 수 없습니다.';
    List<dynamic> course = aiData['recommended_course'] ?? [];
    String time = aiData['total_time'] ?? '시간 정보 없음';
    Map<String, dynamic>? startHub = aiData['start_hub'];

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

                          Map<String, dynamic>? prevPlace;
                          if (index == 0) {
                            prevPlace = startHub;
                          } else {
                            prevPlace = course[index - 1];
                          }

                          return _buildTimelineItem(
                              context,
                              course[index] as Map<String, dynamic>,
                              isLast,
                              index + 1,
                              prevPlace
                          );
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

  Widget _buildTimelineItem(BuildContext context, Map<String, dynamic> place, bool isLast, int stepNumber, Map<String, dynamic>? prevPlace) {
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
                  const SizedBox(height: 8),

                  Align(
                    alignment: Alignment.centerLeft,
                    child: ElevatedButton.icon(
                      onPressed: () => _openKakaoMapRoute(context, prevPlace, place),
                      icon: const Icon(Icons.directions, size: 16),
                      label: Text(
                          stepNumber == 1 && prevPlace == null
                              ? '내 위치에서 출발'
                              : (stepNumber == 1 ? '역/터미널에서 출발' : '이전 장소에서 출발')
                      ),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.blue.shade50,
                        foregroundColor: Colors.blue.shade700,
                        elevation: 0,
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      ),
                    ),
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