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
    // 서버 데이터 추출 (없을 경우 기본값)
    String reason = aiData['reason'] ?? '이유를 불러올 수 없습니다.';
    List<dynamic> course = aiData['recommended_course'] ?? [];
    String time = aiData['total_time'] ?? '시간 정보 없음';

    return Scaffold(
      backgroundColor: Colors.grey.shade100, // 전체 배경색을 살짝 어둡게 주어 카드가 돋보이게 함
      appBar: AppBar(
        title: const Text('AI 맞춤 여행 코스', style: TextStyle(fontWeight: FontWeight.bold)),
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        elevation: 0, // 상단바 그림자 제거로 깔끔하게
        centerTitle: true,
      ),
      body: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 1. 가상의 지도 영역 (추후 카카오맵/구글맵 연동할 자리)
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
                  // 2. 사용자가 선택한 기본 정보 요약 칩
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

                  // 3. AI 추천 이유 카드
                  Card(
                    color: Colors.white,
                    elevation: 2,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    child: Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const Icon(Icons.auto_awesome, color: Colors.amber),
                              const SizedBox(width: 8),
                              const Text('AI의 추천 코멘트', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                            ],
                          ),
                          const Divider(),
                          Text(reason, style: const TextStyle(fontSize: 15, height: 1.5, color: Colors.black87)),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),

                  // 4. 추천 코스 타임라인 영역
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
                          return _buildTimelineItem(course[index].toString(), isLast, index + 1);
                        }),
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),

                  // 5. 총 예상 소요 시간 카드
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

  // 타임라인 UI를 그려주는 내부 함수
  Widget _buildTimelineItem(String placeName, bool isLast, int stepNumber) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 왼쪽: 점과 선 그려주는 영역
          Column(
            children: [
              Container(
                width: 24,
                height: 24,
                decoration: BoxDecoration(
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
                    color: Colors.blue.shade200, // 다음 장소로 이어지는 선
                  ),
                ),
            ],
          ),
          const SizedBox(width: 16),
          // 오른쪽: 장소 이름 텍스트 영역
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(bottom: 24.0), // 각 장소 간의 간격
              child: Text(
                placeName,
                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, height: 1.2),
              ),
            ),
          ),
        ],
      ),
    );
  }
}