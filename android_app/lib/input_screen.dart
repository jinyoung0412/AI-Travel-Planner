import 'dart:async';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'api_service.dart';
import 'spot_result_screen.dart';
import 'course_result_screen.dart';

// ── 지역 중심 좌표 (시청 기준, 차 이동 시 사용) ──────────────────
const Map<String, List<double>> _kRegionCenters = {
  '천안': [36.8151, 127.1139],
  '아산': [36.7898, 127.0043],
};

// ── 대중교통 출발 허브 (지역별) ────────────────────────────────────
const Map<String, List<Map<String, dynamic>>> _kTransitHubs = {
  '천안': [
    {'name': '천안역',           'lat': 36.8082, 'lng': 127.1506},
    {'name': '봉명역',           'lat': 36.8054, 'lng': 127.1430},
    {'name': '쌍용역',           'lat': 36.8011, 'lng': 127.1239},
    {'name': '두정역',           'lat': 36.8201, 'lng': 127.1227},
    {'name': '천안아산역 (KTX)', 'lat': 36.7982, 'lng': 127.1049},
    {'name': '천안종합터미널',   'lat': 36.8005, 'lng': 127.1380},
  ],
  '아산': [
    {'name': '온양온천역',       'lat': 36.7892, 'lng': 127.0039},
    {'name': '신창역',           'lat': 36.7700, 'lng': 126.9830},
    {'name': '탕정역',           'lat': 36.7971, 'lng': 127.0491},
    {'name': '천안아산역 (KTX)', 'lat': 36.7982, 'lng': 127.1049},
    {'name': '아산터미널',       'lat': 36.7896, 'lng': 127.0018},
    {'name': '배방역',           'lat': 36.7976, 'lng': 127.0699},
  ],
};

// ── 페르소나 태그 그룹 ─────────────────────────────────────────────
const Map<String, List<String>> _kTagGroups = {
  '누구와': [
    '혼자', '친구와', '연인과', '부부끼리', '가족 나들이',
    '부모님 모시고', '아이와 함께', '유아/영아 동반',
    '단체/모임', '동아리/클럽', '회식', '소개팅/첫만남',
  ],
  '어떤 분위기': [
    '힐링/여유', '활동적인', '감성적인', '로맨틱한', '조용한',
    '트렌디한', '고급스러운', '아늑한', '이색적인',
    '자연 친화적', '소소한 일상', '설레는',
  ],
  '특별한 날': [
    '기념일', '생일', '졸업·입학 기념', '프로포즈',
    '첫 데이트', '오랜만에 만남', '일상 탈출',
  ],
  '실내 · 야외': [
    '실내 위주', '야외 위주',
  ],
  '어떤 활동': [
    '맛집 탐방', '카페 투어', '문화·역사 탐방', '박물관/전시',
    '쇼핑', '자연/산책', '등산/트레킹', '드라이브',
    '사진 명소', '야경/저녁', '스포츠/레저', '체험 공방',
    '전통/한옥', '공원 나들이', '노래방/실내 오락',
  ],
  '기타': [
    '어르신 동반', '반려동물 동반', '가성비', '아이 친화적', '넓은 공간',
  ],
};

class InputScreen extends StatefulWidget {
  final String mode; // 'spot' | 'course'
  const InputScreen({super.key, required this.mode});

  @override
  State<InputScreen> createState() => _InputScreenState();
}

class _InputScreenState extends State<InputScreen> {
  final _textController = TextEditingController();
  String _region    = '내 주변';
  String _transport = '대중교통/도보';
  String? _selectedHub; // 대중교통 허브 이름 (조건부 표시)
  int _resultCount  = 5; // spot: 3/5/7/10, course: 1/2/3
  bool _isLoading    = false;
  bool _isTagLoading = false;
  double? _gpsLat;
  double? _gpsLng;

  final Set<String> _selectedTags = {};

  bool get _isSpot => widget.mode == 'spot';
  Color get _themeColor =>
      _isSpot ? const Color(0xFFFF7043) : const Color(0xFF26C6DA);

  // 대중교통 허브 선택이 필요한 조건
  bool get _needsHub =>
      _region != '내 주변' && _transport == '대중교통/도보';

  // 실제로 사용할 출발 좌표
  double? get _effectiveLat {
    if (_region == '내 주변') return _gpsLat;
    if (_needsHub && _selectedHub != null) {
      final hub = _kTransitHubs[_region]!
          .firstWhere((h) => h['name'] == _selectedHub, orElse: () => {});
      if (hub.isNotEmpty) return hub['lat'] as double;
    }
    return _kRegionCenters[_region]![0];
  }

