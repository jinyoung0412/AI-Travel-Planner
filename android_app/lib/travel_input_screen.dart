import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'travel_result_screen.dart';
import 'api_service.dart';

class TravelInputScreen extends StatefulWidget {
  const TravelInputScreen({super.key});

  @override
  State<TravelInputScreen> createState() => _TravelInputScreenState();
}

class _TravelInputScreenState extends State<TravelInputScreen> {
  String selectedTransport = '대중교통/도보';
  int personCount = 1;
  String selectedRegion = '천안';
  String duration = '당일치기';
  final List<String> selectedThemes = [];
  bool isLoading = false;
  double? currentLat;
  double? currentLng;

  final List<String> transportOptions = ['대중교통/도보', '승용차'];
  final List<String> regionOptions = [
    '천안',
    '아산',
  ];
  final List<String> durationOptions = ['당일치기', '1박 2일', '2박 3일', '3박 4일'];
  final List<String> themeOptions = ['힐링', '맛집', '액티비티', '역사/문화', '바다', '카페'];

  Future<bool> _fetchCurrentLocation() async {
    LocationPermission permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('위치 권한이 거부되었습니다. 승용차 이동 시 위치 정보가 필요합니다.')),
          );
        }
        return false;
      }
    }
    if (permission == LocationPermission.deniedForever) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('위치 권한이 영구적으로 거부되었습니다. 설정에서 권한을 허용해주세요.')),
        );
      }
      return false;
    }

    final position = await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(accuracy: LocationAccuracy.high),
    );
    setState(() {
      currentLat = position.latitude;
      currentLng = position.longitude;
    });
    return true;
  }

  int _convertDurationToDays(String durationStr) {
    if (durationStr == '1박 2일') return 2;
    if (durationStr == '2박 3일') return 3;
    if (durationStr == '3박 4일') return 4;
    return 1;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('여행 정보 입력')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
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

            _buildSectionTitle('여행 인원'),
            Row(
              children: [
                IconButton(
                  icon: const Icon(Icons.remove_circle_outline),
                  onPressed: () {
                    if (personCount > 1) setState(() => personCount--);
                  },
                ),
                Text(
                  '$personCount명',
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.add_circle_outline),
                  onPressed: () {
                    setState(() => personCount++);
                  },
                ),
              ],
            ),
            const SizedBox(height: 20),

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

            _buildSectionTitle('선호 테마 (다중 선택)'),
            Wrap(
              spacing: 8.0,
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

            SizedBox(
              width: double.infinity,
              height: 50,
              child: ElevatedButton(
                onPressed: isLoading
                    ? null
                    : () async {
                        if (selectedThemes.isEmpty) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('테마를 적어도 하나 선택해주세요!')),
                          );
                          return;
                        }

                        setState(() => isLoading = true);

                        // 승용차 선택 시 현재 위치 수집
                        if (selectedTransport == '승용차') {
                          final success = await _fetchCurrentLocation();
                          if (!success) {
                            setState(() => isLoading = false);
                            return;
                          }
                        }

                        try {
                          int requestDays = _convertDurationToDays(duration);

                          final response = await ApiService.getRecommendation(
                            transport: selectedTransport,
                            personCount: personCount,
                            region: selectedRegion,
                            duration: duration,
                            days: requestDays,
                            themes: selectedThemes,
                            userLat: currentLat,
                            userLng: currentLng,
                          );

                          setState(() {
                            isLoading = false;
                          });

                          if (response != null && response['success'] == true) {
                            if (!context.mounted) return;
                            Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (context) => TravelResultScreen(
                                  region: selectedRegion,
                                  themes: selectedThemes,
                                  duration: duration,
                                  aiData: response['data'],
                                ),
                              ),
                            );
                          } else {
                            if (!context.mounted) return;
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text('서버 응답 오류가 발생했습니다.'),
                              ),
                            );
                          }
                        } catch (e) {
                          setState(() {
                            isLoading = false;
                          });
                          if (!context.mounted) return;
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text('네트워크 오류: $e')),
                          );
                        }
                      },
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.blue,
                  foregroundColor: Colors.white,
                ),
                child: isLoading
                    ? const SizedBox(
                        width: 24,
                        height: 24,
                        child: CircularProgressIndicator(
                          color: Colors.white,
                          strokeWidth: 3,
                        ),
                      )
                    : const Text('여행 코스 추천받기', style: TextStyle(fontSize: 18)),
              ),
            ),
          ],
        ),
      ),
    );
  }

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
