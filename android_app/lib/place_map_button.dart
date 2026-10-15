import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'api_service.dart';
import 'travel_data.dart';

typedef PlaceDetailLookup = Future<String?> Function(PlaceData place);

Future<String?> _lookupDetail(PlaceData place) => ApiService.getKakaoPlaceUrl(
  name: place.name,
  lat: place.lat!,
  lng: place.lng!,
  address: place.address,
);

Future<bool> _launch(Uri uri) async {
  try {
    return await launchUrl(uri, mode: LaunchMode.externalApplication);
  } catch (_) {
    return false;
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
  try {
    final place = PlaceData.fromJson(placeJson);
    final lat = place.lat;
    final lng = place.lng;
    var detail = place.kakaoUrl;
    if (lookupDetail && lat != null && lng != null) {
      try {
        detail = await (detailLookup ?? _lookupDetail)(place) ?? '';
      } catch (_) {
        detail = '';
      }
    }
    if (!context.mounted) return;
    if (detail.isNotEmpty) {
      final uri = Uri.tryParse(detail);
      if (uri != null &&
          (uri.scheme == 'https' || uri.scheme == 'http') &&
          await _launch(uri)) {
        return;
      }
    }
    if (!context.mounted) return;
    if (lat == null || lng == null) throw const FormatException('위치 정보가 없습니다.');
    if (lookupDetail && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('장소 상세를 확인하지 못했어요. 위치를 표시할게요.')),
      );
    }
    final app = Uri.parse('kakaomap://look?p=$lat,$lng');
    bool canOpenApp;
    try {
      canOpenApp = await canLaunchUrl(app);
    } catch (_) {
      canOpenApp = false;
    }
    if (!context.mounted) return;
    if (canOpenApp && await _launch(app)) return;
    if (!context.mounted) return;
    final web = Uri.parse(
      'https://map.kakao.com/link/map/${Uri.encodeComponent(place.name)},$lat,$lng',
    );
    if (!await _launch(web)) {
      throw StateError('지도 실행 실패');
    }
  } catch (_) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('지도를 열 수 없어요. 위치 정보와 지도 앱을 확인해주세요.')),
      );
    }
  }
}
