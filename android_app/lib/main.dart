import 'package:flutter/material.dart';
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';
import 'package:provider/provider.dart';
import 'auth_service.dart';
import 'input_screen.dart';
import 'saved_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  KakaoSdk.init(nativeAppKey: 'b5d634b3a91dd5db5059c1b96c2a000e');
  runApp(
    ChangeNotifierProvider(
      create: (_) => AuthService()..loadFromPrefs(),
      child: const MyApp(),
    ),
  );
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '즉흥 여행',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFFFF7043)),
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthService>();
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8F3),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const SizedBox.shrink(),
                  Row(
                    children: [
                      if (auth.isLoggedIn) ...[
                        IconButton(
                          icon: const Icon(Icons.bookmark_outline_rounded),
                          onPressed: () => Navigator.push(
                            context,
                            MaterialPageRoute(builder: (_) => const SavedScreen()),
                          ),
                        ),
                        GestureDetector(
                          onTap: () => _showProfileMenu(context, auth),
                          child: CircleAvatar(
                            radius: 16,
                            backgroundImage: auth.profileImg != null
                                ? NetworkImage(auth.profileImg!)
                                : null,
                            child: auth.profileImg == null
                                ? const Icon(Icons.person, size: 18)
                                : null,
                          ),
                        ),
                      ] else
                        TextButton(
                          onPressed: () => _login(context, auth),
                          child: const Text('로그인',
                              style: TextStyle(color: Color(0xFFFF7043))),
                        ),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 16),
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
      ),
    );
  }

  Future<void> _login(BuildContext context, AuthService auth) async {
    final ok = await auth.loginWithKakao();
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('로그인에 실패했어요.')),
      );
    }
  }

  void _showProfileMenu(BuildContext context, AuthService auth) {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(auth.nickname ?? '사용자',
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 20),
            ListTile(
              leading: const Icon(Icons.logout),
              title: const Text('로그아웃'),
              onTap: () { Navigator.pop(context); auth.logout(); },
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
