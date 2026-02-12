import 'package:flutter/material.dart';

class TravelResultScreen extends StatelessWidget {
  // 이전 화면에서 넘겨받을 데이터들
  final String region;
  final List<String> themes;
  final String duration;

  const TravelResultScreen({
    super.key,
    required this.region,
    required this.themes,
    required this.duration,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('추천 여행 코스'),
      ),
      body: Column(
        children: [
          // 1. 상단 요약 정보 (어떤 여행인지?)
          Container(
            padding: const EdgeInsets.all(16.0),
            color: Colors.blue.shade50,
            child: Row(
              children: [
                const Icon(Icons.location_on, color: Colors.blue),
                const SizedBox(width: 8),
                Text(
                  '$region 여행 ($duration)',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
              ],
            ),
          ),

          // 2. 테마 태그 보여주기
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
            child: Wrap(
              spacing: 8.0,
              children: themes.map((theme) => Chip(
                label: Text(theme),
                backgroundColor: Colors.blue.shade100,
              )).toList(),
            ),
          ),

          const Divider(height: 1),

          // 3. 여행 코스 리스트 (지금은 가짜 데이터)
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(16.0),
              children: [
                _buildCourseItem('10:00', '독립기념관', '역사/문화', '천안시 동남구 목천읍'),
                _buildPathLine(), // 점선 (이동 경로 느낌)
                _buildCourseItem('12:30', '병천 순대거리', '맛집', '천안시 동남구 병천면'),
                _buildPathLine(),
                _buildCourseItem('14:00', '아라리오 갤러리', '문화/예술', '천안시 동남구 신부동'),
                _buildPathLine(),
                _buildCourseItem('16:00', '단대호수 카페거리', '카페/힐링', '천안시 동남구 안서동'),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // 코스 아이템을 예쁘게 보여주는 위젯 함수
  Widget _buildCourseItem(String time, String place, String category, String address) {
    return Card(
      elevation: 3, // 그림자 효과
      margin: EdgeInsets.zero,
      child: ListTile(
        leading: Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: Colors.blue.shade50,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Text(time, style: const TextStyle(fontWeight: FontWeight.bold)),
        ),
        title: Text(place, style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 4),
            Text(category, style: TextStyle(color: Colors.blue.shade700, fontSize: 12)),
            Text(address, style: const TextStyle(fontSize: 12)),
          ],
        ),
        trailing: const Icon(Icons.arrow_forward_ios, size: 16, color: Colors.grey),
      ),
    );
  }

  // 점선 만들기 (이동하는 느낌)
  Widget _buildPathLine() {
    return Container(
      margin: const EdgeInsets.only(left: 36), // 시간 박스 가운데쯤 오게
      height: 20,
      width: 2,
      color: Colors.grey.shade300,
    );
  }
}