  double? get _effectiveLng {
    if (_region == '내 주변') return _gpsLng;
    if (_needsHub && _selectedHub != null) {
      final hub = _kTransitHubs[_region]!
          .firstWhere((h) => h['name'] == _selectedHub, orElse: () => {});
      if (hub.isNotEmpty) return hub['lng'] as double;
    }
    return _kRegionCenters[_region]![1];
  }

  String get _locationLabel {
    if (_region == '내 주변') {
      return _gpsLat != null ? '현재 위치 확인됨' : '위치 가져오는 중...';
    }
    if (_needsHub && _selectedHub != null) return '$_selectedHub 출발 기준';
    if (!_needsHub) return '$_region 중심부 기준 (차)';
    return '$_region — 출발지를 선택해주세요';
  }

  bool get _locationReady {
    if (_region == '내 주변') return _gpsLat != null;
    if (_needsHub) return _selectedHub != null;
    return true;
  }

  List<int> get _countOptions => _isSpot ? [3, 5, 7, 10] : [1, 2, 3, 4, 5];

  @override
  void initState() {
    super.initState();
    _resultCount = _isSpot ? 5 : 3;
    _fetchLocation();
  }

  Future<void> _autoSuggestTags() async {
    final text = _textController.text.trim();
    if (text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('텍스트를 먼저 입력해주세요.')),
      );
      return;
    }
    setState(() => _isTagLoading = true);
    try {
      final suggested = await ApiService.suggestTags(userText: text);
      if (!mounted) { return; }
      final allTags = _kTagGroups.values.expand((l) => l).toSet();
      setState(() {
        _selectedTags
          ..clear()
          ..addAll(suggested.where(allTags.contains));
        _isTagLoading = false;
      });
    } catch (_) {
      if (mounted) { setState(() => _isTagLoading = false); }
    }
  }

  Future<void> _fetchLocation() async {
    LocationPermission perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      perm = await Geolocator.requestPermission();
    }
    if (perm == LocationPermission.deniedForever ||
        perm == LocationPermission.denied) { return; }
    final pos = await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(accuracy: LocationAccuracy.high),
    );
    if (mounted) {
      setState(() { _gpsLat = pos.latitude; _gpsLng = pos.longitude; });
    }
  }

  Future<void> _submit() async {
    if (_region == '내 주변' && (_gpsLat == null || _gpsLng == null)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('위치를 가져오는 중입니다. 잠시 후 다시 시도해주세요.')),
      );
      return;
    }
    if (_needsHub && _selectedHub == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('대중교통 출발지를 선택해주세요.')),
      );
      return;
    }
    if (_isSpot && _textController.text.trim().isEmpty && _selectedTags.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('장소를 입력하거나 태그를 선택해주세요.')),
      );
      return;
    }
    if (!_isSpot && _selectedTags.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('태그를 하나 이상 선택해주세요.')),
      );
      return;
    }

    setState(() => _isLoading = true);
    try {
      final tags = _selectedTags.toList();
      final Map<String, dynamic>? res;

      if (_isSpot) {
        res = await ApiService.getSpotRecommendation(
          userText: _textController.text.trim(),
          transport: _transport,
          userLat: _effectiveLat!,
          userLng: _effectiveLng!,
          personaTags: tags,
          count: _resultCount,
        );
      } else {
        res = await ApiService.getCourseRecommendation(
          transport: _transport,
          userLat: _effectiveLat!,
          userLng: _effectiveLng!,
          personaTags: tags,
          count: _resultCount,
        );
      }

      if (!mounted) { return; }
      setState(() => _isLoading = false);

      if (res == null || res.containsKey('error')) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(res?['error'] ?? '서버 오류가 발생했습니다.')),
        );
        return;
      }

      final data = res['data'] as Map<String, dynamic>? ?? res;

      if (_isSpot) {
        Navigator.push(context, MaterialPageRoute(
          builder: (_) => SpotResultScreen(
            places: List<Map<String, dynamic>>.from(data['places']),
          ),
        ));
      } else {
        Navigator.push(context, MaterialPageRoute(
          builder: (_) => CourseResultScreen(
            courses: List<List<dynamic>>.from(
              (data['courses'] as List)
                  .map((c) => List<Map<String, dynamic>>.from(c)),
            ),
          ),
        ));
      }
    } catch (e) {
      if (!mounted) { return; }
      setState(() => _isLoading = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('오류: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFFF8F3),
      appBar: AppBar(
        backgroundColor: const Color(0xFFFFF8F3),
        elevation: 0,
        foregroundColor: const Color(0xFF1A1A1A),
        title: Text(_isSpot ? '지금 당장 뭘 할지' : '오늘 하루 뭘 할지'),
      ),
      body: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [

              // ── 1. 지역 선택 ──────────────────────────────────
              _sectionLabel('어디서 놀까요?'),
              const SizedBox(height: 10),
              _ChoiceRow(
                options: const ['내 주변', '천안', '아산'],
                selected: _region,
                themeColor: _themeColor,
                onSelect: (r) => setState(() {
                  _region = r;
                  _selectedHub = null; // 지역 바뀌면 허브 초기화
                }),
              ),

              const SizedBox(height: 20),

              // ── 2. 이동 수단 ──────────────────────────────────
              _sectionLabel('이동 수단'),
              const SizedBox(height: 10),
              _ChoiceRow(
                options: const ['대중교통/도보', '차'],
                selected: _transport,
                themeColor: _themeColor,
                onSelect: (t) => setState(() {
                  _transport = t;
                  _selectedHub = null; // 이동수단 바뀌면 허브 초기화
                }),
              ),

              // ── 3. 대중교통 출발지 (조건부) ───────────────────
              if (_needsHub) ...[
                const SizedBox(height: 20),
                _sectionLabel('어디서 출발할까요?'),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: (_kTransitHubs[_region] ?? []).map((hub) {
                    final name = hub['name'] as String;
                    final selected = _selectedHub == name;
                    return GestureDetector(
                      onTap: () => setState(() => _selectedHub = name),
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 150),
                        padding: const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 9),
                        decoration: BoxDecoration(
                          color: selected ? _themeColor : Colors.white,
                          borderRadius: BorderRadius.circular(22),
                          border: Border.all(
                            color: selected
                                ? _themeColor
                                : Colors.grey.shade300,
                          ),
                        ),
                        child: Text(
                          name,
                          style: TextStyle(
                            fontSize: 13,
                            color: selected
                                ? Colors.white
                                : Colors.grey.shade700,
                            fontWeight: selected
                                ? FontWeight.bold
                                : FontWeight.normal,
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ],

              const SizedBox(height: 20),

              // ── 4. 결과 개수 선택 ─────────────────────────────
              _sectionLabel(_isSpot ? '몇 곳을 추천받을까요?' : '코스를 몇 개 받을까요?'),
              const SizedBox(height: 10),
              Wrap(
                spacing: 10,
                runSpacing: 8,
                children: _countOptions.map((n) {
                  final selected = _resultCount == n;
                  return GestureDetector(
                    onTap: () => setState(() => _resultCount = n),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 150),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 20, vertical: 10),
                      decoration: BoxDecoration(
                        color: selected ? _themeColor : Colors.white,
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(
                          color: selected
                              ? _themeColor
                              : Colors.grey.shade300,
                        ),
                      ),
                      child: Text(
                        _isSpot ? '$n곳' : '$n개',
                        style: TextStyle(
                          color: selected
                              ? Colors.white
                              : Colors.grey.shade700,
                          fontWeight: selected
                              ? FontWeight.bold
                              : FontWeight.normal,
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),

              const SizedBox(height: 28),

              // ── 5. 텍스트 입력 + 태그 자동 선택 버튼 ────────────
              _sectionLabel(
                _isSpot ? '어떤 장소를 찾고 있나요?' : '어떤 날을 원하나요?',
              ),
              const SizedBox(height: 10),
              TextField(
                controller: _textController,
                maxLines: 2,
                decoration: InputDecoration(
                  hintText: _isSpot
                      ? '아래 태그 고르기 어려우면 적어보세요.\n예) 닭갈비, 조용한 카페, 산책로'
                      : '아래 태그 고르기 어려우면 적어보세요.\n예) 연인이랑 감성적인 하루, 가족과 조용한 나들이',
                  hintStyle:
                      TextStyle(color: Colors.grey.shade500, fontSize: 14),
                  filled: true,
                  fillColor: Colors.white,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: BorderSide.none,
                  ),
                  contentPadding: const EdgeInsets.all(16),
                ),
              ),
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton.icon(
                  onPressed: _isTagLoading ? null : _autoSuggestTags,
                  style: TextButton.styleFrom(
                    foregroundColor: _themeColor,
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 6),
                  ),
                  icon: _isTagLoading
                      ? SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: _themeColor),
                        )
                      : Icon(Icons.auto_awesome,
                          size: 16, color: _themeColor),
                  label: Text('태그 자동 선택',
                      style: TextStyle(fontSize: 13, color: _themeColor)),
                ),
              ),

              const SizedBox(height: 12),

              // ── 6. 페르소나 태그 ──────────────────────────────
              ..._kTagGroups.entries.map((entry) => _TagSection(
                    title: entry.key,
                    tags: entry.value,
                    selectedTags: _selectedTags,
                    themeColor: _themeColor,
                    onToggle: (tag) => setState(() {
                      if (_selectedTags.contains(tag)) {
                        _selectedTags.remove(tag);
                      } else {
                        _selectedTags.add(tag);
                      }
                    }),
                  )),

              const SizedBox(height: 20),

              // ── 6. 위치 상태 ──────────────────────────────────
              Row(
                children: [
                  Icon(
                    _locationReady ? Icons.location_on : Icons.location_searching,
                    size: 16,
                    color: _locationReady ? _themeColor : Colors.grey,
                  ),
                  const SizedBox(width: 6),
                  Text(
                    _locationLabel,
                    style: TextStyle(
                      fontSize: 13,
                      color: _locationReady ? _themeColor : Colors.grey,
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 40),

              // ── 7. 추천 버튼 ──────────────────────────────────
              SizedBox(
                width: double.infinity,
                height: 54,
                child: ElevatedButton(
                  onPressed: _isLoading ? null : _submit,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: _themeColor,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14)),
                    elevation: 0,
                  ),
                  child: _isLoading
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(
                              color: Colors.white, strokeWidth: 2.5),
                        )
                      : Text(
                          _isSpot ? '장소 추천받기' : '코스 추천받기',
                          style: const TextStyle(
                              fontSize: 17, fontWeight: FontWeight.bold),
                        ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _sectionLabel(String text) => Text(
        text,
        style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.bold,
            color: Color(0xFF1A1A1A)),
      );

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }
}

// ── 공통 선택 버튼 행 ──────────────────────────────────────────────
class _ChoiceRow extends StatelessWidget {
  final List<String> options;
  final String selected;
  final Color themeColor;
  final void Function(String) onSelect;

  const _ChoiceRow({
    required this.options,
    required this.selected,
    required this.themeColor,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: options.map((opt) {
        final isSelected = selected == opt;
        return Padding(
          padding: const EdgeInsets.only(right: 10),
          child: GestureDetector(
            onTap: () => onSelect(opt),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 150),
              padding:
                  const EdgeInsets.symmetric(horizontal: 22, vertical: 10),
              decoration: BoxDecoration(
                color: isSelected ? themeColor : Colors.white,
                borderRadius: BorderRadius.circular(24),
                border: Border.all(
                  color: isSelected ? themeColor : Colors.grey.shade300,
                ),
              ),
              child: Text(
                opt,
                style: TextStyle(
                  color: isSelected ? Colors.white : Colors.grey.shade700,
                  fontWeight:
                      isSelected ? FontWeight.bold : FontWeight.normal,
                ),
              ),
            ),
          ),
        );
      }).toList(),
    );
  }
}

// ── 태그 섹션 위젯 ─────────────────────────────────────────────────
class _TagSection extends StatelessWidget {
  final String title;
  final List<String> tags;
  final Set<String> selectedTags;
  final Color themeColor;
  final void Function(String) onToggle;

  const _TagSection({
    required this.title,
    required this.tags,
    required this.selectedTags,
    required this.themeColor,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: Color(0xFF555555),
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: tags.map((tag) {
              final selected = selectedTags.contains(tag);
              return GestureDetector(
                onTap: () => onToggle(tag),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  padding: const EdgeInsets.symmetric(
                      horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: selected ? themeColor : Colors.white,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: selected ? themeColor : Colors.grey.shade300,
                    ),
                  ),
                  child: Text(
                    tag,
                    style: TextStyle(
                      fontSize: 13,
                      color: selected ? Colors.white : Colors.grey.shade700,
                      fontWeight:
                          selected ? FontWeight.bold : FontWeight.normal,
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}
