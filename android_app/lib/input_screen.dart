import 'package:flutter/material.dart';
import 'location_service.dart';
import 'activity_choice_dialog.dart';
import 'service_region_dialog.dart';
import 'transit_hubs.dart';
import 'recommendation_source.dart';
import 'network/tag_suggestion_exception.dart';
import 'travel_data.dart';
import 'network/request_cancellation.dart';
import 'course_shortage.dart';
import 'result_actions.dart';
import 'result_notice.dart';

import 'spot_result_screen.dart';
import 'course_result_screen.dart';

part 'input_options.dart';
part 'input_widgets.dart';

class InputScreen extends StatefulWidget {
  final String mode; // 'spot' | 'course'
  final RecommendationSource source;
  final LocationSource? locationSource;
  const InputScreen({
    super.key,
    required this.mode,
    this.source = const ApiRecommendationSource(),
    this.locationSource,
  });

  @override
  State<InputScreen> createState() => _InputScreenState();
}

class _InputScreenState extends State<InputScreen> {
  final _textController = TextEditingController();
  final _formScrollController = ScrollController();
  String? _recommendationError;
  String _region = '내 주변';
  String _transport = '대중교통';
  String? _selectedHub;
  int _resultCount = 5;
  int _spotCount = 3;
  List<String> _slotTypes = [];
  bool _isLoading = false;
  bool _isTagLoading = false;
  double? _gpsLat;
  double? _gpsLng;
  String? _locationError;
  bool _locationLoading = false;
  int _locationRevision = 0;
  late final LocationSource _locationSource;
  int _requestRevision = 0;
  int _tagRevision = 0;
  int _currentStep = 0;
  int? _tagQuestion;
  String _lastObservedText = '';
  bool _usingFallbackOrigin = false;
  List<String> _recentPlaceIds = [];
  RequestCancellation? _cancellation;
  Widget? _lastResults;
  String? _lastResultActivity;
  VoidCallback? _restoreLastResultControls;

  final Set<String> _selectedTags = {};

  bool get _isSpot => widget.mode == 'spot';
  Color get _themeColor =>
      _isSpot ? const Color(0xFFFF7043) : const Color(0xFF26C6DA);

  bool get _needsHub =>
      _region != '내 주변' && _transport == '대중교통' && !_usingFallbackOrigin;

  LocationFix? get _origin {
    if (_region == '내 주변') {
      return _gpsLat != null && _gpsLng != null
          ? LocationFix(_gpsLat!, _gpsLng!)
          : null;
    }
    if (_needsHub) {
      for (final hub in _kTransitHubs[_region] ?? <TransitHub>[]) {
        if (hub.name == _selectedHub) return hub;
      }
      return null;
    }
    return _kRegionCenters[_region];
  }

  String get _locationLabel {
    if (_region == '내 주변') {
      return _gpsLat != null
          ? '현재 위치 확인됨'
          : (_locationLoading ? '위치 가져오는 중...' : '위치를 확인해주세요');
    }
    if (_needsHub && _selectedHub != null) return _selectedHub!;
    if (!_needsHub) return '$_region 중심 출발';
    return '$_region — 출발지를 선택해주세요';
  }

  bool get _locationReady {
    return _origin != null;
  }

  List<int> get _countOptions => _isSpot ? [3, 5, 7, 10] : [1, 2, 3, 4, 5];

  List<String> _defaultTemplate(int count) =>
      _kDefaultCourse.take(count).toList();

  @override
  void initState() {
    super.initState();
    _resultCount = _isSpot ? 5 : 3;
    if (!_isSpot) _slotTypes = _defaultTemplate(_spotCount);
    _textController.addListener(_onTextChanged);
    _locationSource = widget.locationSource ?? DeviceLocationSource();
    _fetchLocation();
  }

  void _onTextChanged() {
    // IMEs also notify for cursor and composing changes. Only a new sentence
    // invalidates a pending suggestion or an approval dialog.
    if (_lastObservedText == _textController.text) return;
    _lastObservedText = _textController.text;
    _recentPlaceIds = [];
    _invalidateTags();
  }

