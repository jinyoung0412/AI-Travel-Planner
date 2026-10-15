import 'package:flutter/material.dart';
import 'bookmark_button.dart';
import 'course_timeline.dart';
import 'local_storage_service.dart';
import 'travel_data.dart';
import 'preference_notice.dart';

class CourseResultScreen extends StatefulWidget {
  final List<List<dynamic>> courses;
  final int requestedCount;
  final String region;
  final Map<String, dynamic> metadata;
  final List<dynamic> courseMetrics;

  const CourseResultScreen({
    super.key,
    required this.courses,
    required this.requestedCount,
    this.region = '',
    this.metadata = const {},
    this.courseMetrics = const [],
  });

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

  List<Map<String, dynamic>> _spots(int index) => jsonObjects(
    widget.courses[index],
  ).map((place) => PlaceData.fromJson(place).toJson()).toList();
  Map<String, dynamic>? _metric(int index) =>
      index < widget.courseMetrics.length && widget.courseMetrics[index] is Map
      ? jsonObject(widget.courseMetrics[index])
      : null;

  @override
  Widget build(BuildContext context) {
    final page = _currentPage;
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8F3),
      appBar: AppBar(
        backgroundColor: const Color(0xFFFFF8F3),
        elevation: 0,
        foregroundColor: const Color(0xFF1A1A1A),
        title: const Text(
          '추천 코스',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        actions: [
          if (widget.courses.isNotEmpty)
            BookmarkButton(
              key: ValueKey(page),
              label: '코스를',
              color: const Color(0xFF26C6DA),
              read: () => LocalStorageService.isCourseSaved(_spots(page)),
              save: () => LocalStorageService.saveCourse(
                widget.region,
                _spots(page),
                metric: _metric(page),
                metadata: widget.metadata,
              ),
              remove: () =>
                  LocalStorageService.removeCourseBySpots(_spots(page)),
            ),
        ],
      ),
      body: widget.courses.isEmpty
          ? const Center(
              child: Text(
                '조건에 맞는 코스가 없어요. 조건을 바꿔 다시 시도해주세요.',
                textAlign: TextAlign.center,
              ),
            )
          : PageView.builder(
              controller: _pageController,
              itemCount: widget.courses.length,
              onPageChanged: (index) => setState(() => _currentPage = index),
              itemBuilder: (context, index) => SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
                child: Column(
                  children: [
                    Wrap(
                      alignment: WrapAlignment.center,
                      children: List.generate(
                        widget.courses.length,
                        (i) => IconButton(
                          tooltip: '코스 ${i + 1} 보기',
                          onPressed: () => _pageController.animateToPage(
                            i,
                            duration: const Duration(milliseconds: 300),
                            curve: Curves.easeInOut,
                          ),
                          icon: Icon(
                            Icons.circle,
                            size: i == index ? 14 : 8,
                            color: i == index
                                ? const Color(0xFF26C6DA)
                                : Colors.grey.shade300,
                          ),
                        ),
                      ),
                    ),
                    Text(
                      '코스 ${index + 1} / ${widget.courses.length}',
                      style: TextStyle(
                        fontSize: 13,
                        color: Colors.grey.shade500,
                      ),
                    ),
                    if (widget.courses.length < widget.requestedCount)
                      Container(
                        margin: const EdgeInsets.symmetric(vertical: 8),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 14,
                          vertical: 10,
                        ),
                        decoration: BoxDecoration(
                          color: const Color(0xFFFFF3E0),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: const Color(0xFFFFCC80)),
                        ),
                        child: Text(
                          '슬롯 조건을 유지하는 서로 다른 코스가 ${widget.courses.length}개 있어요.',
                          style: const TextStyle(
                            fontSize: 13,
                            color: Color(0xFF795548),
                          ),
                        ),
                      ),
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Text(
                        distanceNotice(_metric(index)),
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.grey.shade600,
                        ),
                      ),
                    ),
                    PreferenceNotice(metadata: widget.metadata),
                    CourseTimeline(places: _spots(index)),
                  ],
                ),
              ),
            ),
    );
  }
}
