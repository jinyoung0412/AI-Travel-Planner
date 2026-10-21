import 'package:flutter/material.dart';
import 'place_map_button.dart';
import 'course_timeline.dart';
import 'travel_data.dart';
import 'preference_notice.dart';
import 'local_storage_service.dart';

class SavedScreen extends StatefulWidget {
  const SavedScreen({super.key});

  @override
  State<SavedScreen> createState() => SavedScreenState();
}

class SavedScreenState extends State<SavedScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tab;
  List<Map<String, dynamic>> _spots = [];
  List<Map<String, dynamic>> _courses = [];
  bool _loading = true;
  String? _error;
  int _loadRevision = 0;
  bool _deleting = false;
  bool _mapOpening = false;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 2, vsync: this);
    _load();
  }

  void refresh() => _load();

  @override
  void dispose() {
    _loadRevision++;
    _tab.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final revision = ++_loadRevision;
    try {
      final spots = await LocalStorageService.getSavedSpots();
      final courses = await LocalStorageService.getSavedCourses();
      if (!mounted || revision != _loadRevision) return;
      setState(() {
        _spots = spots;
        _courses = courses;
        _loading = false;
        _error = null;
      });
    } catch (_) {
      if (!mounted || revision != _loadRevision) return;
      setState(() {
        _loading = false;
        _error = '저장한 내용을 읽지 못했어요. 기존 데이터는 보존됩니다.';
      });
    }
  }

  Future<void> _openPlace(Map<String, dynamic> place) async {
    if (_mapOpening) return;
    _mapOpening = true;
    try {
      await openPlaceMap(context, place);
    } finally {
      _mapOpening = false;
    }
  }

  Future<void> _delete(Future<void> Function() operation) async {
    try {
      await operation();
      if (mounted) await _load();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('삭제하지 못했어요. 다시 시도해주세요.')));
      }
    } finally {
      _deleting = false;
    }
  }

  Future<void> _deleteSpot(Map<String, dynamic> spot) async {
    if (_deleting) return;
    _deleting = true;
    final name = PlaceData.fromJson(spot).name;
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('스팟 삭제'),
        content: Text('$name\n저장된 스팟을 삭제할까요?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('취소'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('삭제', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) {
      _deleting = false;
      return;
    }
    await _delete(() => LocalStorageService.deleteSpot(spot));
  }

  Future<void> _deleteCourse(int index) async {
    if (_deleting) return;
    _deleting = true;
    final course = _courses[index];
    final spots = jsonObjects(course['spots'] ?? []);
    final region = course['region'] is String
        ? course['region'] as String
        : '저장된 코스';
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('코스 삭제'),
        content: Text('$region\n저장된 코스를 삭제할까요?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('취소'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('삭제', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) {
      _deleting = false;
      return;
    }
    await _delete(() => LocalStorageService.removeCourseBySpots(spots));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8F3),
      appBar: AppBar(
        backgroundColor: const Color(0xFFFFF8F3),
        elevation: 0,
        automaticallyImplyLeading: false,
        title: const Text(
          '저장한 장소',
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 22),
        ),
        bottom: TabBar(
          controller: _tab,
          labelColor: const Color(0xFFFF7043),
          unselectedLabelColor: Colors.grey,
          indicatorColor: const Color(0xFFFF7043),
          indicatorWeight: 3,
          tabs: [
            Tab(text: '스팟 ${_spots.isNotEmpty ? "(${_spots.length})" : ""}'),
            Tab(
              text: '코스 ${_courses.isNotEmpty ? "(${_courses.length})" : ""}',
            ),
          ],
        ),
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: Color(0xFFFF7043)),
            )
          : _error != null
          ? Center(
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(_error!, textAlign: TextAlign.center),
                    TextButton(onPressed: _load, child: const Text('다시 읽기')),
                  ],
                ),
              ),
            )
          : TabBarView(
              controller: _tab,
              children: [_buildSpots(), _buildCourses()],
            ),
    );
  }

  Widget _buildSpots() {
    if (_spots.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.bookmark_outline_rounded,
              size: 64,
              color: Colors.grey.shade300,
            ),
            const SizedBox(height: 16),
            Text(
              '저장된 스팟이 없어요',
              style: TextStyle(fontSize: 16, color: Colors.grey.shade400),
            ),
            const SizedBox(height: 8),
            Text(
              '추천 결과에서 저장 버튼을 눌러보세요',
              style: TextStyle(fontSize: 13, color: Colors.grey.shade400),
            ),
          ],
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
      itemCount: _spots.length,
      itemBuilder: (_, i) => _SpotCard(
        spot: _spots[i],
        onDelete: () => _deleteSpot(_spots[i]),
        onMapTap: () => _openPlace(_spots[i]),
      ),
    );
  }

  Widget _buildCourses() {
    if (_courses.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.route_rounded, size: 64, color: Colors.grey.shade300),
            const SizedBox(height: 16),
            Text(
              '저장된 코스가 없어요',
              style: TextStyle(fontSize: 16, color: Colors.grey.shade400),
            ),
            const SizedBox(height: 8),
            Text(
              '코스 추천 결과에서 저장 버튼을 눌러보세요',
              style: TextStyle(fontSize: 13, color: Colors.grey.shade400),
            ),
          ],
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
      itemCount: _courses.length,
      itemBuilder: (_, i) => _CourseCard(
        course: _courses[i],
        onDelete: () => _deleteCourse(i),
        onTap: () => _showCourseDetail(context, _courses[i]),
      ),
    );
  }

  void _showCourseDetail(BuildContext context, Map<String, dynamic> course) {
    final spots = jsonObjects(course['spots'] ?? []);
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => DraggableScrollableSheet(
        initialChildSize: 0.65,
        maxChildSize: 0.92,
        minChildSize: 0.4,
        builder: (_, controller) => Container(
          decoration: const BoxDecoration(
            color: Color(0xFFFFF8F3),
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          child: ListView(
            controller: controller,
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.grey.shade300,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text(
                course['region'] is String &&
                        (course['region'] as String).isNotEmpty
                    ? course['region'] as String
                    : '저장된 코스',
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Text(
                '${spots.length}개 장소',
                style: TextStyle(fontSize: 13, color: Colors.grey.shade500),
              ),
              const SizedBox(height: 8),
              PreferenceNotice(metadata: jsonObject(course['metadata'] ?? {})),
              Text(
                distanceNotice(course['metric'], places: spots),
                style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
              ),
              const Divider(),
              CourseTimeline(places: spots),
            ],
          ),
        ),
      ),
    );
  }
}