  void _invalidateTags() {
    _tagRevision++;
    if (_isTagLoading && mounted) setState(() => _isTagLoading = false);
  }

  void _goNext() {
    if (_isLoading) return;
    if (_currentStep == 0 && !_locationReady) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _locationError ??
                (_needsHub ? '대중교통 출발지를 선택해주세요.' : '위치를 확인하거나 지역을 직접 선택해주세요.'),
          ),
        ),
      );
      return;
    }
    FocusScope.of(context).unfocus();
    setState(() {
      if (_currentStep == 1 && _tagQuestion != null) {
        if (_tagQuestion! < _visibleTagGroups.length - 1) {
          _tagQuestion = _tagQuestion! + 1;
        } else {
          _tagQuestion = null;
        }
      } else {
        _currentStep++;
      }
    });
  }

  void _goPrev() {
    _cancellation?.cancel();
    _requestRevision++;
    _invalidateTags();
    setState(() {
      _isLoading = false;
      if (_currentStep == 1 && _tagQuestion != null) {
        _tagQuestion = _tagQuestion! > 0 ? _tagQuestion! - 1 : null;
      } else if (_currentStep > 0) {
        _currentStep--;
      }
    });
  }

  Future<void> _autoSuggestTags() async {
    if (_isTagLoading || _isLoading) return;
    final text = _textController.text.trim();
    if (text.isEmpty) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('텍스트를 먼저 입력해주세요.')));
      return;
    }
    final revision = ++_tagRevision;
    setState(() => _isTagLoading = true);
    try {
      final suggested = await widget.source.suggestTags(text);
      if (!mounted ||
          revision != _tagRevision ||
          _textController.text.trim() != text) {
        return;
      }
      final allTags = _kTagGroups.values.expand((l) => l).toSet();
      final filtered = suggested.where(allTags.contains).toList();
      final toAdd = <String>[];
      for (final entry in _visibleTagGroups) {
        final groupTags = entry.value.toSet();
        final hits = filtered.where(groupTags.contains).toList();
        if (_kSingleSelectGroups.contains(entry.key)) {
          if (hits.isNotEmpty) toAdd.add(hits.first);
        } else {
          toAdd.addAll(hits);
        }
      }
      if (toAdd.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('선택할 태그를 찾지 못했어요. 직접 선택하거나 다시 시도해주세요.')),
        );
        return;
      }
      final nextTags = toAdd.toSet();
      if (_selectedTags.isNotEmpty &&
          (!_selectedTags.containsAll(nextTags) ||
              !nextTags.containsAll(_selectedTags))) {
        final changes = <String>[];
        for (final group in _visibleTagGroups) {
          String values(Set<String> tags) {
            final selected = group.value.where(tags.contains);
            return selected.isEmpty
                ? '없음'
                : selected
                      .map((tag) => _kActivityTagLabels[tag] ?? tag)
                      .join(', ');
          }

          final before = values(_selectedTags), after = values(nextTags);
          if (before != after) {
            final label = switch (group.key) {
              '누구와' => '동행',
              '어떤 분위기' => '분위기',
              '어떤 활동' => '활동',
              _ => group.key,
            };
            changes.add('$label: $before → $after');
          }
        }

        setState(() => _isTagLoading = false);
        final accepted = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('선택을 이렇게 바꿀까요?'),
            scrollable: true,
            content: Text(changes.join('\n\n')),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('유지하기'),
              ),
              TextButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('변경 적용'),
              ),
            ],
          ),
        );
        if (!mounted ||
            revision != _tagRevision ||
            _textController.text.trim() != text ||
            accepted != true) {
          return;
        }
      }
      _changeControls(() {
        _selectedTags
          ..clear()
          ..addAll(toAdd);
        _isTagLoading = false;
      });
    } catch (error) {
      if (!mounted || revision != _tagRevision) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            error is TagSuggestionException
                ? error.message
                : '태그를 가져오지 못했어요. 다시 시도해주세요.',
          ),
        ),
      );
    } finally {
      if (mounted && revision == _tagRevision) {
        setState(() => _isTagLoading = false);
      }
    }
  }

  Iterable<MapEntry<String, List<String>>> get _visibleTagGroups =>
      _kTagGroups.entries.where((e) => _isSpot || e.key != '어떤 활동');

  Future<void> _fetchLocation() async {
    if (_locationLoading) return;
    final revision = ++_locationRevision;
    setState(() {
      _locationLoading = true;
      _recommendationError = null;
      _locationError = null;
      _gpsLat = null;
      _gpsLng = null;
    });
    try {
      final fix = await _locationSource.locate();
      if (!mounted || revision != _locationRevision) return;
      setState(() {
        _gpsLat = fix.lat;
        _gpsLng = fix.lng;
      });
    } catch (error) {
      if (!mounted || revision != _locationRevision) return;
      setState(
        () => _locationError = error is LocationException
            ? error.message
            : const LocationException(LocationFailure.unavailable).message,
      );
    } finally {
      if (mounted && revision == _locationRevision) {
        setState(() => _locationLoading = false);
      }
    }
  }

  bool _isInServiceArea(double lat, double lng) =>
      lat >= 36.55 && lat <= 37.05 && lng >= 126.80 && lng <= 127.35;

  void _changeControls(VoidCallback change) => setState(() {
    change();
    _recentPlaceIds = [];
    _recommendationError = null;
  });

  void _showRecommendationError(String message) {
    setState(() => _recommendationError = message);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _formScrollController.hasClients) {
        _formScrollController.jumpTo(0);
      }
    });
  }

  Future<void> _submit({String? repeatedActivity}) async {
    if (_isLoading || _isTagLoading) return;
    // Clear the input focus history before a dialog can restore it on close.
    FocusScope.of(context).unfocus();
    final whoTags = _kTagGroups['누구와']!.toSet();
    if (!_selectedTags.any(whoTags.contains) &&
        _textController.text.trim().isEmpty) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('문장을 적거나 동행을 선택해주세요.')));
      _openTagQuestion(0);
      return;
    }
    if (_region == '내 주변' && (_gpsLat == null || _gpsLng == null)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('위치를 가져오는 중입니다. 잠시 후 다시 시도해주세요.')),
      );
      return;
    }
    if (_needsHub && _selectedHub == null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('대중교통 출발지를 선택해주세요.')));
      return;
    }
    final revision = ++_requestRevision;
    _cancellation?.cancel();
    _cancellation = RequestCancellation();
    setState(() {
      _isLoading = true;
      _recommendationError = null;
    });
    _invalidateTags();
    try {
      double? effectiveLat = _origin?.lat;
      double? effectiveLng = _origin?.lng;
      if (_region == '내 주변' && effectiveLat != null && effectiveLng != null) {
        if (!_isInServiceArea(effectiveLat, effectiveLng)) {
          if (!mounted) return;
          final proceed = await showDialog<bool>(
            context: context,
            builder: (_) => const ServiceRegionDialog(),
          );
          if (!mounted || revision != _requestRevision || proceed != true) {
            return;
          }
          effectiveLat = 36.8151;
          effectiveLng = 127.1139;
          _changeControls(() {
            _region = '천안';
            _selectedHub = null;
            _usingFallbackOrigin = true;
          });
        }
      }

      var request = RecommendationRequest(
        mode: widget.mode,
        userText: _textController.text.trim(),
        transport: _transport,
        region: _region,
        lat: effectiveLat!,
        lng: effectiveLng!,
        tags: _selectedTags.toList(),
        count: _resultCount,
        slotTypes: _slotTypes,
        naturalPlan: false,
        recentPlaceIds: _recentPlaceIds,
        cancellation: _cancellation,
      );
      if (request.userText.isNotEmpty &&
          widget.source is IntentRecommendationSource) {
        final intentSource = widget.source as IntentRecommendationSource;
        var response = await intentSource.interpret(request);
        if (!mounted || revision != _requestRevision) return;
        final initial = response == null || response.containsKey('error')
            ? null
            : jsonObject(response['data'] ?? response);
        if (initial?['clarification_required'] == true) {
          final clarification = jsonObject(initial!['clarification']);
          final canRepeat =
              repeatedActivity != null &&
              jsonObjects(
                clarification['options'],
              ).any((option) => option['value'] == repeatedActivity);
          final choice = canRepeat
              ? repeatedActivity
              : await _chooseActivity(clarification);
          if (!mounted || revision != _requestRevision) return;
          if (choice == null) {
            setState(() => _currentStep = 1);
            return;
          }
          request = request.clarified(
            activity: choice,
            token: clarification['token'] as String,
          );
          response = await intentSource.interpret(request);
          if (!mounted || revision != _requestRevision) return;
          final repeated = response == null || response.containsKey('error')
              ? null
              : jsonObject(response['data'] ?? response);
          if (repeated?['clarification_required'] == true) {
            _showRecommendationError(
              '고른 활동으로 요청을 확정하지 못했어요. 문장을 수정하거나 활동을 다시 선택해주세요.',
            );
            setState(() => _currentStep = 1);
            return;
          }
        }
        if (response == null || response.containsKey('error')) {
          _showRecommendationError(
            '${response?['error'] ?? '여행 문장을 해석하지 못했어요.'}',
          );
          return;
        }
        final preview = jsonObject(response['data'] ?? response);
        final plan = jsonObject(preview['travel_request']);
        final issues = [
          ...(plan['ambiguities'] as List? ?? []),
          ...(plan['unsupported'] as List? ?? []),
        ];
        final switchMode = preview['mode_switch_required'] == true;
        // A complete request proceeds directly. Only ask when the user must
        // resolve an ambiguity or choose a different recommendation mode.
        if (issues.isNotEmpty || switchMode) {
          final approved = await _resolveIntent(issues);
          if (!mounted || revision != _requestRevision) return;
          if (!approved) {
            setState(() => _currentStep = 1);
            return;
          }
        }
        request = request.reviewed(
          token: preview['intent_token'] as String,
          targetMode: preview['target_mode'] as String,
          targetCount: preview['target_count'] as int,
        );
      }
      var res = await widget.source.recommend(request);
      if (!mounted || revision != _requestRevision) return;
      if (res?['reason'] == 'unverified_conditions') {
        final metadata = jsonObject(res?['metadata'] ?? {});
        final labels = (metadata['unverified_conditions'] as List? ?? [])
            .whereType<Map>()
            .map((c) => c['label'])
            .join(', ');
        final approved =
            await showDialog<bool>(
              context: context,
              builder: (context) => AlertDialog(
                title: const Text('조건을 바꿔볼까요?'),
                content: Text(
                  labels.isEmpty
                      ? '일부 조건을 제외하고 다시 찾아볼까요?'
                      : '$labels 조건을 제외하고 다시 찾아볼까요?',
                ),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(context, false),
                    child: const Text('조건 유지'),
                  ),
                  TextButton(
                    onPressed: () => Navigator.pop(context, true),
                    child: const Text('다시 찾기'),
                  ),
                ],
              ),
            ) ??
            false;
        if (!mounted || revision != _requestRevision) return;
        if (!approved) {
          setState(() => _currentStep = 1);
          return;
        }
        request = request.reviewed(
          token: request.intentToken!,
          unverified: true,
        );
        res = await widget.source.recommend(request);
      }
      if (!mounted || revision != _requestRevision) return;

      if (res == null || res.containsKey('error')) {
        final shortage = CourseShortage.fromResponse(
          res,
          request,
          labels: _kSlotLabels,
        );
        if (shortage != null) {
          final action = await showDialog<String>(
            context: context,
            builder: (context) => AlertDialog(
              title: Text(shortage.title),
              content: SingleChildScrollView(child: Text(shortage.message)),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('닫기'),
                ),
                TextButton(
                  onPressed: () => Navigator.pop(context, 'location'),
                  child: const Text('출발점·교통 수정'),
                ),
                TextButton(
                  onPressed: () => Navigator.pop(context, 'activity'),
                  child: Text(_isSpot ? '문장 수정' : '방문 순서 수정'),
                ),
              ],
            ),
          );
          if (!mounted || revision != _requestRevision) return;
          if (action != null) {
            setState(
              () => _currentStep = action == 'location'
                  ? 0
                  : (!_isSpot && !request.naturalPlan
                        ? 2
                        : (request.userText.isNotEmpty || _isSpot ? 1 : 2)),
            );
          }
          return;
        }
        _showRecommendationError('${res?['error'] ?? '서버 오류가 발생했습니다.'}');
        return;
      }

      final data = RecommendationData.fromJson(res);

      if (request.mode == 'spot') {
        final places = data.places;
        _openResults(
          SpotResultScreen(
            places: places,
            sameAsPrevious:
                _lastResults is SpotResultScreen &&
                samePlaceComposition(
                  places,
                  (_lastResults as SpotResultScreen).places,
                ),
            requestedCount: request.count,
            metadata: data.metadata,
          ),
          revision,
          activityChoice: request.activityChoice,
        );
      } else {
        final courses = data.courses;
        final metadata = data.metadata;
        final metrics = data.courseMetrics;
        _openResults(
          CourseResultScreen(
            courses: courses,
            sameAsPrevious:
                _lastResults is CourseResultScreen &&
                sameCourseComposition(
                  courses,
                  (_lastResults as CourseResultScreen).courses
                      .map(jsonObjects)
                      .toList(),
                ),
            requestedCount: request.count,
            region: request.region,
            metadata: metadata,
            courseMetrics: metrics,
            transport: request.transport,
          ),
          revision,
          activityChoice: request.activityChoice,
        );
      }
    } catch (_) {
      if (!mounted || revision != _requestRevision) return;
      _showRecommendationError('추천 결과를 불러오지 못했어요. 다시 시도해주세요.');
    } finally {
      if (mounted && revision == _requestRevision) {
        setState(() => _isLoading = false);
      }
    }
  }

  VoidCallback _captureResultControls() {
    final form = (
      text: _textController.text,
      region: _region,
      transport: _transport,
      hub: _selectedHub,
      count: _resultCount,
      spotCount: _spotCount,
      slots: List<String>.from(_slotTypes),
      tags: Set<String>.from(_selectedTags),
      fallback: _usingFallbackOrigin,
      lat: _gpsLat,
      lng: _gpsLng,
    );
    return () => _changeControls(() {
      _textController.text = form.text;
      _region = form.region;
      _transport = form.transport;
      _selectedHub = form.hub;
      _resultCount = form.count;
      _spotCount = form.spotCount;
      _slotTypes = List<String>.from(form.slots);
      _selectedTags
        ..clear()
        ..addAll(form.tags);
      _usingFallbackOrigin = form.fallback;
      _tagQuestion = null;
      _gpsLat = form.lat;
      _gpsLng = form.lng;
    });
  }

  void _openResults(
    Widget screen,
    int revision, {
    VoidCallback? restoreControls,
    String? activityChoice,
  }) {
    final restore = restoreControls ?? _captureResultControls();
    // Retain only the latest successful result. A failed refresh or cancelled
    // confirmation must not destroy a result that the user has not saved.
    _lastResults = screen;
    _lastResultActivity = activityChoice;
    _restoreLastResultControls = restore;
    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    Navigator.push<ResultAction>(
      context,
      MaterialPageRoute(builder: (_) => screen),
    ).then((action) {
      if (!mounted || revision != _requestRevision || action == null) return;
      restore();
      if (action == ResultAction.edit) {
        _recentPlaceIds = [];
        setState(() => _currentStep = 0);
      } else {
        // Refresh the signed interpretation with a fresh seed. Preserve only
        // the explicitly chosen activity; unknown-condition consent is renewed.
        _recentPlaceIds = _resultPlaceIds(screen);
        _submit(repeatedActivity: activityChoice);
      }
    });
  }

  List<String> _resultPlaceIds(Widget screen) {
    final places = screen is SpotResultScreen
        ? screen.places
        : screen is CourseResultScreen
        ? screen.courses.expand((course) => jsonObjects(course)).toList()
        : <Map<String, dynamic>>[];
    return places
        .map((p) => p['place_id'])
        .whereType<String>()
        .where((id) => id.isNotEmpty)
        .toSet()
        .take(100)
        .toList();
  }

  Future<String?> _chooseActivity(Map<String, dynamic> clarification) {
    final options = jsonObjects(clarification['options']);
    return showDialog<String>(
      context: context,
      builder: (context) => ActivityChoiceDialog(options: options),
    );
  }

  Future<bool> _resolveIntent(List<dynamic> issues) async {
    final hasIssues = issues.isNotEmpty;
    final message = hasIssues
        ? issues
              .whereType<Map>()
              .map((e) => '${e['quote']} — ${e['reason']}')
              .join('\n\n')
        : '여러 장소를 순서대로 방문하는 코스 1개를 추천해요.';
    return await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: Text(hasIssues ? '문장을 조금만 바꿔주세요' : '코스로 추천할까요?'),
            content: SingleChildScrollView(child: Text(message)),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('문장 수정'),
              ),
              if (!hasIssues)
                TextButton(
                  onPressed: () => Navigator.pop(context, true),
                  child: const Text('코스로 전환해 추천'),
                ),
            ],
          ),
        ) ??
        false;
  }

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
            if (_lastResults != null)
              TextButton.icon(
                onPressed: _isLoading
                    ? null
                    : () => _openResults(
                        _lastResults!,
                        _requestRevision,
                        restoreControls: _restoreLastResultControls,
                        activityChoice: _lastResultActivity,
                      ),
                icon: const Icon(Icons.history, size: 18),
                label: const Text('이전 추천 다시 보기'),
              ),
            Expanded(
              child: AbsorbPointer(
                absorbing: _isLoading,
                child: GestureDetector(
                  onTap: () => FocusScope.of(context).unfocus(),
                  child: AnimatedSwitcher(
                    duration: MediaQuery.disableAnimationsOf(context)
                        ? Duration.zero
                        : const Duration(milliseconds: 220),
                    layoutBuilder: (child, previousChildren) => Stack(
                      alignment: Alignment.topCenter,
                      children: [...previousChildren, if (child != null) child],
                    ),
                    transitionBuilder: (child, animation) =>
                        FadeTransition(opacity: animation, child: child),
                    child: SingleChildScrollView(
                      key: ValueKey('$_currentStep:$_tagQuestion'),
                      controller: _formScrollController,
                      padding: const EdgeInsets.fromLTRB(24, 8, 24, 16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          if (_recommendationError != null)
                            _RecommendationErrorNotice(
                              message: _recommendationError!,
                            ),
                          _buildCurrentStep(),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
            _buildNavButtons(),
          ],
        ),
      ),
    );
  }

  Widget _buildStepIndicator() {
    final labels = _isSpot
        ? const ['기본 설정', '취향']
        : const ['기본 설정', '취향', '코스 구성'];
    return Container(
      padding: const EdgeInsets.fromLTRB(32, 10, 32, 8),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF8F3),
        border: Border(bottom: BorderSide(color: Colors.grey.shade200)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (int i = 0; i < labels.length; i++) ...[
            if (i > 0)
              Expanded(
                child: Container(
                  height: 1.5,
                  margin: const EdgeInsets.only(top: 14),
                  color: i <= _currentStep ? _themeColor : Colors.grey.shade300,
                ),
              ),
            Expanded(
              flex: 3,
              child: _StepDot(
                index: i,
                label: labels[i],
                currentStep: _currentStep,
                themeColor: _themeColor,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildCurrentStep() {
    switch (_currentStep) {
      case 0:
        return _buildStep1();
      case 1:
        return _buildStep2();
      case 2:
        return _buildStep3();
      default:
        return const SizedBox();
    }
  }

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
          onSelect: (r) {
            if (r != '내 주변') _cancelLocation();
            _changeControls(() {
              _region = r;
              _selectedHub = null;
              _usingFallbackOrigin = false;
              _recentPlaceIds = [];
            });
          },
        ),
        if (_region == '내 주변' && _locationError != null) ...[
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
                const Icon(
                  Icons.location_off,
                  size: 16,
                  color: Color(0xFFFF8F00),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    _locationError!,
                    style: const TextStyle(
                      fontSize: 13,
                      color: Color(0xFF795548),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
        if (_region == '내 주변' && !_locationLoading)
          TextButton.icon(
            onPressed: _fetchLocation,
            icon: const Icon(Icons.refresh),
            label: const Text('위치 다시 확인'),
          ),
        const SizedBox(height: 28),
        _label('이동 수단'),
        const SizedBox(height: 10),
        _ChoiceRow(
          options: const ['대중교통', '차'],
          selected: _transport,
          themeColor: _themeColor,
          onSelect: (t) => _changeControls(() {
            _transport = t;
            _selectedHub = null;
            _usingFallbackOrigin = false;
            _recentPlaceIds = [];
          }),
        ),
        if (_needsHub) ...[
          const SizedBox(height: 28),
          _label('어디서 출발할까요?'),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: (_kTransitHubs[_region] ?? []).map((hub) {
              final name = hub.name;
              final sel = _selectedHub == name;
              return _ChoicePill(
                label: name,
                selected: sel,
                color: _themeColor,
                onTap: () => _changeControls(() => _selectedHub = name),
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
            return _ChoicePill(
              label: _isSpot ? '$n곳' : '$n개',
              selected: sel,
              color: _themeColor,
              onTap: () => _changeControls(() => _resultCount = n),
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
              return _ChoicePill(
                label: '$n곳',
                selected: sel,
                color: _themeColor,
                onTap: () => _changeControls(() {
                  if (_spotCount == n) return;
                  _spotCount = n;
                  _slotTypes = _defaultTemplate(n);
                }),
              );
            }).toList(),
          ),
        ],
        const SizedBox(height: 20),
        if (!_needsHub)
          Row(
            children: [
              Icon(
                _locationReady ? Icons.location_on : Icons.location_searching,
                size: 15,
                color: _locationReady ? _themeColor : Colors.grey.shade400,
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  _locationLabel,
                  style: TextStyle(
                    fontSize: 13,
                    color: _locationReady ? _themeColor : Colors.grey.shade400,
                  ),
                ),
              ),
            ],
          ),
        const SizedBox(height: 8),
      ],
    );
  }

  Widget _buildStep2() {
    if (_tagQuestion != null) return _buildTagQuestion();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _title(_isSpot ? '어떤 장소를 찾고 있나요?' : '어떤 날을 원하나요?'),
        const SizedBox(height: 10),
        TextField(
          controller: _textController,
          canRequestFocus: !_isLoading,
          onChanged: (_) {
            if (_recommendationError != null) _changeControls(() {});
          },
          maxLines: 2,
          decoration: InputDecoration(
            hintText: _isSpot
                ? '원하는 장소와 조건을 적어주세요.\n예) 친구와 조용한 카페에서 쉬고 싶어요'
                : '원하는 하루와 조건을 적어주세요.\n예) 연인과 100일 기념 데이트를 하고 싶어요',
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
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: _themeColor,
                    ),
                  )
                : Icon(Icons.auto_awesome, size: 16, color: _themeColor),
            label: Text(
              '문장으로 태그 고르기',
              style: TextStyle(fontSize: 13, color: _themeColor),
            ),
          ),
        ),
        if (_selectedTags.isNotEmpty) ...[
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _selectedTags
                .map(
                  (tag) => _ChoicePill(
                    label: _kActivityTagLabels[tag] ?? tag,
                    selected: true,
                    color: _themeColor,
                    onTap: () => _openTagQuestion(
                      _visibleTagGroups.toList().indexWhere(
                        (group) => group.value.contains(tag),
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
        ],
        const SizedBox(height: 16),
        OutlinedButton.icon(
          onPressed: () => _openTagQuestion(0),
          icon: const Icon(Icons.touch_app_outlined),
          label: const Text('직접 태그 선택하기'),
        ),
        const SizedBox(height: 8),
      ],
    );
  }

  void _openTagQuestion(int index) {
    FocusScope.of(context).unfocus();
    setState(() => _tagQuestion = index < 0 ? 0 : index);
  }

  Widget _buildTagQuestion() {
    final groups = _visibleTagGroups.toList();
    final entry = groups[_tagQuestion!];
    final title = switch (entry.key) {
      '누구와' => '누구와 함께하나요?',
      '어떤 분위기' => '어떤 분위기를 원하나요?',
      '특별한 날' => '특별한 날인가요?',
      '실내 · 야외' => '실내와 야외 중 어디가 좋나요?',
      _ => '어떤 활동을 원하나요?',
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          header: true,
          label: '태그 질문 ${_tagQuestion! + 1}/${groups.length}',
          child: _title(title),
        ),
        const SizedBox(height: 12),
        _TagSection(
          title: entry.key,
          showTitle: false,
          tags: entry.value,
          selectedTags: _selectedTags,
          themeColor: _themeColor,
          hint: entry.key == '누구와'
              ? null
              : entry.key == '어떤 분위기'
              ? '여러 개 선택 가능'
              : '선택사항',
          onToggle: (tag) {
            _invalidateTags();
            _changeControls(() {
              if (_selectedTags.contains(tag)) {
                _selectedTags.remove(tag);
              } else {
                if (_kSingleSelectGroups.contains(entry.key)) {
                  _selectedTags.removeAll(entry.value);
                }
                _selectedTags.add(tag);
              }
            });
          },
        ),
      ],
    );
  }

  Widget _buildStep3() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _title('방문 순서'),
        const SizedBox(height: 28),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            for (int i = 0; i < _slotTypes.length; i++)
              _SlotChip(
                order: i + 1,
                slotType: _slotTypes[i],
                onTap: () => _showSlotPicker(i),
              ),
          ],
        ),
        const SizedBox(height: 20),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton.icon(
            onPressed: () => _changeControls(() {
              _slotTypes = _defaultTemplate(_spotCount);
            }),
            style: TextButton.styleFrom(
              foregroundColor: Colors.grey.shade500,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            ),
            icon: Icon(Icons.refresh, size: 14, color: Colors.grey.shade400),
            label: Text(
              '기본 순서로 되돌리기',
              style: TextStyle(fontSize: 12, color: Colors.grey.shade500),
            ),
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
      builder: (_) => SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 36),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${index + 1}번째 장소에서 뭘 할까요?',
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 16),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: _kSlotStyles.keys.map((type) {
                  final isSel = _slotTypes[index] == type;
                  final color = _kSlotStyles[type]!.color;
                  return _ChoicePill(
                    label: _kSlotLabels[type] ?? type,
                    selected: isSel,
                    color: color,
                    icon: _kSlotStyles[type]!.icon,
                    onTap: () {
                      _changeControls(() {
                        _slotTypes[index] = type;
                      });
                      Navigator.pop(context);
                    },
                  );
                }).toList(),
              ),
            ],
          ),
        ),
      ),
    );
  }

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
                    borderRadius: BorderRadius.circular(14),
                  ),
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
              onPressed:
                  (_currentStep == 1 && _tagQuestion != null) ||
                      _currentStep < (_isSpot ? 1 : 2)
                  ? _goNext
                  : (_isLoading || _isTagLoading ? null : _submit),
              style: ElevatedButton.styleFrom(
                backgroundColor: _themeColor,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
                elevation: 0,
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
              child: _isLoading
                  ? const SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(
                        color: Colors.white,
                        strokeWidth: 2.5,
                      ),
                    )
                  : Text(
                      _currentStep == 1 && _tagQuestion != null
                          ? '선택 완료'
                          : _currentStep < (_isSpot ? 1 : 2)
                          ? '다음'
                          : (_isSpot ? '장소 추천받기' : '코스 추천받기'),
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _title(String text) => Text(
    text,
    style: const TextStyle(
      fontSize: 24,
      fontWeight: FontWeight.w600,
      color: Color(0xFF1A1A1A),
    ),
  );

  Widget _label(String text) => Text(
    text,
    style: const TextStyle(
      fontSize: 16,
      fontWeight: FontWeight.bold,
      color: Color(0xFF1A1A1A),
    ),
  );

  void _cancelLocation() {
    ++_locationRevision;
    _locationLoading = false;
    final source = _locationSource;
    if (source is CancellableLocationSource) {
      // Cancellation handles failures internally and prevents an unsafe retry.
      source.cancel();
    }
  }

  @override
  void dispose() {
    _cancellation?.cancel();
    _requestRevision++;
    _tagRevision++;
    _cancelLocation();
    _textController.removeListener(_onTextChanged);
    _textController.dispose();
    _formScrollController.dispose();
    super.dispose();
  }
}
