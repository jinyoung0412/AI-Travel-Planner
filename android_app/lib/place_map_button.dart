import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'api_service.dart';
import 'travel_data.dart';

typedef PlaceDetailLookup = Future<String?> Function(PlaceData place);

bool _isKakaoDetailUrl(String url) =>
    RegExp(r'^https?://place\.map\.kakao\.com/\d+$').hasMatch(url);

Future<String?> _lookupDetail(PlaceData place) => ApiService.getKakaoPlaceUrl(
  name: place.name,
  lat: place.lat!,
  lng: place.lng!,
  address: place.address,
);

// Shared by buttons, saved cards and direct callers. A successful launch future
// only acknowledges dispatch; the external activity may not be visible yet.
_MapOpening? _activeOpening;

class _MapOpening with WidgetsBindingObserver {
  final BuildContext context;
  final _released = Completer<void>();
  Timer? _transitionTimer;
  bool _away = false;
  bool _returned = false;
  bool _finished = false;
  bool _launchUncertain = false;

  _MapOpening(this.context) {
    WidgetsBinding.instance.addObserver(this);
  }

  bool get canContinue =>
      !_released.isCompleted &&
      context.mounted &&
      !const {
        AppLifecycleState.paused,
        AppLifecycleState.hidden,
        AppLifecycleState.detached,
      }.contains(WidgetsBinding.instance.lifecycleState);

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.detached) {
      _release();
    } else if (state == AppLifecycleState.resumed) {
      if (_away) {
        _returned = true;
        if (_finished) _release();
      }
    } else {
      _away = true;
      _transitionTimer?.cancel();
    }
  }

  Future<bool> launch(Uri uri) async {
    if (!canContinue) return false;
    _away = false;
    _returned = false;
    try {
      return await launchUrl(
        uri,
        mode: LaunchMode.externalApplication,
      ).timeout(const Duration(seconds: 5));
    } on TimeoutException {
      // Dispatch may still complete on the platform. Do not launch a second URL.
      _launchUncertain = true;
      rethrow;
    } catch (_) {
      return false;
    }
  }

  Future<void> finish(bool launched) async {
    _finished = true;
    if (!(launched || _launchUncertain) ||
        !context.mounted ||
        _returned ||
        _released.isCompleted) {
      _release();
    } else if (!_away) {
      // Some platforms do not emit lifecycle events. Bound that foreground
      // guard so a successful dispatch never permanently disables retry.
      _transitionTimer = Timer(const Duration(seconds: 2), _release);
    }
    await _released.future;
  }

  void _release() {
    if (_released.isCompleted) return;
    _transitionTimer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    if (identical(_activeOpening, this)) _activeOpening = null;
    _released.complete();
  }
}

class PlaceMapButton extends StatefulWidget {
  final Map<String, dynamic> place;
  final bool lookupDetail;
  final PlaceDetailLookup? detailLookup;
  const PlaceMapButton({
    super.key,
    required this.place,
    this.lookupDetail = false,
    this.detailLookup,
  });

  @override
  State<PlaceMapButton> createState() => _PlaceMapButtonState();
}

class _PlaceMapButtonState extends State<PlaceMapButton> {
  bool _opening = false;

  Future<void> _open() async {
    if (_opening) return;
    setState(() => _opening = true);
    try {
      await openPlaceMap(
        context,
        widget.place,
        lookupDetail: widget.lookupDetail,
        detailLookup: widget.detailLookup,
      );
    } finally {
      if (mounted) setState(() => _opening = false);
    }
  }

  @override
  Widget build(BuildContext context) => TextButton.icon(
    onPressed: _opening ? null : _open,
    icon: _opening
        ? const SizedBox(
            width: 14,
            height: 14,
            child: CircularProgressIndicator(strokeWidth: 2),
          )
        : const Icon(Icons.map_outlined, size: 16),
    label: Text(
      _opening ? '불러오는 중...' : (widget.lookupDetail ? '카카오맵에서 보기' : '지도에서 보기'),
    ),
    style: TextButton.styleFrom(
      foregroundColor: Colors.grey.shade600,
      alignment: Alignment.centerLeft,
      padding: const EdgeInsets.symmetric(vertical: 8),
    ),
  );
}

Future<void> openPlaceMap(
  BuildContext context,
  Map<String, dynamic> placeJson, {
  bool lookupDetail = false,
  PlaceDetailLookup? detailLookup,
}) async {
  // A removed screen must not block a later screen, including direct callers
  // whose dialog or platform future was pending when its navigator disposed.
  if (_activeOpening != null && !_activeOpening!.context.mounted) {
    _activeOpening!._release();
  }
  if (!context.mounted || _activeOpening != null) return;
  final opening = _MapOpening(context);
  _activeOpening = opening;
  var launched = false;
  try {
    final place = PlaceData.fromJson(placeJson);
    final lat = place.lat;
    final lng = place.lng;
    var detail = place.kakaoUrl;
    // A saved Kakao identity is already a concrete destination. Do not replace
    // it with an empty/failed lookup or delay opening it on network access.
    if (!_isKakaoDetailUrl(detail) &&
        lookupDetail &&
        lat != null &&
        lng != null) {
      try {
        final resolved = await (detailLookup ?? _lookupDetail)(
          place,
        ).timeout(const Duration(seconds: 36));
        if (resolved != null && _isKakaoDetailUrl(resolved)) detail = resolved;
      } catch (_) {
        // The coordinate fallback below still requires consent and eligibility.
      }
    }
    if (!context.mounted || !opening.canContinue) return;
    if (_isKakaoDetailUrl(detail)) {
      final uri = Uri.parse(detail.replaceFirst(RegExp(r'^http:'), 'https:'));
      launched = await opening.launch(uri);
      if (launched) return;
    }
    if (!context.mounted || !opening.canContinue) return;
    if (lat == null || lng == null) throw const FormatException('위치 정보가 없습니다.');
    if (!place.coordinateMapAllowed) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('좌표 품질 확인이 필요한 장소예요. 좌표 지도 대신 장소 이름과 주소를 확인해주세요.'),
        ),
      );
      return;
    }
    // Neither a concrete address nor finite coordinates proves location
    // accuracy. Older saved records have no coordinate-quality contract.
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        scrollable: true,
        title: const Text('참고 위치 열기'),
        content: Text(
          '${place.name}\n${place.address}\n\n'
          '저장된 좌표가 실제 장소와 일치하는지 확인되지 않았어요. '
          '지도에서 장소 이름과 주소를 다시 확인해주세요.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('취소'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('참고 위치 열기'),
          ),
        ],
      ),
    );
    if (confirmed != true || !opening.canContinue) return;
    final app = Uri.parse('kakaomap://look?p=$lat,$lng');
    bool canOpenApp;
    try {
      canOpenApp = await canLaunchUrl(app).timeout(const Duration(seconds: 5));
    } catch (_) {
      canOpenApp = false;
    }
    if (!opening.canContinue) return;
    if (canOpenApp) {
      launched = await opening.launch(app);
      if (launched) return;
    }
    if (!opening.canContinue) return;
    // Kakao's documented coordinate-only link keeps labels out of the routing
    // fields: an encoded label comma can redirect mobile web to its home page.
    // Keep the original name/address in the consent notice and saved record.
    final web = Uri.parse('https://map.kakao.com/link/map/$lat,$lng');
    launched = await opening.launch(web);
    if (!launched) {
      throw StateError('지도 실행 실패');
    }
  } catch (_) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('지도를 열 수 없어요. 위치 정보와 지도 앱을 확인해주세요.')),
      );
    }
  } finally {
    await opening.finish(launched);
  }
}
