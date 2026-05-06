import 'dart:async';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'api_service.dart';
import 'spot_result_screen.dart';
import 'course_result_screen.dart';

// ── 지역 중심 좌표 ──────────────────────────────────────────────
const Map<String, List<double>> _kRegionCenters = {
  '천안': [36.8151, 127.1139],
  '아산': [36.7898, 127.0043],
};

// ── 대중교통 출발 허브 ───────────────────────────────────────────
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

// ── 단일 선택 그룹 ('어떤 분위기'만 복수 선택) ──────────────────
const Set<String> _kSingleSelectGroups = {
  '누구와', '특별한 날', '실내 · 야외', '어떤 활동',
};

// ── 슬롯 타입 아이콘 / 색상 ─────────────────────────────────────
const Map<String, IconData> _kSlotIcons = {
  '음식':     Icons.restaurant,
  '카페':     Icons.local_cafe,
  '자연·산책': Icons.nature_people,
  '등산':     Icons.terrain,
  '문화·역사': Icons.account_balance,
  '쇼핑':    Icons.shopping_cart,
  '관광지':   Icons.place,
  '실내 오락': Icons.videogame_asset,
};

const Map<String, Color> _kSlotColors = {
  '음식':     Color(0xFFFF7043),
  '카페':     Color(0xFF795548),
  '자연·산책': Color(0xFF43A047),
  '등산':     Color(0xFF2E7D32),
  '문화·역사': Color(0xFF7B1FA2),
  '쇼핑':    Color(0xFFE91E63),
  '관광지':   Color(0xFF1976D2),
  '실내 오락': Color(0xFF5E35B1),
};