class _SpotCard extends StatelessWidget {
  final Map<String, dynamic> spot;
  final VoidCallback onDelete;
  final VoidCallback onMapTap;

  const _SpotCard({
    required this.spot,
    required this.onDelete,
    required this.onMapTap,
  });

  @override
  Widget build(BuildContext context) {
    final data = PlaceData.fromJson(spot);
    final category = data.category;
    return Semantics(
      button: true,
      label: '${data.name} 지도에서 보기',
      child: InkWell(
        onTap: onMapTap,
        child: Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.06),
                blurRadius: 10,
                offset: const Offset(0, 3),
              ),
            ],
          ),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: const Color(0xFFFFF0EB),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.place_rounded,
                  color: Color(0xFFFF7043),
                  size: 24,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      data.name,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Wrap(
                      spacing: 6,
                      runSpacing: 4,
                      children: [
                        if (category.isNotEmpty) ...[
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFFFFF0EB),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              category,
                              style: const TextStyle(
                                fontSize: 11,
                                color: Color(0xFFFF7043),
                              ),
                            ),
                          ),
                          const SizedBox(width: 6),
                        ],
                        Text(
                          '탭하여 지도 열기',
                          style: TextStyle(
                            fontSize: 11,
                            color: Colors.grey.shade400,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: '스팟 삭제',
                icon: Icon(
                  Icons.delete_outline,
                  color: Colors.grey.shade400,
                  size: 20,
                ),
                onPressed: onDelete,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CourseCard extends StatelessWidget {
  final Map<String, dynamic> course;
  final VoidCallback onDelete;
  final VoidCallback onTap;

  const _CourseCard({
    required this.course,
    required this.onDelete,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final spots = jsonObjects(course['spots'] ?? []);
    final region = course['region'] is String ? course['region'] as String : '';

    return Semantics(
      button: true,
      label: '$region 코스 자세히 보기',
      child: InkWell(
        onTap: onTap,
        child: Container(
          margin: const EdgeInsets.only(bottom: 14),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.06),
                blurRadius: 10,
                offset: const Offset(0, 3),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: const Color(0xFFE8F9FB),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(
                      Icons.route_rounded,
                      color: Color(0xFF26C6DA),
                      size: 24,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          region.isNotEmpty ? region : '저장된 코스',
                          style: const TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        Text(
                          '${spots.length}개 장소 · 탭하여 자세히 보기',
                          style: TextStyle(
                            fontSize: 11,
                            color: Colors.grey.shade400,
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: '코스 삭제',
                    icon: Icon(
                      Icons.delete_outline,
                      color: Colors.grey.shade400,
                      size: 20,
                    ),
                    onPressed: onDelete,
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: spots.asMap().entries.map((e) {
                  final isLast = e.key == spots.length - 1;
                  return Expanded(
                    child: Row(
                      children: [
                        Expanded(
                          child: Column(
                            children: [
                              Container(
                                width: 28,
                                height: 28,
                                decoration: const BoxDecoration(
                                  color: Color(0xFF26C6DA),
                                  shape: BoxShape.circle,
                                ),
                                alignment: Alignment.center,
                                child: Text(
                                  '${e.key + 1}',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 11,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                PlaceData.fromJson(e.value).name,
                                style: const TextStyle(fontSize: 10),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                textAlign: TextAlign.center,
                              ),
                            ],
                          ),
                        ),
                        if (!isLast)
                          Container(
                            width: 16,
                            height: 2,
                            color: const Color(0xFF26C6DA),
                            margin: const EdgeInsets.only(bottom: 18),
                          ),
                      ],
                    ),
                  );
                }).toList(),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
