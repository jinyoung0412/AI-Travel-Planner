import 'package:flutter/material.dart';
import 'bookmark_button.dart';
import 'course_timeline.dart';
import 'course_summary_card.dart';
import 'local_storage_service.dart';
import 'travel_data.dart';
import 'result_actions.dart';
import 'result_notice.dart';
import 'course_comparison.dart';
import 'result_entrance.dart';
import 'course_map_data.dart';
import 'course_map_panel.dart';
import 'network/course_route_client.dart';

class CourseResultScreen extends StatefulWidget {
  final List<List<dynamic>> courses;
  final int requestedCount;
  final String region;
  final Map<String, dynamic> metadata;
  final List<dynamic> courseMetrics;
  final bool sameAsPrevious;
  final KakaoMapConfiguration mapConfiguration;
  final CourseMapSessionFactory? mapSessionFactory;
  final String transport;
  final CourseRouteLoader? routeLoader;

  const CourseResultScreen({
    super.key,
    required this.courses,
    required this.requestedCount,
    this.region = '',
    this.metadata = const {},
    this.courseMetrics = const [],
    this.sameAsPrevious = false,
    this.mapConfiguration = const KakaoMapConfiguration(),
    this.mapSessionFactory,
    this.transport = '대중교통',
    this.routeLoader,
  });

  @override
  State<CourseResultScreen> createState() => _CourseResultScreenState();
}

class _CourseResultScreenState extends State<CourseResultScreen> {
  final CourseRouteClient _routeClient = CourseRouteClient();
  final PageController _pageController = PageController();
  int _currentPage = 0;
  final Map<int, int> _selectedStops = {};
  final Map<int, List<GlobalKey>> _stopKeys = {};
  final Map<int, GlobalKey> _mapKeys = {};

  List<GlobalKey> _keys(int course, int count) => _stopKeys.putIfAbsent(
    course,
    () => List.generate(count, (_) => GlobalKey()),
  );

