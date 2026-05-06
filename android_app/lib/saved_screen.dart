import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'auth_service.dart';
import 'api_service.dart';

class SavedScreen extends StatefulWidget {
  const SavedScreen({super.key});

  @override
  State<SavedScreen> createState() => _SavedScreenState();
}

class _SavedScreenState extends State<SavedScreen> with SingleTickerProviderStateMixin {
  late TabController _tab;
  List<dynamic> _spots = [];
  List<dynamic> _courses = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 2, vsync: this);
    _load();
  }

  Future<void> _load() async {
    final token = context.read<AuthService>().token;
    if (token == null) return;
    final spots   = await ApiService.getSavedSpots(token);
    final courses = await ApiService.getSavedCourses(token);
    if (mounted) setState(() { _spots = spots; _courses = courses; _loading = false; });
  }

  Future<void> _deleteSpot(int id) async {
    final token = context.read<AuthService>().token;
    if (token == null) return;
    await ApiService.deleteSpot(token, id);
    setState(() => _spots.removeWhere((s) => s['id'] == id));
  }

  Future<void> _deleteCourse(int id) async {
    final token = context.read<AuthService>().token;
    if (token == null) return;
    await ApiService.deleteCourse(token, id);
    setState(() => _courses.removeWhere((c) => c['id'] == id));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8F3),
      appBar: AppBar(
        backgroundColor: const Color(0xFFFFF8F3),
        elevation: 0,
        foregroundColor: const Color(0xFF1A1A1A),
        title: const Text('저장한 장소'),
        bottom: TabBar(
          controller: _tab,
          labelColor: const Color(0xFFFF7043),
          unselectedLabelColor: Colors.grey,
          indicatorColor: const Color(0xFFFF7043),
          tabs: const [Tab(text: '스팟'), Tab(text: '코스')],
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : TabBarView(
              controller: _tab,
              children: [_buildSpots(), _buildCourses()],
            ),
    );
  }

  Widget _buildSpots() {
    if (_spots.isEmpty) return const Center(child: Text('저장된 스팟이 없어요'));
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _spots.length,
      itemBuilder: (_, i) {
        final s = _spots[i];
        return Card(
          margin: const EdgeInsets.only(bottom: 12),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          child: ListTile(
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            title: Text(s['name'] ?? '', style: const TextStyle(fontWeight: FontWeight.bold)),
            subtitle: Text(s['category'] ?? ''),
            trailing: IconButton(
              icon: const Icon(Icons.delete_outline, color: Colors.grey),
              onPressed: () => _deleteSpot(s['id']),
            ),
          ),
        );
      },
    );
  }

  Widget _buildCourses() {
    if (_courses.isEmpty) return const Center(child: Text('저장된 코스가 없어요'));
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _courses.length,
      itemBuilder: (_, i) {
        final c = _courses[i];
        final spots = c['spots'] as List? ?? [];
        return Card(
          margin: const EdgeInsets.only(bottom: 16),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        c['region'] ?? '코스',
                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.delete_outline, color: Colors.grey),
                      onPressed: () => _deleteCourse(c['id']),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                ...spots.asMap().entries.map((e) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    children: [
                      Container(
                        width: 24, height: 24,
                        decoration: const BoxDecoration(
                          color: Color(0xFF26C6DA),
                          shape: BoxShape.circle,
                        ),
                        alignment: Alignment.center,
                        child: Text('${e.key + 1}',
                            style: const TextStyle(color: Colors.white, fontSize: 12)),
                      ),
                      const SizedBox(width: 10),
                      Text(e.value['name'] ?? ''),
                    ],
                  ),
                )),
              ],
            ),
          ),
        );
      },
    );
  }
}