// ── 페르소나 태그 그룹 ───────────────────────────────────────────
const Map<String, List<String>> _kTagGroups = {
  '누구와': [
    '혼자', '친구와', '연인과', '부부끼리', '가족 나들이',
    '부모님 모시고', '아이와 함께', '유아/영아 동반',
    '단체/모임', '동아리/클럽', '회식', '소개팅/첫만남',
  ],
  '어떤 분위기': [
    '힐링/여유', '활동적인', '감성적인', '로맨틱한', '조용한',
    '트렌디한', '고급스러운', '아늑한', '이색적인',
    '자연 친화적', '소소한 일상', '설레는', '멋진 야경',
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
    '쇼핑', '자연/산책', '등산/트레킹',
    '사진 명소', '스포츠/레저', '체험 공방',
    '전통/한옥', '노래방/실내 오락',
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
  String  _region    = '내 주변';
  String  _transport = '대중교통';
  String? _selectedHub;
  int     _resultCount = 5;
  int     _spotCount   = 5;
  List<String> _slotTypes = [];
  bool    _isLoading    = false;
  bool    _isTagLoading = false;
  double? _gpsLat;
  double? _gpsLng;
  bool    _gpsPermissionDenied = false;
  int     _currentStep  = 0;

  final Set<String> _selectedTags = {};

  bool get _isSpot => widget.mode == 'spot';
  Color get _themeColor =>
      _isSpot ? const Color(0xFFFF7043) : const Color(0xFF26C6DA);

  bool get _needsHub =>
      _region != '내 주변' && _transport == '대중교통';

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

  List<String> _defaultTemplate(int n) {
    switch (n) {
      case 3: return ['음식', '자연·산책', '카페'];
      case 4: return ['음식', '자연·산책', '카페', '문화·역사'];
      default: return ['음식', '자연·산책', '카페', '문화·역사', '음식'];
    }
  }

  @override
  void initState() {
    super.initState();
    _resultCount = _isSpot ? 5 : 3;
    if (!_isSpot) _slotTypes = _defaultTemplate(_spotCount);
    _fetchLocation();
  }

  void _goNext() {
    if (_currentStep == 0 && _region == '내 주변' && _gpsPermissionDenied) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('위치 권한을 허용해야 현재 위치를 사용할 수 있어요.')),
      );
      return;
    }
    setState(() => _currentStep++);
  }

  void _goPrev() => setState(() => _currentStep--);

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
      if (!mounted) return;
      final allTags = _kTagGroups.values.expand((l) => l).toSet();
      final filtered = suggested.where(allTags.contains).toList();
      final toAdd = <String>[];
      for (final entry in _kTagGroups.entries) {
        final groupTags = entry.value.toSet();
        final hits = filtered.where(groupTags.contains).toList();
        if (_kSingleSelectGroups.contains(entry.key)) {
          if (hits.isNotEmpty) toAdd.add(hits.first);
        } else {
          toAdd.addAll(hits);
        }
      }
      setState(() {
        _selectedTags..clear()..addAll(toAdd);
        _isTagLoading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _isTagLoading = false);
    }
  }

  Future<void> _fetchLocation() async {
    LocationPermission perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      perm = await Geolocator.requestPermission();
    }
    if (perm == LocationPermission.deniedForever ||
        perm == LocationPermission.denied) {
      if (mounted) setState(() => _gpsPermissionDenied = true);
      return;
    }
    final pos = await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(accuracy: LocationAccuracy.high),
    );
    if (mounted) {
      setState(() { _gpsLat = pos.latitude; _gpsLng = pos.longitude; });
    }
  }

  Future<void> _submit() async {
    final whoTags = _kTagGroups['누구와']!.toSet();
    if (!_selectedTags.any(whoTags.contains)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('"누구와" 항목을 선택해주세요.')),
      );
      return;
    }
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

    setState(() => _isLoading = true);
    try {
      final tags = _selectedTags.toList();
      final Map<String, dynamic>? res;

      if (_isSpot) {
        res = await ApiService.getSpotRecommendation(
          userText: _textController.text.trim(),
          transport: _transport,
          region: _region,
          userLat: _effectiveLat!,
          userLng: _effectiveLng!,
          personaTags: tags,
          count: _resultCount,
        );
      } else {
        res = await ApiService.getCourseRecommendation(
          transport: _transport,
          region: _region,
          userLat: _effectiveLat!,
          userLng: _effectiveLng!,
          personaTags: tags,
          count: _resultCount,
          spotCount: _spotCount,
          slotTypes: _slotTypes,
        );
      }

      if (!mounted) return;
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
            requestedCount: _resultCount,
          ),
        ));
      } else {
        Navigator.push(context, MaterialPageRoute(
          builder: (_) => CourseResultScreen(
            courses: List<List<dynamic>>.from(
              (data['courses'] as List)
                  .map((c) => List<Map<String, dynamic>>.from(c)),
            ),
            requestedCount: _resultCount,
            region: _region,
          ),
        ));
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _isLoading = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('오류: $e')));
    }
  }

  // ── 빌드 ──────────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: _currentStep == 0,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _goPrev();
      },
      child: Scaffold(
      backgroundColor: const Color(0xFFFFF8F3),
      appBar: AppBar(
        backgroundColor: const Color(0xFFFFF8F3),
        elevation: 0,
        foregroundColor: const Color(0xFF1A1A1A),
        title: Text(_isSpot ? '스팟 추천' : '코스 추천'),
        leading: _currentStep > 0
            ? IconButton(
                icon: const Icon(Icons.arrow_back),
                onPressed: _goPrev,
              )
            : null,
      ),
      body: Column(
        children: [
          _buildStepIndicator(),
          Expanded(
            child: GestureDetector(
              onTap: () => FocusScope.of(context).unfocus(),
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 220),
                layoutBuilder: (child, previousChildren) => Stack(
                  alignment: Alignment.topCenter,
                  children: [...previousChildren, if (child != null) child],
                ),
                transitionBuilder: (child, animation) => FadeTransition(
                  opacity: animation,
                  child: child,
                ),
                child: SingleChildScrollView(
                  key: ValueKey(_currentStep),
                  padding: const EdgeInsets.fromLTRB(24, 8, 24, 16),
                  child: _buildCurrentStep(),
                ),
              ),
            ),
          ),
          _buildNavButtons(),
        ],
      ),
    ));
  }

  // ── 스텝 인디케이터 ────────────────────────────────────────────
  Widget _buildStepIndicator() {
    final labels = _isSpot ? const ['기본 설정', '취향'] : const ['기본 설정', '취향', '코스 구성'];
    return Container(
      padding: const EdgeInsets.fromLTRB(32, 10, 32, 8),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF8F3),
        border: Border(bottom: BorderSide(color: Colors.grey.shade200)),
      ),
      child: Row(
        children: [
          for (int i = 0; i < labels.length; i++) ...[
            if (i > 0)
              Expanded(
                child: Container(
                  height: 1.5,
                  margin: const EdgeInsets.only(bottom: 22),
                  color: i <= _currentStep ? _themeColor : Colors.grey.shade300,
                ),
              ),
            _StepDot(
              index: i,
              label: labels[i],
              currentStep: _currentStep,
              themeColor: _themeColor,
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildCurrentStep() {
    switch (_currentStep) {
      case 0: return _buildStep1();
      case 1: return _buildStep2();
      case 2: return _buildStep3();
      default: return const SizedBox();
    }
  }

  // ── Step 1: 기본 설정 ──────────────────────────────────────────
  Widget _buildStep1() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _label('어디서 놀까요?'),
        const SizedBox(height: 10),
        _ChoiceRow(
          options: const ['내 주변', '천안', '아산'],
          selected: _region,
          themeColor: _themeColor,
          onSelect: (r) => setState(() { _region = r; _selectedHub = null; }),
        ),
        if (_region == '내 주변' && _gpsPermissionDenied) ...[
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: const Color(0xFFFFF3E0),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: const Color(0xFFFFCC80)),
            ),
            child: Row(
              children: [
                const Icon(Icons.location_off, size: 16, color: Color(0xFFFF8F00)),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text(
                    '위치 권한이 거부되었어요. 설정에서 허용하거나 지역을 직접 선택해주세요.',
                    style: TextStyle(fontSize: 13, color: Color(0xFF795548)),
                  ),
                ),
              ],
            ),
          ),
        ],
        const SizedBox(height: 28),
        _label('이동 수단'),
        const SizedBox(height: 10),
        _ChoiceRow(
          options: const ['대중교통', '차'],
          selected: _transport,
          themeColor: _themeColor,
          onSelect: (t) => setState(() { _transport = t; _selectedHub = null; }),
        ),
        if (_needsHub) ...[
          const SizedBox(height: 28),
          _label('어디서 출발할까요?'),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: (_kTransitHubs[_region] ?? []).map((hub) {
              final name = hub['name'] as String;
              final sel  = _selectedHub == name;
              return GestureDetector(
                onTap: () => setState(() => _selectedHub = name),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
                  decoration: BoxDecoration(
                    color: sel ? _themeColor : Colors.white,
                    borderRadius: BorderRadius.circular(22),
                    border: Border.all(color: sel ? _themeColor : Colors.grey.shade300),
                  ),
                  child: Text(name,
                    style: TextStyle(
                      fontSize: 13,
                      color: sel ? Colors.white : Colors.grey.shade700,
                      fontWeight: sel ? FontWeight.bold : FontWeight.normal,
                    )),
                ),
              );
            }).toList(),
          ),
        ],
        const SizedBox(height: 28),
        _label(_isSpot ? '몇 곳을 추천받을까요?' : '코스를 몇 개 받을까요?'),
        const SizedBox(height: 10),
        Wrap(
          spacing: 10,
          runSpacing: 8,
          children: _countOptions.map((n) {
            final sel = _resultCount == n;
            return GestureDetector(
              onTap: () => setState(() => _resultCount = n),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 150),
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                decoration: BoxDecoration(
                  color: sel ? _themeColor : Colors.white,
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(color: sel ? _themeColor : Colors.grey.shade300),
                ),
                child: Text(_isSpot ? '$n곳' : '$n개',
                  style: TextStyle(
                    color: sel ? Colors.white : Colors.grey.shade700,
                    fontWeight: sel ? FontWeight.bold : FontWeight.normal,
                  )),
              ),
            );
          }).toList(),
        ),
        if (!_isSpot) ...[
          const SizedBox(height: 28),
          _label('코스당 몇 곳을 돌까요?'),
          const SizedBox(height: 10),
          Wrap(
            spacing: 10,
            runSpacing: 8,
            children: [3, 4, 5].map((n) {
              final sel = _spotCount == n;
              return GestureDetector(
                onTap: () => setState(() { _spotCount = n; _slotTypes = _defaultTemplate(n); }),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                  decoration: BoxDecoration(
                    color: sel ? _themeColor : Colors.white,
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(color: sel ? _themeColor : Colors.grey.shade300),
                  ),
                  child: Text('$n곳',
                    style: TextStyle(
                      color: sel ? Colors.white : Colors.grey.shade700,
                      fontWeight: sel ? FontWeight.bold : FontWeight.normal,
                    )),
                ),
              );
            }).toList(),
          ),
        ],
        const SizedBox(height: 20),
        Row(
          children: [
            Icon(
              _locationReady ? Icons.location_on : Icons.location_searching,
              size: 15,
              color: _locationReady ? _themeColor : Colors.grey.shade400,
            ),
            const SizedBox(width: 6),
            Text(_locationLabel,
              style: TextStyle(
                fontSize: 13,
                color: _locationReady ? _themeColor : Colors.grey.shade400,
              )),
          ],
        ),
        const SizedBox(height: 8),
      ],
    );
  }

  // ── Step 2: 취향 (누구와 + 기타 태그 + 텍스트 입력) ──────────────
  Widget _buildStep2() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _label(_isSpot ? '어떤 장소를 찾고 있나요?' : '어떤 날을 원하나요?'),
        const SizedBox(height: 10),
        TextField(
          controller: _textController,
          maxLines: 2,
          decoration: InputDecoration(
            hintText: _isSpot
                ? '자유롭게 적으면 AI가 태그를 골라줄게요.\n예) 친구랑 맛집 탐방, 연인과 감성 카페'
                : '자유롭게 적으면 AI가 태그를 골라줄게요.\n예) 연인이랑 감성적인 하루, 가족과 조용한 나들이',
            hintStyle: TextStyle(color: Colors.grey.shade400, fontSize: 14),
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
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            ),
            icon: _isTagLoading
                ? SizedBox(
                    width: 14, height: 14,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: _themeColor))
                : Icon(Icons.auto_awesome, size: 16, color: _themeColor),
            label: Text('AI 태그 자동 선택',
                style: TextStyle(fontSize: 13, color: _themeColor)),
          ),
        ),
        const SizedBox(height: 8),
        ..._kTagGroups.entries
          .where((e) => _isSpot || (e.key != '어떤 활동' && e.key != '실내 · 야외'))
          .map((entry) {
          final isSingle = _kSingleSelectGroups.contains(entry.key);
          String? hint;
          if (entry.key == '누구와') hint = '필수 선택';
          if (entry.key == '어떤 분위기') hint = '복수 선택 가능';
          return _TagSection(
            title: entry.key,
            tags: entry.value,
            selectedTags: _selectedTags,
            themeColor: _themeColor,
            singleSelect: isSingle,
            hint: hint,
            onToggle: (tag) => setState(() {
              if (_selectedTags.contains(tag)) {
                _selectedTags.remove(tag);
              } else {
                if (isSingle) _selectedTags.removeAll(entry.value);
                _selectedTags.add(tag);
              }
            }),
          );
        }),
        const SizedBox(height: 8),
      ],
    );
  }

  // ── Step 3: 코스 구성 (코스 모드 전용) ────────────────────────────
  Widget _buildStep3() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _label('어떤 순서로 놀까요?'),
        const SizedBox(height: 6),
        Text(
          '각 슬롯을 탭해서 원하는 활동으로 바꿀 수 있어요.',
          style: TextStyle(fontSize: 13, color: Colors.grey.shade500),
        ),
        const SizedBox(height: 28),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (int i = 0; i < _slotTypes.length; i++) ...[
                if (i > 0)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    child: Icon(Icons.arrow_forward_ios,
                        size: 12, color: Colors.grey.shade400),
                  ),
                _SlotChip(
                  slotType: _slotTypes[i],
                  onTap: () => _showSlotPicker(i),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 20),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton.icon(
            onPressed: () => setState(() => _slotTypes = _defaultTemplate(_spotCount)),
            style: TextButton.styleFrom(
              foregroundColor: Colors.grey.shade500,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            ),
            icon: Icon(Icons.refresh, size: 14, color: Colors.grey.shade400),
            label: Text('기본값으로 초기화',
                style: TextStyle(fontSize: 12, color: Colors.grey.shade500)),
          ),
        ),
        const SizedBox(height: 8),
      ],
    );
  }

  void _showSlotPicker(int index) {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => Padding(
        padding: const EdgeInsets.fromLTRB(24, 20, 24, 36),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${index + 1}번째 장소에서 뭘 할까요?',
                style: const TextStyle(
                    fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 16),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: _kSlotIcons.keys.map((type) {
                final isSel = _slotTypes[index] == type;
                final color = _kSlotColors[type]!;
                return GestureDetector(
                  onTap: () {
                    setState(() => _slotTypes[index] = type);
                    Navigator.pop(context);
                  },
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 150),
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: isSel ? color : Colors.white,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                          color: isSel ? color : Colors.grey.shade300),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(_kSlotIcons[type]!,
                            size: 14,
                            color: isSel ? Colors.white : color),
                        const SizedBox(width: 6),
                        Text(type,
                            style: TextStyle(
                              fontSize: 13,
                              color: isSel
                                  ? Colors.white
                                  : Colors.grey.shade700,
                              fontWeight: isSel
                                  ? FontWeight.bold
                                  : FontWeight.normal,
                            )),
                      ],
                    ),
                  ),
                );
              }).toList(),
            ),
          ],
        ),
      ),
    );
  }

  // ── 하단 버튼 ──────────────────────────────────────────────────
  Widget _buildNavButtons() {
    final bottomPad = MediaQuery.of(context).padding.bottom;
    return Container(
      padding: EdgeInsets.fromLTRB(24, 12, 24, 12 + bottomPad),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF8F3),
        border: Border(top: BorderSide(color: Colors.grey.shade200)),
      ),
      child: Row(
        children: [
          if (_currentStep > 0) ...[
            Expanded(
              child: OutlinedButton(
                onPressed: _goPrev,
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.grey.shade700,
                  side: BorderSide(color: Colors.grey.shade300),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14)),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
                child: const Text('이전', style: TextStyle(fontSize: 15)),
              ),
            ),
            const SizedBox(width: 12),
          ],
          Expanded(
            flex: 2,
            child: ElevatedButton(
              onPressed: _currentStep < (_isSpot ? 1 : 2)
                  ? _goNext
                  : (_isLoading ? null : _submit),
              style: ElevatedButton.styleFrom(
                backgroundColor: _themeColor,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14)),
                elevation: 0,
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
              child: _isLoading
                  ? const SizedBox(
                      width: 22, height: 22,
                      child: CircularProgressIndicator(
                          color: Colors.white, strokeWidth: 2.5))
                  : Text(
                      _currentStep < (_isSpot ? 1 : 2)
                          ? '다음'
                          : (_isSpot ? '장소 추천받기' : '코스 추천받기'),
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.bold),
                    ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _label(String text) => Text(text,
      style: const TextStyle(
          fontSize: 16, fontWeight: FontWeight.bold,
          color: Color(0xFF1A1A1A)));

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }
}