  void _selectStop(int course, int stop, {required bool fromMap}) {
    if (!mounted ||
        course != _currentPage ||
        stop < 0 ||
        stop >= _spots(course).length) {
      return;
    }
    setState(() => _selectedStops[course] = stop);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || course != _currentPage) return;
      final keys = _stopKeys[course];
      final target = fromMap
          ? (keys == null ? null : keys[stop].currentContext)
          : _mapKeys[course]?.currentContext;
      if (target == null || target.size?.isEmpty != false) return;
      Scrollable.ensureVisible(
        target,
        alignment: fromMap ? 0.5 : 0,
        duration: MediaQuery.disableAnimationsOf(context)
            ? Duration.zero
            : const Duration(milliseconds: 220),
      );
    });
  }

  @override
  void didUpdateWidget(CourseResultScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.courses != widget.courses) {
      _selectedStops.clear();
      _stopKeys.clear();
      _mapKeys.clear();
      if (_currentPage >= widget.courses.length) {
        _currentPage = 0;
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted && _pageController.hasClients) {
            _pageController.jumpToPage(0);
          }
        });
      }
    }
  }

  @override
  void dispose() {
    _routeClient.close();
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

  void _showPage(int index) {
    if (MediaQuery.disableAnimationsOf(context)) {
      _pageController.jumpToPage(index);
    } else {
      _pageController.animateToPage(
        index,
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeInOut,
      );
    }
  }

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
              color: const Color(0xFF914B33),
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
      bottomNavigationBar: const ResultActions(quiet: true),
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
                padding: const EdgeInsets.only(top: 8, bottom: 32),
                child: ResultEntrance(
                  child: Column(
                    children: [
                      if (widget.sameAsPrevious) const RepeatedResultNotice(),
                      if (widget.courses.length > 1) ...[
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 20),
                          child: Align(
                            alignment: Alignment.centerLeft,
                            child: Wrap(
                              spacing: 16,
                              children: List.generate(
                                widget.courses.length,
                                (i) => Tooltip(
                                  message: '코스 ${i + 1} 보기',
                                  child: Semantics(
                                    selected: i == index,
                                    child: TextButton(
                                      onPressed: () => _showPage(i),
                                      style: TextButton.styleFrom(
                                        foregroundColor: i == index
                                            ? const Color(0xFF914B33)
                                            : const Color(0xFF81736A),
                                        minimumSize: const Size(64, 48),
                                        shape: const RoundedRectangleBorder(),
                                        side: BorderSide.none,
                                      ),
                                      child: Container(
                                        padding: const EdgeInsets.symmetric(
                                          vertical: 10,
                                        ),
                                        decoration: BoxDecoration(
                                          border: Border(
                                            bottom: BorderSide(
                                              color: i == index
                                                  ? const Color(0xFF914B33)
                                                  : Colors.transparent,
                                              width: 2,
                                            ),
                                          ),
                                        ),
                                        child: Text('코스 ${i + 1}'),
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
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
                            '코스 ${widget.courses.length}개를 찾았어요.',
                            style: const TextStyle(
                              fontSize: 13,
                              color: Color(0xFF795548),
                            ),
                          ),
                        ),
                      CourseMapPanel(
                        key: _mapKeys.putIfAbsent(index, GlobalKey.new),
                        active: index == _currentPage,
                        places: _spots(index),
                        selectedIndex: _selectedStops[index],
                        onSelect: (stop) =>
                            _selectStop(index, stop, fromMap: true),
                        configuration: widget.mapConfiguration,
                        sessionFactory: widget.mapSessionFactory,
                        transport: widget.transport,
                        routeLoader: widget.routeLoader ?? _routeClient.load,
                      ),
                      Container(
                        key: ValueKey('course-map-summary-$index'),
                        padding: const EdgeInsets.symmetric(horizontal: 20),
                        width: double.infinity,
                        decoration: const BoxDecoration(
                          color: Color(0xFFFFFDFB),
                          border: Border(
                            bottom: BorderSide(color: Color(0xFFEADFD5)),
                          ),
                        ),
                        child: Wrap(
                          alignment: WrapAlignment.spaceBetween,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          spacing: 12,
                          children: [
                            CourseSummaryCard(
                              key: ValueKey('course-summary-$index'),
                              metric: _metric(index),
                              metadata: widget.metadata,
                              places: _spots(index),
                              quiet: true,
                              showDescription: false,
                            ),
                            if (widget.courses.length > 1)
                              TextButton.icon(
                                style: TextButton.styleFrom(
                                  foregroundColor: const Color(0xFF914B33),
                                  minimumSize: const Size(0, 48),
                                ),
                                icon: const Icon(Icons.north_east, size: 16),
                                label: const Text(
                                  '코스 비교',
                                  style: TextStyle(fontSize: 12),
                                ),
                                onPressed: () async {
                                  final selected =
                                      await showModalBottomSheet<int>(
                                        context: context,
                                        isScrollControlled: true,
                                        useSafeArea: true,
                                        builder: (_) => CourseComparison(
                                          courses: List.generate(
                                            widget.courses.length,
                                            _spots,
                                          ),
                                          metrics: List.generate(
                                            widget.courses.length,
                                            _metric,
                                          ),
                                          selected: _currentPage,
                                        ),
                                      );
                                  if (mounted && selected != null) {
                                    _showPage(selected);
                                  }
                                },
                              ),
                          ],
                        ),
                      ),
                      Padding(
                        padding: const EdgeInsets.fromLTRB(20, 24, 20, 0),
                        child: CourseTimeline(
                          key: ValueKey('course-timeline-$index'),
                          places: _spots(index),
                          compact: true,
                          quiet: true,
                          selectedIndex: _selectedStops[index],
                          stopKeys: _keys(index, widget.courses[index].length),
                          onSelect: (stop) =>
                              _selectStop(index, stop, fromMap: false),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
    );
  }
}
