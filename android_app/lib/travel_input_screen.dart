import 'package:flutter/material.dart';
import 'travel_result_screen.dart';

class TravelInputScreen extends StatefulWidget {
  const TravelInputScreen({super.key});

  @override
  State<TravelInputScreen> createState() => _TravelInputScreenState();
}

class _TravelInputScreenState extends State<TravelInputScreen> {
  // 1. 사용자가 입력한 값을 저장할 변수들
  String selectedTransport = '대중교통/도보'; // 기본값
  int personCount = 1;
  String selectedRegion = '충남 전체';
  String duration = '당일치기';

  // 선택된 테마들을 담을 리스트
  final List<String> selectedThemes = [];

  // 2. 선택지 데이터 (나중에 서버에서 받아올 수도 있음)
  final List<String> transportOptions = ['대중교통/도보', '승용차'];
  final List<String> regionOptions = ['충남 전체', '천안', '아산', '공주', '보령', '서산'];
  final List<String> durationOptions = ['당일치기', '1박 2일', '2박 3일', '3박 4일'];
  final List<String> themeOptions = ['힐링', '맛집', '액티비티', '역사/문화', '바다', '카페'];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('여행 정보 입력')),
      body: SingleChildScrollView( // 화면이 작으면 스크롤 되게
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ------------------------------------------------
            _buildSectionTitle('이동 수단'),
            DropdownButtonFormField<String>(
              value: selectedTransport,
              items: transportOptions.map((String value) {
                return DropdownMenuItem<String>(
                  value: value,
                  child: Text(value),
                );
              }).toList(),
              onChanged: (newValue) {
                setState(() {
                  selectedTransport = newValue!;
                });
              },
              decoration: const InputDecoration(border: OutlineInputBorder()),
            ),
            const SizedBox(height: 20),

            // ------------------------------------------------
            _buildSectionTitle('여행 인원'),
            Row(
              children: [
                IconButton(
                  icon: const Icon(Icons.remove_circle_outline),
                  onPressed: () {
                    if (personCount > 1) setState(() => personCount--);
                  },
                ),
                Text('$personCount명', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                IconButton(
                  icon: const Icon(Icons.add_circle_outline),
                  onPressed: () {
                    setState(() => personCount++);
                  },
                ),
              ],
            ),
            const SizedBox(height: 20),

            // ------------------------------------------------
            _buildSectionTitle('여행 지역'),
            DropdownButtonFormField<String>(
              value: selectedRegion,
              items: regionOptions.map((String value) {
                return DropdownMenuItem<String>(
                  value: value,
                  child: Text(value),
                );
              }).toList(),
              onChanged: (newValue) {
                setState(() => selectedRegion = newValue!);
              },
              decoration: const InputDecoration(border: OutlineInputBorder()),
            ),
            const SizedBox(height: 20),

            // ------------------------------------------------
            _buildSectionTitle('가용 시간'),
            DropdownButtonFormField<String>(
              value: duration,
              items: durationOptions.map((String value) {
                return DropdownMenuItem<String>(
                  value: value,
                  child: Text(value),
                );
              }).toList(),
              onChanged: (newValue) {
                setState(() => duration = newValue!);
              },
              decoration: const InputDecoration(border: OutlineInputBorder()),
            ),
            const SizedBox(height: 20),

            // ------------------------------------------------
            _buildSectionTitle('선호 테마 (다중 선택)'),
            Wrap(
              spacing: 8.0, // 버튼 사이 간격
              children: themeOptions.map((theme) {
                final isSelected = selectedThemes.contains(theme);
                return FilterChip(
                  label: Text(theme),
                  selected: isSelected,
                  onSelected: (bool selected) {
                    setState(() {
                      if (selected) {
                        selectedThemes.add(theme);
                      } else {
                        selectedThemes.remove(theme);
                      }
                    });
                  },
                  selectedColor: Colors.blue.shade100,
                  checkmarkColor: Colors.blue,
                );
              }).toList(),
            ),
            const SizedBox(height: 40),

            // ------------------------------------------------
            // 완료 버튼
            SizedBox(
              width: double.infinity, // 가로 꽉 차게
              height: 50,
              child: ElevatedButton(
                onPressed: () {
                  // 입력값이 다 채워졌는지 확인 (간단한 유효성 검사)
                  if (selectedThemes.isEmpty) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('테마를 적어도 하나 선택해주세요!')),
                    );
                    return; // 테마 안 고르면 안 넘어감
                  }

                  // 결과 화면으로 이동! (데이터를 들고 갑니다 짐 싸서 🧳)
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (context) => TravelResultScreen(
                        region: selectedRegion,  // "천안"
                        themes: selectedThemes,  // ["맛집", "힐링"]
                        duration: duration,      // "당일치기"
                      ),
                    ),
                  );
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.blue,
                  foregroundColor: Colors.white,
                ),
                child: const Text('여행 코스 추천받기', style: TextStyle(fontSize: 18)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // 소제목 스타일을 통일하기 위한 함수
  Widget _buildSectionTitle(String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8.0),
      child: Text(
        title,
        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
      ),
    );
  }
}