// ── 스텝 도트 ──────────────────────────────────────────────────
class _StepDot extends StatelessWidget {
  final int index;
  final String label;
  final int currentStep;
  final Color themeColor;

  const _StepDot({
    required this.index,
    required this.label,
    required this.currentStep,
    required this.themeColor,
  });

  @override
  Widget build(BuildContext context) {
    final isDone   = index < currentStep;
    final isActive = index == currentStep;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          width: 30, height: 30,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: isDone || isActive ? themeColor : Colors.white,
            border: Border.all(
              color: isDone || isActive ? themeColor : Colors.grey.shade300,
              width: 1.5,
            ),
          ),
          child: Center(
            child: isDone
                ? const Icon(Icons.check, size: 14, color: Colors.white)
                : Text('${index + 1}',
                    style: TextStyle(
                      fontSize: 12, fontWeight: FontWeight.bold,
                      color: isActive ? Colors.white : Colors.grey.shade400,
                    )),
          ),
        ),
        const SizedBox(height: 4),
        Text(label,
          style: TextStyle(
            fontSize: 11,
            color: isActive
                ? themeColor
                : isDone
                    ? Colors.grey.shade500
                    : Colors.grey.shade400,
            fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
          )),
      ],
    );
  }
}

// ── 공통 선택 버튼 행 ──────────────────────────────────────────
class _ChoiceRow extends StatelessWidget {
  final List<String> options;
  final String? selected;
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
        final isSel = selected != null && selected == opt;
        return Padding(
          padding: const EdgeInsets.only(right: 10),
          child: GestureDetector(
            onTap: () => onSelect(opt),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 150),
              padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 10),
              decoration: BoxDecoration(
                color: isSel ? themeColor : Colors.white,
                borderRadius: BorderRadius.circular(24),
                border: Border.all(
                    color: isSel ? themeColor : Colors.grey.shade300),
              ),
              child: Text(opt,
                style: TextStyle(
                  color: isSel ? Colors.white : Colors.grey.shade700,
                  fontWeight: isSel ? FontWeight.bold : FontWeight.normal,
                )),
            ),
          ),
        );
      }).toList(),
    );
  }
}

