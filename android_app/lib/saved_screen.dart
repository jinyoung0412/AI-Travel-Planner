import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'local_storage_service.dart';

class SavedScreen extends StatefulWidget {
  const SavedScreen({super.key});

  @override
  State<SavedScreen> createState() => SavedScreenState();
}

class SavedScreenState extends State<SavedScreen> with SingleTickerProviderStateMixin {
  late TabController _tab;
  List<Map<String, dynamic>> _spots = [];
  List<Map<String, dynamic>> _courses = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 2, vsync: this);
    _load();
  }

  void refresh() => _load();

  Future<void> _load() async {
    final spots   = await LocalStorageService.getSavedSpots();
    final courses = await LocalStorageService.getSavedCourses();
    if (mounted) setState(() { _spots = spots; _courses = courses; _loading = false; });
  }

  Future<void> _deleteSpot(String name) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('스팟 삭제'),
        content: Text('$name\n저장된 스팟을 삭제할까요?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('취소')),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('삭제', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (ok != true) return;
    await LocalStorageService.deleteSpot(name);
    setState(() => _spots.removeWhere((s) => s['name'] == name));
  }

  Future<void> _deleteCourse(int index) async {
    final course = _courses[index];
    final region = course['region'] as String? ?? '저장된 코스';
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('코스 삭제'),
        content: Text('$region\n저장된 코스를 삭제할까요?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('취소')),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('삭제', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (ok != true) return;
    await LocalStorageService.deleteCourse(index);
    setState(() => _courses.removeAt(index));
  }

  Future<void> _openMap(String? kakaoUrl, double? lat, double? lng, String name) async {
    if (kakaoUrl != null && kakaoUrl.isNotEmpty) {
      final uri = Uri.parse(kakaoUrl);
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
        return;
      }
    }
    if (lat != null && lng != null) {
      final appUri = Uri.parse('kakaomap://look?p=$lat,$lng');
      final webUri = Uri.parse(
          'https://map.kakao.com/link/map/${Uri.encodeComponent(name)},$lat,$lng');
      if (await canLaunchUrl(appUri)) {
        await launchUrl(appUri);
      } else {
        await launchUrl(webUri, mode: LaunchMode.externalApplication);
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
        automaticallyImplyLeading: false,
        title: const Text('저장한 장소', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 22)),
        bottom: TabBar(
          controller: _tab,
          labelColor: const Color(0xFFFF7043),
          unselectedLabelColor: Colors.grey,
          indicatorColor: const Color(0xFFFF7043),
          indicatorWeight: 3,
          tabs: [
            Tab(text: '스팟 ${_spots.isNotEmpty ? "(${_spots.length})" : ""}'),
            Tab(text: '코스 ${_courses.isNotEmpty ? "(${_courses.length})" : ""}'),
          ],
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFFFF7043)))
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
            Icon(Icons.bookmark_outline_rounded, size: 64, color: Colors.grey.shade300),
            const SizedBox(height: 16),
            Text('저장된 스팟이 없어요',
                style: TextStyle(fontSize: 16, color: Colors.grey.shade400)),
            const SizedBox(height: 8),
            Text('추천 결과에서 ★ 버튼을 눌러 저장해보세요',
                style: TextStyle(fontSize: 13, color: Colors.grey.shade400)),
          ],
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
      itemCount: _spots.length,
      itemBuilder: (_, i) => _SpotCard(
        spot: _spots[i],
        onDelete: () => _deleteSpot(_spots[i]['name']),
        onMapTap: () => _openMap(
          _spots[i]['kakao_url'],
          (_spots[i]['lat'] as num?)?.toDouble(),
          (_spots[i]['lng'] as num?)?.toDouble(),
          _spots[i]['name'] ?? '',
        ),
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
            Text('저장된 코스가 없어요',
                style: TextStyle(fontSize: 16, color: Colors.grey.shade400)),
            const SizedBox(height: 8),
            Text('코스 추천 결과에서 저장 버튼을 눌러보세요',
                style: TextStyle(fontSize: 13, color: Colors.grey.shade400)),
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
    final spots = List<Map<String, dynamic>>.from(course['spots'] ?? []);
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
          child: Column(
            children: [
              const SizedBox(height: 12),
              Container(
                width: 40, height: 4,
                decoration: BoxDecoration(
                  color: Colors.grey.shade300,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
                child: Row(
                  children: [
                    const Icon(Icons.route_rounded, color: Color(0xFF26C6DA)),
                    const SizedBox(width: 8),
                    Text(
                      course['region']?.isNotEmpty == true ? course['region'] : '저장된 코스',
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                    ),
                    const Spacer(),
                    Text('${spots.length}개 장소',
                        style: TextStyle(fontSize: 13, color: Colors.grey.shade500)),
                  ],
                ),
              ),
              const Divider(),
              Expanded(
                child: ListView.builder(
                  controller: controller,
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
                  itemCount: spots.length,
                  itemBuilder: (_, i) {
                    final s = spots[i];
                    final isLast = i == spots.length - 1;
                    return IntrinsicHeight(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Column(
                            children: [
                              Container(
                                width: 30, height: 30,
                                decoration: const BoxDecoration(
                                  color: Color(0xFF26C6DA),
                                  shape: BoxShape.circle,
                                ),
                                alignment: Alignment.center,
                                child: Text('${i + 1}',
                                    style: const TextStyle(
                                        color: Colors.white,
                                        fontWeight: FontWeight.bold,
                                        fontSize: 13)),
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
                          Expanded(
                            child: Container(
                              margin: EdgeInsets.only(bottom: isLast ? 0 : 12),
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(12),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withValues(alpha: 0.05),
                                    blurRadius: 6,
                                    offset: const Offset(0, 2),
                                  ),
                                ],
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(s['name'] ?? '',
                                      style: const TextStyle(
                                          fontWeight: FontWeight.bold, fontSize: 15)),
                                  if ((s['category'] ?? '').isNotEmpty) ...[
                                    const SizedBox(height: 4),
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 8, vertical: 2),
                                      decoration: BoxDecoration(
                                        color: const Color(0xFFE8F9FB),
                                        borderRadius: BorderRadius.circular(6),
                                      ),
                                      child: Text(s['category'],
                                          style: const TextStyle(
                                              fontSize: 11, color: Color(0xFF26C6DA))),
                                    ),
                                  ],
                                  const SizedBox(height: 8),
                                  GestureDetector(
                                    onTap: () => _openMap(
                                      s['kakao_url'],
                                      (s['lat'] as num?)?.toDouble(),
                                      (s['lng'] as num?)?.toDouble(),
                                      s['name'] ?? '',
                                    ),
                                    child: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        Icon(Icons.map_outlined,
                                            size: 14, color: Colors.grey.shade500),
                                        const SizedBox(width: 4),
                                        Text('지도에서 보기',
                                            style: TextStyle(
                                                fontSize: 12,
                                                color: Colors.grey.shade500)),
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
                  },
                ),
              ),
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

  const _SpotCard({required this.spot, required this.onDelete, required this.onMapTap});

  @override
  Widget build(BuildContext context) {
    final category = spot['category'] as String? ?? '';
    return GestureDetector(
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
              width: 44, height: 44,
              decoration: BoxDecoration(
                color: const Color(0xFFFFF0EB),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.place_rounded, color: Color(0xFFFF7043), size: 24),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(spot['name'] ?? '',
                      style: const TextStyle(
                          fontSize: 15, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      if (category.isNotEmpty) ...[
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: const Color(0xFFFFF0EB),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(category,
                              style: const TextStyle(
                                  fontSize: 11, color: Color(0xFFFF7043))),
                        ),
                        const SizedBox(width: 6),
                      ],
                      Text('탭하여 지도 열기',
                          style: TextStyle(
                              fontSize: 11, color: Colors.grey.shade400)),
                    ],
                  ),
                ],
              ),
            ),
            IconButton(
              icon: Icon(Icons.delete_outline, color: Colors.grey.shade400, size: 20),
              onPressed: onDelete,
            ),
          ],
        ),
      ),
    );
  }
}

