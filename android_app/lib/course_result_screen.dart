import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class CourseResultScreen extends StatefulWidget {
  final List<List<dynamic>> courses;
  final int requestedCount;

  const CourseResultScreen({super.key, required this.courses, required this.requestedCount});

  @override
  State<CourseResultScreen> createState() => _CourseResultScreenState();
}

class _CourseResultScreenState extends State<CourseResultScreen> {
  final PageController _pageController = PageController();
  int _currentPage = 0;

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  Future<void> _openKakaoMap(BuildContext context, Map<String, dynamic> place) async {
    final lat  = place['lat'];
    final lng  = place['lng'];
    final name = Uri.encodeComponent(place['name'] ?? '');
    final appUri = Uri.parse('kakaomap://look?p=$lat,$lng');
    final webUri = Uri.parse('https://map.kakao.com/link/to/$name,$lat,$lng');

    if (await canLaunchUrl(appUri)) {
      await launchUrl(appUri);
    } else if (await canLaunchUrl(webUri)) {
      await launchUrl(webUri, mode: LaunchMode.externalApplication);
    } else {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('지도를 열 수 없습니다.')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8F3),
      appBar: AppBar(
        backgroundColor: const Color(0xFFFFF8F3),
        elevation: 0,
        foregroundColor: const Color(0xFF1A1A1A),
        title: const Text('추천 코스', style: TextStyle(fontWeight: FontWeight.bold)),
      ),
      body: Column(
        children: [
          // 페이지 인디케이터
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: List.generate(widget.courses.length, (i) {
                final active = i == _currentPage;
                return GestureDetector(
                  onTap: () => _pageController.animateToPage(
                    i,
                    duration: const Duration(milliseconds: 300),
                    curve: Curves.easeInOut,
                  ),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    width: active ? 28 : 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: active ? const Color(0xFF26C6DA) : Colors.grey.shade300,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                );
              }),
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text(
              '코스 ${_currentPage + 1} / ${widget.courses.length}',
              style: TextStyle(fontSize: 13, color: Colors.grey.shade500),
            ),
          ),
          if (widget.courses.length < widget.requestedCount)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: const Color(0xFFFFF3E0),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0xFFFFCC80)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.info_outline, size: 16, color: Color(0xFFFF8F00)),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '선택하신 조건에 맞는 코스가 부족해 ${widget.courses.length}개만 추천되었어요.',
                        style: const TextStyle(fontSize: 13, color: Color(0xFF795548)),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          // 코스 PageView
          Expanded(
            child: PageView.builder(
              controller: _pageController,
              itemCount: widget.courses.length,
              onPageChanged: (i) => setState(() => _currentPage = i),
              itemBuilder: (context, courseIndex) {
                final course = widget.courses[courseIndex]
                    .map((e) => Map<String, dynamic>.from(e as Map))
                    .toList();
                return _CourseCard(
                  course: course,
                  courseIndex: courseIndex,
                  onMapTap: (place) => _openKakaoMap(context, place),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _CourseCard extends StatelessWidget {
  final List<Map<String, dynamic>> course;
  final int courseIndex;
  final void Function(Map<String, dynamic>) onMapTap;

  const _CourseCard({
    required this.course,
    required this.courseIndex,
    required this.onMapTap,
  });

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
      child: Column(
        children: List.generate(course.length, (index) {
          final isLast = index == course.length - 1;
          return _TimelineStop(
            place: course[index],
            step: index + 1,
            isLast: isLast,
            onMapTap: () => onMapTap(course[index]),
          );
        }),
      ),
    );
  }
}

class _TimelineStop extends StatelessWidget {
  final Map<String, dynamic> place;
  final int step;
  final bool isLast;
  final VoidCallback onMapTap;

  const _TimelineStop({
    required this.place,
    required this.step,
    required this.isLast,
    required this.onMapTap,
  });

  @override
  Widget build(BuildContext context) {
    final name     = place['name']     ?? '';
    final address  = place['address']  ?? '';
    final category = place['category'] ?? '';

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 타임라인 선 + 번호
          Column(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: const BoxDecoration(
                  color: Color(0xFF26C6DA),
                  shape: BoxShape.circle,
                ),
                child: Center(
                  child: Text(
                    '$step',
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                  ),
                ),
              ),
              if (!isLast)
                Expanded(
                  child: Container(
                    width: 2,
                    margin: const EdgeInsets.symmetric(vertical: 4),
                    color: const Color(0xFF26C6DA),
                  ),
                ),
            ],
          ),
          const SizedBox(width: 14),
          // 장소 카드
          Expanded(
            child: Container(
              margin: EdgeInsets.only(bottom: isLast ? 0 : 16),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(14),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.05),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  if (category.isNotEmpty)
                    Container(
                      margin: const EdgeInsets.only(bottom: 4),
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        color: const Color(0xFFE8F9FB),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(category, style: const TextStyle(fontSize: 12, color: Color(0xFF26C6DA))),
                    ),
                  Text(address, style: TextStyle(fontSize: 13, color: Colors.grey.shade500)),
                  const SizedBox(height: 10),
                  GestureDetector(
                    onTap: onMapTap,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.map_outlined, size: 15, color: Colors.grey.shade600),
                        const SizedBox(width: 4),
                        Text('지도에서 보기', style: TextStyle(fontSize: 13, color: Colors.grey.shade600)),
                      ],
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