// ── 태그 섹션 위젯 ─────────────────────────────────────────────
class _TagSection extends StatelessWidget {
  final String title;
  final List<String> tags;
  final Set<String> selectedTags;
  final Color themeColor;
  final bool singleSelect;
  final String? hint;
  final void Function(String) onToggle;

  const _TagSection({
    required this.title,
    required this.tags,
    required this.selectedTags,
    required this.themeColor,
    required this.onToggle,
    this.singleSelect = false,
    this.hint,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(title,
                style: const TextStyle(
                  fontSize: 14, fontWeight: FontWeight.w600,
                  color: Color(0xFF555555),
                )),
              if (hint != null) ...[
                const SizedBox(width: 6),
                Text(hint!,
                  style: const TextStyle(
                      fontSize: 11, color: Color(0xFFFF7043))),
              ],
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: tags.map((tag) {
              final sel = selectedTags.contains(tag);
              return GestureDetector(
                onTap: () => onToggle(tag),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  padding: const EdgeInsets.symmetric(
                      horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: sel ? themeColor : Colors.white,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                        color: sel ? themeColor : Colors.grey.shade300),
                  ),
                  child: Text(tag,
                    style: TextStyle(
                      fontSize: 13,
                      color: sel ? Colors.white : Colors.grey.shade700,
                      fontWeight: sel ? FontWeight.bold : FontWeight.normal,
                    )),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}

// ── 슬롯 칩 위젯 ───────────────────────────────────────────────
class _SlotChip extends StatelessWidget {
  final String slotType;
  final VoidCallback onTap;

  const _SlotChip({required this.slotType, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final icon  = _kSlotIcons[slotType]  ?? Icons.place;
    final color = _kSlotColors[slotType] ?? const Color(0xFF607D8B);
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 76,
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 6),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: color.withValues(alpha: 0.5)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: 24),
            const SizedBox(height: 7),
            Text(
              slotType,
              style: TextStyle(
                  fontSize: 10,
                  color: color,
                  fontWeight: FontWeight.bold),
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }
}