class _CourseCard extends StatelessWidget {
  final Map<String, dynamic> course;
  final VoidCallback onDelete;
  final VoidCallback onTap;

  const _CourseCard({required this.course, required this.onDelete, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final spots = List<Map<String, dynamic>>.from(course['spots'] ?? []);
    final region = course['region'] as String? ?? '';

    return GestureDetector(
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
                  width: 44, height: 44,
                  decoration: BoxDecoration(
                    color: const Color(0xFFE8F9FB),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.route_rounded,
                      color: Color(0xFF26C6DA), size: 24),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(region.isNotEmpty ? region : '저장된 코스',
                          style: const TextStyle(
                              fontSize: 15, fontWeight: FontWeight.bold)),
                      Text('${spots.length}개 장소 · 탭하여 자세히 보기',
                          style: TextStyle(
                              fontSize: 11, color: Colors.grey.shade400)),
                    ],
                  ),
                ),
                IconButton(
                  icon: Icon(Icons.delete_outline,
                      color: Colors.grey.shade400, size: 20),
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
                              width: 28, height: 28,
                              decoration: const BoxDecoration(
                                color: Color(0xFF26C6DA),
                                shape: BoxShape.circle,
                              ),
                              alignment: Alignment.center,
                              child: Text('${e.key + 1}',
                                  style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 11,
                                      fontWeight: FontWeight.bold)),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              e.value['name'] ?? '',
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
                          width: 16, height: 2,
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
    );
  }
}
