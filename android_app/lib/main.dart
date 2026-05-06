import 'package:flutter/material.dart';
import 'input_screen.dart';
import 'saved_screen.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '오늘 충남',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFFFF7043)),
        useMaterial3: true,
      ),
      home: const RootScreen(),
    );
  }
}

class RootScreen extends StatefulWidget {
  const RootScreen({super.key});

  @override
  State<RootScreen> createState() => _RootScreenState();
}

class _RootScreenState extends State<RootScreen> {
  int _tab = 0;
  final _savedKey = GlobalKey<SavedScreenState>();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8F3),
      body: IndexedStack(
        index: _tab,
        children: [const HomeScreen(), SavedScreen(key: _savedKey)],
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _tab,
        onTap: (i) {
          if (i == 1) _savedKey.currentState?.refresh();
          setState(() => _tab = i);
        },
        backgroundColor: Colors.white,
        selectedItemColor: const Color(0xFFFF7043),
        unselectedItemColor: Colors.grey.shade400,
        selectedLabelStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12),
        unselectedLabelStyle: const TextStyle(fontSize: 12),
        elevation: 12,
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.explore_rounded), label: '추천'),
          BottomNavigationBarItem(icon: Icon(Icons.bookmark_rounded), label: '저장'),
        ],
      ),
    );
  }
}

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 16),
            const Text(
              '오늘 충남',
              style: TextStyle(
                fontSize: 28,
                fontWeight: FontWeight.w900,
                color: Color(0xFFFF7043),
                letterSpacing: -0.5,
              ),
            ),
            const SizedBox(height: 6),
            const Text(
              '지금 어디\n가볼까요?',
              style: TextStyle(
                fontSize: 34,
                fontWeight: FontWeight.bold,
                height: 1.3,
                color: Color(0xFF1A1A1A),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '충남 천안 · 아산',
              style: TextStyle(fontSize: 16, color: Colors.grey.shade500),
            ),
            const SizedBox(height: 56),
            _ModeCard(
              title: '스팟 추천',
              subtitle: '밥집, 카페, 산책 등\n한 가지 장소 즉시 탐색',
              icon: Icons.bolt_rounded,
              color: const Color(0xFFFF7043),
              mode: 'spot',
            ),
            const SizedBox(height: 16),
            _ModeCard(
              title: '코스 추천',
              subtitle: '내가 원하는 순서로\n당일 코스 직접 구성',
              icon: Icons.route_rounded,
              color: const Color(0xFF26C6DA),
              mode: 'course',
            ),
          ],
        ),
      ),
    );
  }
}

class _ModeCard extends StatelessWidget {
  final String title;
  final String subtitle;
  final IconData icon;
  final Color color;
  final String mode;

  const _ModeCard({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.color,
    required this.mode,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => InputScreen(mode: mode)),
      ),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: 0.35),
              blurRadius: 16,
              offset: const Offset(0, 6),
            ),
          ],
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    subtitle,
                    style: TextStyle(
                      fontSize: 14,
                      color: Colors.white.withValues(alpha: 0.85),
                      height: 1.5,
                    ),
                  ),
                ],
              ),
            ),
            Icon(icon, size: 52, color: Colors.white.withValues(alpha: 0.85)),
          ],
        ),
      ),
    );
  }
}
