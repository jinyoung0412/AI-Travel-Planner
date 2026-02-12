import 'package:flutter/material.dart';
import 'package:ai_travel_app/travel_input_screen.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '충남 여행 AI',
      theme: ThemeData(
        // 앱의 메인 색상 (충남이니까 파란색 계열 추천!)
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue),
        useMaterial3: true,
      ),
      // 앱을 켰을 때 처음 보여줄 화면
      home: const HomeScreen(),
    );
  }
}

// 홈 화면
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // 1. 상단 바 (AppBar)
      appBar: AppBar(
        title: const Text('AI 충남 여행 플래너'),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
      ),
      // 2. 몸통 (Body)
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text(
              '어떤 여행을 떠나고 싶으신가요?',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 20), // 여백
            // 버튼 예시
            ElevatedButton(
              onPressed: () {
                // 화면 이동 코드 (네비게이션)
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const TravelInputScreen(),
                  ),
                );
              },
              child: const Text('여행 코스 추천받기'),
            ),
          ],
        ),
      ),
    );
  }
}
